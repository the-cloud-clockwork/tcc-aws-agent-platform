"""Tests for the Cedar translator — YAML rules to Cedar policy statements."""

from __future__ import annotations

from agent_core.policy.translator import (
    translate_rule,
    translate_rules,
    validate_cedar_expression,
)
from agent_core.schemas.policy_config import PolicyRuleConfig


class TestTranslateRule:
    def test_allow_rule(self):
        rule = PolicyRuleConfig(name="r1", allow="query_data")
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert cedar.startswith("permit(")
        assert 'AgentCore::Action::"query_data"' in cedar
        assert 'AgentCore::Gateway::"arn:aws:gw:123"' in cedar
        assert cedar.endswith(";")

    def test_deny_rule(self):
        rule = PolicyRuleConfig(name="r1", deny="delete_record")
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert cedar.startswith("forbid(")
        assert 'AgentCore::Action::"delete_record"' in cedar

    def test_with_when_condition(self):
        rule = PolicyRuleConfig(
            name="r1", allow="update", when="context.input.amount <= 500"
        )
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert "when { context.input.amount <= 500 }" in cedar

    def test_with_unless_condition(self):
        rule = PolicyRuleConfig(
            name="r1",
            deny="approve",
            unless="principal.scope.contains('group:Managers')",
        )
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert "unless { principal.scope.contains('group:Managers') }" in cedar

    def test_with_principal(self):
        rule = PolicyRuleConfig(
            name="r1",
            allow="query",
            principal='AgentCore::Principal::"admin"',
        )
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert 'AgentCore::Principal::"admin"' in cedar
        assert cedar.startswith('permit(AgentCore::Principal::"admin"')

    def test_default_principal(self):
        rule = PolicyRuleConfig(name="r1", allow="query")
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert cedar.startswith("permit(principal,")

    def test_with_target_prefix(self):
        rule = PolicyRuleConfig(name="r1", allow="process_refund")
        cedar = translate_rule(
            rule, gateway_arn="arn:aws:gw:123", target_prefix="OrderTarget"
        )
        assert 'AgentCore::Action::"OrderTarget___process_refund"' in cedar

    def test_without_target_prefix(self):
        rule = PolicyRuleConfig(name="r1", allow="process_refund")
        cedar = translate_rule(rule, gateway_arn="arn:aws:gw:123")
        assert 'AgentCore::Action::"process_refund"' in cedar
        assert "___" not in cedar


class TestTranslateRules:
    def test_multiple_rules(self):
        rules = [
            PolicyRuleConfig(name="r1", allow="query"),
            PolicyRuleConfig(name="r2", deny="delete"),
        ]
        cedar = translate_rules(rules, gateway_arn="arn:aws:gw:123")
        assert "// r1" in cedar
        assert "// r2" in cedar
        assert "permit(" in cedar
        assert "forbid(" in cedar

    def test_empty_rules(self):
        cedar = translate_rules([], gateway_arn="arn:aws:gw:123")
        assert cedar == ""

    def test_single_rule(self):
        rules = [PolicyRuleConfig(name="only", allow="query")]
        cedar = translate_rules(rules, gateway_arn="arn:aws:gw:123")
        assert "// only" in cedar
        assert "\n\n" not in cedar  # single rule, no separator


class TestValidateCedarExpression:
    def test_valid_expression(self):
        errors = validate_cedar_expression("context.input.amount <= 500")
        assert errors == []

    def test_balanced_braces(self):
        errors = validate_cedar_expression("{ context.input.amount <= 500 }")
        assert errors == []

    def test_unbalanced_open_brace(self):
        errors = validate_cedar_expression("{ context.input.amount <= 500")
        assert any("unclosed" in e for e in errors)

    def test_unbalanced_close_brace(self):
        errors = validate_cedar_expression("context.input.amount <= 500 }")
        assert any("unexpected" in e for e in errors)

    def test_unbalanced_parens(self):
        errors = validate_cedar_expression("(context.input.amount <= 500")
        assert any("unclosed" in e for e in errors)

    def test_empty_expression(self):
        errors = validate_cedar_expression("")
        assert any("empty" in e.lower() for e in errors)

    def test_whitespace_only(self):
        errors = validate_cedar_expression("   ")
        assert any("empty" in e.lower() for e in errors)
