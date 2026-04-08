"""Tests for ENH-015 (extra=forbid) and ENH-016 (schema additions)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.blueprints.agent import (
    AgentBlueprint,
    GraphEdgeConfig,
    GraphNodeConfig,
    MultiAgentConfig,
)
from agent_core.blueprints.strategy import StrategyEvaluationConfig
from agent_core.schemas.evaluation_config import EvaluationPersistenceConfig
from agent_core.schemas.identity_config import CredentialConfig

_MODEL_DICT = {
    "provider": "bedrock",
    "model_id": "test-model",
    "temperature": 0.5,
    "max_tokens": 1024,
}


class TestGraphNodeConfigHardening:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            GraphNodeConfig(
                agent_ref="bp-1", node_id="n1", unknown_field="bad"
            )

    def test_agent_ref_optional(self):
        node = GraphNodeConfig(node_id="gate-1", type="gate")
        assert node.agent_ref is None
        assert node.type == "gate"

    def test_gate_node_with_condition(self):
        node = GraphNodeConfig(
            node_id="gate-1",
            type="gate",
            trip_condition="score > 0.8",
            fallback="fallback-node",
        )
        assert node.trip_condition == "score > 0.8"
        assert node.fallback == "fallback-node"

    def test_agent_node_defaults(self):
        node = GraphNodeConfig(agent_ref="bp-1", node_id="n1")
        assert node.type == "agent"
        assert node.trip_condition is None
        assert node.fallback is None


class TestGraphEdgeConfigHardening:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            GraphEdgeConfig(
                from_node="a", to_node="b", unknown="bad"
            )


class TestMultiAgentConfigHardening:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            MultiAgentConfig(unknown_field="bad")

    def test_specialists_field(self):
        cfg = MultiAgentConfig(
            role="coordinator",
            pattern="swarm",
            specialists=["analyst", "researcher"],
        )
        assert cfg.specialists == ["analyst", "researcher"]

    def test_specialists_default_empty(self):
        cfg = MultiAgentConfig()
        assert cfg.specialists == []


class TestCredentialConfigHardening:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            CredentialConfig(
                name="test",
                type="api_key",
                provider="test-provider",
                unknown="bad",
            )

    def test_secret_arn_optional(self):
        cfg = CredentialConfig(
            name="test", type="api_key", provider="test-provider"
        )
        assert cfg.secret_arn is None

    def test_secret_arn_set(self):
        cfg = CredentialConfig(
            name="test",
            type="api_key",
            provider="test-provider",
            secret_arn="arn:aws:secretsmanager:eu-west-1:123456789012:secret:my-secret",
        )
        assert cfg.secret_arn.startswith("arn:aws:secretsmanager")


class TestStrategyEvaluationConfigHardening:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            StrategyEvaluationConfig(
                primary_metric="accuracy", unknown="bad"
            )

    def test_persistence_optional(self):
        cfg = StrategyEvaluationConfig(primary_metric="accuracy")
        assert cfg.persistence is None

    def test_persistence_with_config(self):
        cfg = StrategyEvaluationConfig(
            primary_metric="accuracy",
            persistence=EvaluationPersistenceConfig(
                enabled=True,
                table_env="EVAL_TABLE",
                retention_days=90,
            ),
        )
        assert cfg.persistence.enabled is True
        assert cfg.persistence.table_env == "EVAL_TABLE"


class TestAgentBlueprintHardening:
    def test_extra_top_level_field_rejected(self):
        with pytest.raises(ValidationError):
            AgentBlueprint(
                id="test",
                version="1.0.0",
                name="Test",
                model=_MODEL_DICT,
                prompt_ref="test",
                unknown_top_level="bad",
            )
