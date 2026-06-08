"""Generic agent handler — one handler renders any blueprint."""

from __future__ import annotations

import logging
import os
from typing import Any

from agent_core.blueprints.loader import BlueprintLoader
from agent_core.runtime.adapter import AgentResult, InvocationContext, normalize_payload
from agent_core.runtime.agent_config import AgentConfigRegistry
from agent_core.runtime.idempotency import IdempotencyStore, generate_idempotency_key
from agent_core.runtime.marshal import marshal_output
from agent_core.runtime.session import SessionManager

logger = logging.getLogger(__name__)


def _log_history_shape(agent_id: str, history: list[Any]) -> None:
    """Emit a compact summary of conversation_history to CloudWatch.

    Diagnostic for marshal v2/v3 — tells us per-run which tool names appear
    in the captured Strands message list, so we can spot mismatches between
    expected and actual create_artifact / toolResult shapes without paying
    the cost of dumping the full conversation.
    """
    try:
        tool_use_names: dict[str, int] = {}
        tool_result_count = 0
        tool_result_statuses: dict[str, int] = {}
        text_blocks = 0
        for msg in history:
            if not isinstance(msg, dict):
                continue
            for block in msg.get("content", []) or []:
                if not isinstance(block, dict):
                    continue
                tu = block.get("toolUse")
                if isinstance(tu, dict):
                    name = str(tu.get("name", "?"))
                    tool_use_names[name] = tool_use_names.get(name, 0) + 1
                tr = block.get("toolResult")
                if isinstance(tr, dict):
                    tool_result_count += 1
                    s = str(tr.get("status", "missing"))
                    tool_result_statuses[s] = tool_result_statuses.get(s, 0) + 1
                if "text" in block:
                    text_blocks += 1
        logger.info(
            "marshal_v2.history_shape agent=%s messages=%d tool_uses=%s "
            "tool_results=%d statuses=%s text_blocks=%d",
            agent_id, len(history), tool_use_names,
            tool_result_count, tool_result_statuses, text_blocks,
        )
    except Exception as exc:
        logger.warning("Failed to log history shape for %s: %s", agent_id, exc)


