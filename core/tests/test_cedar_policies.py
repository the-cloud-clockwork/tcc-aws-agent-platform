"""Unit tests for Cedar policy builder and validator."""

from __future__ import annotations

import pytest

from agent_core.policy.cedar_policies import (
    CedarPolicy,
    CedarPolicyBuilder,
    PolicyEffect,
    PolicyAction,
    validate_policy_set,
    CEDAR_SCHEMA,
)


class TestCedarPolicy:
    """Tests for individual Cedar policy serialization."""

    def test_simple_permit(self):
        policy = CedarPolicy(
            policy_id="test",
            effect=PolicyEffect.PERMIT,
            description="Test policy",
            principal='Agent::"test_agent"',
            action=PolicyAction.INVOKE_TOOL,
            resource='Tool::"test-mcp::do_thing"',
        )
        cedar_text = policy.to_cedar()

        assert "permit(" in cedar_text
        assert 'Agent::"test_agent"' in cedar_text
        assert 'Tool::"test-mcp::do_thing"' in cedar_text

    def test_forbid_with_condition(self):
        policy = CedarPolicy(
            policy_id="test-forbid",
            effect=PolicyEffect.FORBID,
            description="Forbid in simulation",
            principal='in AgentGroup::"all_agents"',
            action=PolicyAction.INVOKE_TOOL,
            resource='Tool::"executor-mcp::execute_action"',
            conditions=['context.execution_mode == "simulation"'],
        )
        cedar_text = policy.to_cedar()

        assert "forbid(" in cedar_text
        assert 'context.execution_mode == "simulation"' in cedar_text

    def test_group_principal_uses_in(self):
        policy = CedarPolicy(
            policy_id="test-group",
            effect=PolicyEffect.PERMIT,
            description="Group test",
            principal='in AgentGroup::"test_agents"',
            action=PolicyAction.INVOKE_TOOL,
            resource='in ToolGroup::"data-mcp"',
        )
        cedar_text = policy.to_cedar()

        assert 'principal in AgentGroup::"test_agents"' in cedar_text
        assert 'resource in ToolGroup::"data-mcp"' in cedar_text


class TestCedarPolicyBuilder:
    """Tests for the policy set builder."""

    def test_build_empty(self):
        builder = CedarPolicyBuilder()
        result = builder.build()
        assert "Cedar Policies" in result

    def test_add_policy(self):
        builder = CedarPolicyBuilder()
        builder.add_policy(CedarPolicy(
            policy_id="test-1",
            effect=PolicyEffect.PERMIT,
            description="Test permit",
            principal='Agent::"test"',
            action=PolicyAction.INVOKE_TOOL,
            resource='Tool::"test::do"',
        ))
        result = builder.build()
        assert "test_1" in result or "Test permit" in result

    def test_build_contains_all_policies(self):
        builder = CedarPolicyBuilder()
        policies = [
            CedarPolicy(
                policy_id=f"p{i}",
                effect=PolicyEffect.PERMIT,
                description=f"Policy {i}",
                principal='Agent::"test"',
                action=PolicyAction.INVOKE_TOOL,
                resource='Tool::"test::op"',
            )
            for i in range(3)
        ]
        for p in policies:
            builder.add_policy(p)
        result = builder.build()
        for p in policies:
            assert p.description in result

    def test_write_to_file(self, tmp_path):
        builder = CedarPolicyBuilder()
        builder.add_policy(CedarPolicy(
            policy_id="test",
            effect=PolicyEffect.PERMIT,
            description="Write test",
            principal='Agent::"test"',
            action=PolicyAction.INVOKE_TOOL,
            resource='Tool::"t::op"',
        ))
        output = tmp_path / "test.cedar"
        builder.write_to_file(str(output))
        assert output.exists()
        content = output.read_text()
        assert "permit(" in content


class TestValidatePolicySet:
    """Tests for policy validation."""

    def test_valid_policies(self):
        policies = [
            CedarPolicy(
                policy_id="p1",
                effect=PolicyEffect.PERMIT,
                description="First",
                principal='Agent::"a"',
                action=PolicyAction.INVOKE_TOOL,
                resource='Tool::"t"',
            ),
        ]
        errors = validate_policy_set(policies)
        assert len(errors) == 0

    def test_duplicate_ids_detected(self):
        policies = [
            CedarPolicy(
                policy_id="dupe",
                effect=PolicyEffect.PERMIT,
                description="First",
                principal='Agent::"a"',
                action=PolicyAction.INVOKE_TOOL,
                resource='Tool::"t"',
            ),
            CedarPolicy(
                policy_id="dupe",
                effect=PolicyEffect.FORBID,
                description="Second",
                principal='Agent::"b"',
                action=PolicyAction.INVOKE_TOOL,
                resource='Tool::"t"',
            ),
        ]
        errors = validate_policy_set(policies)
        assert any("Duplicate" in e for e in errors)


class TestCedarSchema:
    """Tests for Cedar entity schema."""

    def test_schema_has_entity_types(self):
        assert "Agent" in CEDAR_SCHEMA["AgentCore"]["entityTypes"]
        assert "Tool" in CEDAR_SCHEMA["AgentCore"]["entityTypes"]
        assert "AgentGroup" in CEDAR_SCHEMA["AgentCore"]["entityTypes"]
        assert "ToolGroup" in CEDAR_SCHEMA["AgentCore"]["entityTypes"]

    def test_schema_has_actions(self):
        actions = CEDAR_SCHEMA["AgentCore"]["actions"]
        assert "invoke_tool" in actions
        assert "read_memory" in actions
        assert "write_memory" in actions

    def test_agent_member_of_group(self):
        agent = CEDAR_SCHEMA["AgentCore"]["entityTypes"]["Agent"]
        assert "AgentGroup" in agent["memberOfTypes"]
