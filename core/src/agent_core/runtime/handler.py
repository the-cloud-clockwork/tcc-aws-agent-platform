"""Generic agent handler — one handler renders any blueprint."""
from __future__ import annotations

import logging
import os
from typing import Any

from agent_core.blueprints.loader import BlueprintLoader
from agent_core.runtime.adapter import AgentResult, normalize_payload
from agent_core.runtime.agent_config import AgentConfigRegistry
from agent_core.runtime.idempotency import IdempotencyStore, generate_idempotency_key
from agent_core.runtime.marshal import marshal_output

logger = logging.getLogger(__name__)


class GenericHandler:
    """Configurable agent handler that renders any blueprint.

    Handles payload normalization, validation, idempotency, agent session
    lifecycle, output marshalling, and response formatting.
    """

    def __init__(
        self,
        loader: BlueprintLoader,
        config_registry: AgentConfigRegistry,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self._loader = loader
        self._configs = config_registry
        self._idempotency = idempotency_store

    def handle(self, event: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Handle a Lambda or AgentCore event."""
        # 1. Normalize payload
        payload = normalize_payload(event)
        agent_id = payload.agent_id
        if agent_id == "unknown":
            agent_id = os.environ.get("AGENT_ID", "unknown")
        session_id = payload.session_id
        params = dict(payload.parameters)

        # 2. Look up config
        config = self._configs.get(agent_id)
        if config is None:
            return AgentResult(
                status="error", agent_id=agent_id, session_id=session_id,
                error=f"Unknown agent: {agent_id}. Registered: {self._configs.list_agents()}",
            ).to_lambda_response()

        # 3. Apply defaults
        for k, v in config.defaults.items():
            params.setdefault(k, v)

        # 4. Validate required fields
        for field_name in config.required_fields:
            if field_name not in params or params[field_name] is None:
                return AgentResult(
                    status="error", agent_id=agent_id, session_id=session_id,
                    error=f"Missing required field: {field_name}",
                ).to_lambda_response()

        # 5. Idempotency check
        idem_key = generate_idempotency_key(
            agent_id=agent_id,
            operation=config.operation_name,
            params={k: params[k] for k in sorted(config.required_fields) if k in params},
        )
        if self._idempotency:
            cached = self._idempotency.check(idem_key)
            if cached is not None:
                logger.info("Idempotency hit for %s: %s", agent_id, idem_key)
                return AgentResult(
                    status="success", agent_id=agent_id, session_id=session_id, output=cached,
                ).to_lambda_response()

        # 6. Build prompt and run agent
        try:
            user_prompt = config.build_prompt(params, idem_key)

            with self._loader.build_agent_session(agent_id) as session:
                result = session.agent(user_prompt)

            output = marshal_output(result, agent_id, session_id)

            # 7. Store idempotency
            if self._idempotency:
                self._idempotency.store(idem_key, output)

            return AgentResult(
                status="success", agent_id=agent_id, session_id=session_id,
                output=output,
                claim_check=output.get("claim_check", False),
                artifact_id=output.get("artifact_id"),
            ).to_lambda_response()

        except Exception as exc:
            logger.exception("Agent '%s' failed", agent_id)
            return AgentResult(
                status="error", agent_id=agent_id, session_id=session_id,
                error=str(exc),
            ).to_lambda_response()
