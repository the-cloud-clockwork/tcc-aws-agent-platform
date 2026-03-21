"""Tests for PolicyConfig and PolicyRuleConfig Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.schemas.policy_config import PolicyConfig, PolicyRuleConfig


class TestPolicyRuleConfig:
    def test_allow_rule(self):
        rule = PolicyRuleConfig(name="r1", allow="query_data")
        assert rule.allow == "query_data"
        assert rule.deny is None

    def test_deny_rule(self):
        rule = PolicyRuleConfig(name="r1", deny="delete_record")
        assert rule.deny == "delete_record"
        assert rule.allow is None

    def test_allow_with_when(self):
        rule = PolicyRuleConfig(
            name="r1", allow="update", when="context.input.amount <= 500"
        )
        assert rule.when == "context.input.amount <= 500"

    def test_deny_with_unless(self):
        rule = PolicyRuleConfig(
            name="r1",
            deny="approve",
            unless="principal.scope.contains('group:Managers')",
        )
        assert rule.unless == "principal.scope.contains('group:Managers')"

    def test_both_allow_deny_rejected(self):
        with pytest.raises(ValidationError, match="exactly one"):
            PolicyRuleConfig(name="r1", allow="a", deny="b")

    def test_neither_allow_deny_rejected(self):
        with pytest.raises(
            ValidationError, match="one of 'allow' or 'deny' is required"
        ):
            PolicyRuleConfig(name="r1")

    def test_principal_optional(self):
        rule = PolicyRuleConfig(name="r1", allow="query")
        assert rule.principal is None

    def test_principal_set(self):
        rule = PolicyRuleConfig(
            name="r1",
            allow="query",
            principal='AgentCore::Principal::"admin"',
        )
        assert rule.principal == 'AgentCore::Principal::"admin"'

    def test_conditions_optional(self):
        rule = PolicyRuleConfig(name="r1", allow="query")
        assert rule.when is None
        assert rule.unless is None

    def test_frozen(self):
        rule = PolicyRuleConfig(name="r1", allow="query")
        with pytest.raises(ValidationError):
            rule.name = "modified"


class TestPolicyConfig:
    def test_required_fields(self):
        with pytest.raises(ValidationError):
            PolicyConfig()

    def test_valid_enforce(self):
        config = PolicyConfig(engine="TestEngine", mode="ENFORCE")
        assert config.engine == "TestEngine"
        assert config.mode == "ENFORCE"

    def test_valid_log_only(self):
        config = PolicyConfig(engine="TestEngine", mode="LOG_ONLY")
        assert config.mode == "LOG_ONLY"

    def test_invalid_mode(self):
        with pytest.raises(ValidationError, match="pattern"):
            PolicyConfig(engine="TestEngine", mode="PERMISSIVE")

    def test_empty_rules(self):
        config = PolicyConfig(engine="E", mode="ENFORCE")
        assert config.rules == []

    def test_with_rules(self):
        config = PolicyConfig(
            engine="E",
            mode="ENFORCE",
            rules=[
                PolicyRuleConfig(name="r1", allow="query"),
                PolicyRuleConfig(name="r2", deny="delete"),
            ],
        )
        assert len(config.rules) == 2

    def test_target_prefix_optional(self):
        config = PolicyConfig(engine="E", mode="ENFORCE")
        assert config.target_prefix is None

    def test_target_prefix_set(self):
        config = PolicyConfig(engine="E", mode="ENFORCE", target_prefix="OrderTarget")
        assert config.target_prefix == "OrderTarget"

    def test_frozen(self):
        config = PolicyConfig(engine="E", mode="ENFORCE")
        with pytest.raises(ValidationError):
            config.engine = "modified"
