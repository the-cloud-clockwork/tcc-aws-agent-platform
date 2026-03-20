"""Tests for advanced AgentCore features — memory branching, streaming, multi-tenant."""

from __future__ import annotations

import pytest

from agent_core.agentcore.memory_branching import MemoryBranchManager
from agent_core.agentcore.multi_tenant import (
    TenantContext,
    TenantLimitExceeded,
    TenantResourceGuard,
    TenantScopedKey,
)
from agent_core.agentcore.streaming import StreamBuffer, StreamEventType, format_sse


class TestMemoryBranching:
    def test_create_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("branch_a", base_state={"items": ["item-A"]})
        assert branch.name == "branch_a"
        assert branch.state == {"items": ["item-A"]}
        assert branch.status == "active"

    def test_update_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("test", base_state={"count": 0})
        mgr.update_branch(branch.branch_id, state_updates={"count": 5}, metrics={"sharpe": 1.5})
        updated = mgr.get_branch(branch.branch_id)
        assert updated.state["count"] == 5
        assert updated.metrics["sharpe"] == 1.5

    def test_compare_branches(self):
        mgr = MemoryBranchManager(session_id="test-session")
        b1 = mgr.create_branch("conservative")
        b2 = mgr.create_branch("aggressive")
        mgr.update_branch(b1.branch_id, metrics={"sharpe_ratio": 1.2})
        mgr.update_branch(b2.branch_id, metrics={"sharpe_ratio": 1.8})

        best = mgr.compare_branches(
            [b1.branch_id, b2.branch_id],
            metric="sharpe_ratio",
        )
        assert best.name == "aggressive"

    def test_merge_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("winner", base_state={"strategy": "momentum"})
        result = mgr.merge_branch(branch.branch_id)
        assert result == {"strategy": "momentum"}
        assert mgr.get_branch(branch.branch_id).status == "merged"

    def test_discard_branch(self):
        mgr = MemoryBranchManager(session_id="test-session")
        branch = mgr.create_branch("loser")
        mgr.discard_branch(branch.branch_id)
        assert mgr.get_branch(branch.branch_id).status == "discarded"

    def test_list_branches(self):
        mgr = MemoryBranchManager(session_id="test-session")
        mgr.create_branch("a")
        mgr.create_branch("b")
        b3 = mgr.create_branch("c")
        mgr.discard_branch(b3.branch_id)

        active = mgr.list_branches(status="active")
        assert len(active) == 2
        all_branches = mgr.list_branches()
        assert len(all_branches) == 3


class TestStreaming:
    @pytest.mark.asyncio
    async def test_push_and_get(self):
        buffer = StreamBuffer(session_id="s1", agent_id="test-detector")
        await buffer.push(StreamEventType.PROGRESS, {"step": 1, "total": 5})
        await buffer.push(StreamEventType.COMPLETE, {"result": "done"})

        events = buffer.get_events()
        assert len(events) == 2
        assert events[0].event_type == StreamEventType.PROGRESS
        assert events[1].event_type == StreamEventType.COMPLETE
        assert buffer.is_complete is True

    @pytest.mark.asyncio
    async def test_get_events_after_sequence(self):
        buffer = StreamBuffer(session_id="s1", agent_id="test")
        await buffer.push(StreamEventType.PROGRESS, {"step": 1})
        await buffer.push(StreamEventType.PROGRESS, {"step": 2})
        await buffer.push(StreamEventType.COMPLETE, {})

        events_after_1 = buffer.get_events(after_sequence=1)
        assert len(events_after_1) == 2

    def test_format_sse(self):
        from agent_core.agentcore.streaming import StreamEvent
        event = StreamEvent(
            event_type=StreamEventType.PROGRESS,
            agent_id="test",
            session_id="s1",
            data={"step": 1},
            sequence=1,
        )
        sse = format_sse(event)
        assert sse.startswith("event: progress\n")
        assert "data:" in sse
        assert sse.endswith("\n\n")


class TestMultiTenant:
    def test_tenant_context_defaults(self):
        ctx = TenantContext()
        assert ctx.tenant_id == "default"
        assert ctx.max_entities == 100

    def test_scoped_dynamodb_key(self):
        key = TenantScopedKey.dynamodb_pk("tenant-1", "artifact", "abc123")
        assert "tenant-1" in key
        assert "artifact" in key
        assert "abc123" in key

    def test_scoped_s3_key(self):
        key = TenantScopedKey.s3_key("tenant-1", "reports", "tax_2025.json")
        assert key == "tenants/tenant-1/reports/tax_2025.json"

    def test_scoped_session_id(self):
        sid = TenantScopedKey.session_id("tenant-1", "sfn-exec-abc")
        assert sid == "tenant-1:sfn-exec-abc"

    def test_resource_guard_entity_ok(self):
        ctx = TenantContext(max_entities=100)
        guard = TenantResourceGuard(ctx)
        guard.check_entity_limit(50)  # Should not raise

    def test_resource_guard_entity_exceeded(self):
        ctx = TenantContext(max_entities=100)
        guard = TenantResourceGuard(ctx)
        with pytest.raises(TenantLimitExceeded, match="Entity limit"):
            guard.check_entity_limit(100)

    def test_resource_guard_concurrent_agents(self):
        ctx = TenantContext(max_concurrent_agents=5)
        guard = TenantResourceGuard(ctx)
        with pytest.raises(TenantLimitExceeded, match="Concurrent agent"):
            guard.check_concurrent_agents(5)

    def test_resource_guard_storage(self):
        ctx = TenantContext(max_artifacts_gb=10.0)
        guard = TenantResourceGuard(ctx)
        with pytest.raises(TenantLimitExceeded, match="storage limit"):
            guard.check_artifact_storage(9.5, 1.0)
