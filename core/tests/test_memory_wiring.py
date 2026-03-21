"""Tests for agent_core.memory.wiring — MemoryWiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMemoryWiring:
    """Test MemoryWiring construction and property access."""

    @patch("agent_core.memory.wiring.MemoryBranchManager")
    @patch("agent_core.memory.wiring.MemoryHookProvider")
    @patch("agent_core.memory.wiring.MemoryManager")
    def test_construction(
        self,
        mock_manager_cls: MagicMock,
        mock_hook_cls: MagicMock,
        mock_branch_cls: MagicMock,
    ) -> None:
        from agent_core.schemas.memory_config import MemoryConfig

        config = MemoryConfig(
            strategies=[{"name": "s1", "type": "SUMMARY"}],
        )

        from agent_core.memory.wiring import MemoryWiring

        wiring = MemoryWiring(
            config=config,
            memory_id="mem-123",
            region="us-west-2",
        )
        assert wiring.memory_id == "mem-123"
        assert wiring.config is config
        mock_manager_cls.assert_called_once_with(region="us-west-2")

    @patch("agent_core.memory.wiring.MemoryBranchManager")
    @patch("agent_core.memory.wiring.MemoryHookProvider")
    @patch("agent_core.memory.wiring.MemoryManager")
    def test_properties(
        self,
        mock_manager_cls: MagicMock,
        mock_hook_cls: MagicMock,
        mock_branch_cls: MagicMock,
    ) -> None:
        from agent_core.schemas.memory_config import MemoryConfig

        config = MemoryConfig(strategies=[{"name": "s1", "type": "SUMMARY"}])

        from agent_core.memory.wiring import MemoryWiring

        wiring = MemoryWiring(config=config, memory_id="mem-1")
        assert wiring.manager is not None
        assert wiring.hook_provider is not None
        assert wiring.branching is not None

    @patch("agent_core.memory.wiring.MemoryBranchManager")
    @patch("agent_core.memory.wiring.MemoryHookProvider")
    @patch("agent_core.memory.wiring.MemoryManager")
    def test_tool_provider_disabled(
        self,
        mock_manager_cls: MagicMock,
        mock_hook_cls: MagicMock,
        mock_branch_cls: MagicMock,
    ) -> None:
        from agent_core.schemas.memory_config import MemoryConfig

        config = MemoryConfig(
            strategies=[{"name": "s1", "type": "SUMMARY"}],
            enable_tool_provider=False,
        )

        from agent_core.memory.wiring import MemoryWiring

        wiring = MemoryWiring(config=config, memory_id="mem-1")
        tools = wiring.get_tool_provider_tools(actor_id="a1", session_id="s1")
        assert tools == []
