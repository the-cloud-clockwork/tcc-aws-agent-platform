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

    def handle(
        self, payload_data: dict[str, Any], context: InvocationContext | None = None
    ) -> dict[str, Any]:
        """Handle an AgentCore Runtime invocation."""
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

            # Create session if manager present
            session_state = None
            if self._session_manager is not None:
                from agent_core.execution.mode import get_execution_mode

                session_state = self._session_manager.create_session(
                    session_id=session_id,
                    agent_id=agent_id,
                    execution_mode=get_execution_mode().value,
                )

            # Load blueprint to get artifact config
            artifact_tier = "platform"
            artifact_kms = None
            try:
                blueprint = self._loader.load_agent(agent_id)
                artifact_tier = blueprint.artifacts.tier
                artifact_kms = blueprint.artifacts.kms_key_alias
            except Exception as bp_err:
                logger.warning(
                    "Could not load blueprint for artifact config: %s", bp_err
                )

            # Resolve KMS key: prefer tier-based env var (full ARN), fall back to alias
            tier_env = f"{artifact_tier.upper()}_ARTIFACTS_KMS_KEY_ARN"
            tier_kms_arn = os.environ.get(tier_env, "")
            if tier_kms_arn:
                artifact_kms = tier_kms_arn
            elif artifact_kms and not artifact_kms.startswith("arn:"):
                artifact_kms = f"alias/{artifact_kms}"

            # Extract date from payload params
            artifact_date = (
                params.get("analysis_date")
                or params.get("date")
                or params.get("pipeline_date")
            )

            with self._loader.build_agent_session(agent_id) as session:
                result = session.run(user_prompt)

            output = marshal_output(
                result,
                agent_id,
                session_id,
                tier=artifact_tier,
                kms_key_alias=artifact_kms,
                date=artifact_date,
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
            logger.error("Agent '%s' failed:\n%s", agent_id, tb_str)
            # Do NOT persist session on error — avoid storing partial state
            return AgentResult(
                status="error",
                agent_id=agent_id,
                session_id=session_id,
                error=tb_str[-8000:],  # Last 8000 chars of full traceback
            ).to_response()