class GenericHandler:
    """Configurable agent handler that renders any blueprint.

    Handles payload normalization, validation, idempotency, agent session
    lifecycle, session management, output marshalling, and response formatting.
    """

    def __init__(
        self,
        loader: BlueprintLoader,
        config_registry: AgentConfigRegistry,
        idempotency_store: IdempotencyStore | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._loader = loader
        self._configs = config_registry
        self._idempotency = idempotency_store
        self._session_manager = session_manager

    def _resolve_artifact_config(self, agent_id: str) -> tuple[str, str | None]:
        """Resolve artifact tier and KMS key from blueprint and env."""
        tier = "platform"
        kms: str | None = None
        try:
            bp = self._loader.load_agent(agent_id)
            tier = bp.artifacts.tier
            kms = bp.artifacts.kms_key_alias
        except Exception as bp_err:
            logger.warning("Could not load blueprint for artifact config: %s", bp_err)

        tier_kms_arn = os.environ.get(f"{tier.upper()}_ARTIFACTS_KMS_KEY_ARN", "")
        if tier_kms_arn:
            kms = tier_kms_arn
        elif kms and not kms.startswith("arn:"):
            kms = f"alias/{kms}"
        return tier, kms

    def handle(
        self, payload_data: dict[str, Any], context: InvocationContext | None = None
    ) -> dict[str, Any]:
        """Handle an AgentCore Runtime invocation.

        Payload contract
        ----------------
        The top-level ``payload_data`` dict is passed through ``normalize_payload``
        (agent_core/runtime/adapter.py) which reads these keys:

        ==================  ========  =========  ========================================
        Key                 Type      Required   Notes
        ==================  ========  =========  ========================================
        ``agent_id``        str       no         Falls back to ``AGENT_ID`` env var.
        ``session_id``      str       no         Auto-UUID if missing.
        ``execution_mode``  str       no         Defaults to ``"simulation"``.
        ``parameters``      dict      no         Agent-specific inputs (``date``,
                                                 ``watchlist_id``, ``threshold_pct``,
                                                 etc.). Also accepts ``params``.
        ``memory_context``  dict      no         Pre-loaded memory passthrough.
        ``metadata``        dict      no         Arbitrary metadata.
        ==================  ========  =========  ========================================

        **Agent-specific inputs must go inside ``parameters``.** Top-level keys
        outside the table above are ignored by the handler.

        Minimal direct-invoke example (gap-detector)::

            {
              "parameters": {
                "date": "2026-04-10",
                "watchlist_id": "default",
                "threshold_pct": 2.0
              }
            }

        Bash::

            PAYLOAD=$(echo -n '{"parameters":{"date":"2026-04-10","watchlist_id":"default","threshold_pct":2.0}}' | base64 -w0)
            SID=$(uuidgen | tr -d '-')$(uuidgen | tr -d '-' | head -c 8)
            aws bedrock-agentcore invoke-agent-runtime \\
              --agent-runtime-arn "arn:aws:bedrock-agentcore:REGION:ACCT:runtime/AGENT-SUFFIX" \\
              --runtime-session-id "$SID" \\
              --payload "$PAYLOAD" /tmp/out.json

        Lambda-wrapper convention (Step Functions path)
        -----------------------------------------------
        The Step Functions ``invoke_agent_lambda`` wraps inputs differently when
        ``MemoryBranch`` is set — it JSON-encodes the entire prompt dict into a
        ``"prompt"`` string key and adds ``memory_branch`` + ``memory_merge_strategy``
        top-level keys. Those keys are consumed by the AgentCore SDK memory layer
        upstream of this handler; they do NOT populate ``parameters``. Use the
        direct ``parameters`` shape for tests and tool-level invocations.
        """
        # 1. Normalize payload
        payload = normalize_payload(payload_data)
        agent_id = payload.agent_id
        if agent_id == "unknown":
            agent_id = os.environ.get("AGENT_ID", "unknown")
        session_id = payload.session_id
        params = dict(payload.parameters)

        # 2. Look up config
        config = self._configs.get(agent_id)
        if config is None:
            return AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=session_id,
                error=f"Unknown agent: {agent_id}. Registered: {self._configs.list_agents()}",
            ).to_response()

        # 3. Apply defaults
        for k, v in config.defaults.items():
            params.setdefault(k, v)

        # 4. Validate required fields
        for field_name in config.required_fields:
            if field_name not in params or params[field_name] is None:
                return AgentResult(
                    status="error",
                    agent_id=agent_id,
                    session_id=session_id,
                    error=f"Missing required field: {field_name}",
                ).to_response()

        # 5. Idempotency check
        idem_key = generate_idempotency_key(
            agent_id=agent_id,
            operation=config.operation_name,
            params={
                k: params[k] for k in sorted(config.required_fields) if k in params
            },
        )
        if self._idempotency:
            cached = self._idempotency.check(idem_key)
            if cached is not None:
                logger.info("Idempotency hit for %s: %s", agent_id, idem_key)
                return AgentResult(
                    status="success",
                    agent_id=agent_id,
                    session_id=session_id,
                    output=cached,
                ).to_response()

        # 6. Build prompt and run agent
        try:
            user_prompt = config.build_prompt(params, idem_key)

            from agent_core.execution.mode import get_execution_mode

            resolved_mode = get_execution_mode(event_mode=payload.execution_mode)

            # Create session if manager present
            session_state = None
            if self._session_manager is not None:
                session_state = self._session_manager.create_session(
                    session_id=session_id,
                    agent_id=agent_id,
                    execution_mode=resolved_mode.value,
                )

            artifact_tier, artifact_kms = self._resolve_artifact_config(agent_id)
            artifact_date = params.get("analysis_date") or params.get("date") or params.get("pipeline_date")

            with self._loader.build_agent_session(agent_id, mode=resolved_mode) as session:
                result = session.run(user_prompt)
                # Snapshot the full Strands message history before MCP teardown.
                # marshal_output uses this to (a) alias an earlier
                # create_artifact platform tier write instead of duplicating it
                # and (b) walk for a typed payload when the final assistant
                # message is markdown-only.
                conversation_history = list(session.messages)
                _log_history_shape(agent_id, conversation_history)

            output = marshal_output(
                result,
                agent_id,
                session_id,
                tier=artifact_tier,
                kms_key_alias=artifact_kms,
                date=artifact_date,
                conversation_history=conversation_history,
            )

            # Persist session on success
            if self._session_manager is not None and session_state is not None:
                self._session_manager.persist_session(session_state)

            # 7. Store idempotency
            if self._idempotency:
                self._idempotency.store(idem_key, output)

            return AgentResult(
                status="success",
                agent_id=agent_id,
                session_id=session_id,
                output=dict(output).get("output", output),
                claim_check=dict(output).get("claim_check", False),
                artifact_id=dict(output).get("artifact_id", ""),
                s3_key=dict(output).get("s3_key", ""),
                tier=dict(output).get("tier", artifact_tier),
            ).to_response()

        except Exception as exc:
            import traceback as _tb
            # Surface FULL traceback + cause chain (MCPClient swallows real errors)
            tb_str = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))

            # Unwrap ExceptionGroup / __cause__ / __context__ to the leaf cause(s),
            # so a real error buried inside an anyio TaskGroup — e.g. an httpx 403
            # from an MCP runtime that lost its JWT authorizer — is named up front
            # instead of the opaque "unhandled errors in a TaskGroup (N sub-exceptions)".
            def _leaf_causes(e, _seen=None):
                _seen = _seen if _seen is not None else set()
                if e is None or id(e) in _seen:
                    return []
                _seen.add(id(e))
                subs = getattr(e, "exceptions", None)  # BaseExceptionGroup
                if subs:
                    leaves: list = []
                    for s in subs:
                        leaves.extend(_leaf_causes(s, _seen))
                    return leaves
                nested = e.__cause__ or e.__context__
                deeper = _leaf_causes(nested, _seen) if nested is not None else []
                return deeper or [e]

            _leaves = _leaf_causes(exc)
            _root = "; ".join(f"{type(le).__name__}: {le}" for le in _leaves[:5])
            if _root:
                # Append (not prepend) so it survives the error=tb_str[-8000:] tail slice.
                tb_str = f"{tb_str}\n\nROOT CAUSE: {_root}"
            logger.error("Agent '%s' failed (root cause: %s):\n%s", agent_id, _root, tb_str)

            # Classify upstream LLM failures so SFN can distinguish them from
            # pipeline/domain errors and route to a FAIL state instead of the
            # empty-gaps fallback. Travels under $.gaps.body.metadata.error_class.
            error_class = "agent_error"
            http_status: int | None = None
            provider: str | None = None
            retriable = False
            try:
                import litellm
                if isinstance(exc, litellm.BadGatewayError):
                    error_class = "upstream_llm_unavailable"
                    http_status = 502
                    provider = getattr(exc, "llm_provider", None)
                    retriable = True
                elif isinstance(exc, litellm.ServiceUnavailableError):
                    error_class = "upstream_llm_unavailable"
                    http_status = 503
                    provider = getattr(exc, "llm_provider", None)
                    retriable = True
                elif isinstance(exc, litellm.Timeout):
                    error_class = "upstream_llm_timeout"
                    retriable = True
                elif isinstance(exc, litellm.RateLimitError):
                    error_class = "upstream_llm_rate_limit"
                    http_status = 429
                    retriable = True
                elif isinstance(exc, litellm.APIConnectionError):
                    error_class = "upstream_llm_connection_error"
                    retriable = True
                elif isinstance(exc, litellm.APIError):
                    error_class = "upstream_llm_api_error"
                    http_status = getattr(exc, "status_code", None)
                    provider = getattr(exc, "llm_provider", None)
                    retriable = http_status in (429, 500, 502, 503, 504)
            except ImportError:
                pass

            # Do NOT persist session on error — avoid storing partial state
            return AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=session_id,
                error=tb_str[-8000:],  # Last 8000 chars of full traceback
                metadata={
                    "error_class": error_class,
                    "http_status": http_status,
                    "provider": provider,
                    "retriable": retriable,
                },
            ).to_response()
