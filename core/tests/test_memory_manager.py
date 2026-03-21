"""Tests for agent_core.memory.manager — MemoryManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMemoryManager:
    """Test MemoryManager construction and method dispatch."""

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("agent_core.memory.manager.Memory")
    def test_construction_with_env_region(self, mock_memory_cls: MagicMock) -> None:
        from agent_core.memory.manager import MemoryManager

        mgr = MemoryManager()
        assert mgr is not None
        mock_memory_cls.assert_called_once()

    @patch("agent_core.memory.manager.Memory")
    def test_construction_with_explicit_region(
        self, mock_memory_cls: MagicMock
    ) -> None:
        from agent_core.memory.manager import MemoryManager

        mgr = MemoryManager(region="eu-west-1")
        assert mgr is not None

    def test_construction_missing_region_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch("agent_core.memory.manager.Memory"):
                from agent_core.memory.manager import MemoryManager

                with pytest.raises(Exception):
                    MemoryManager()

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("agent_core.memory.manager.Memory")
    def test_create_event(self, mock_memory_cls: MagicMock) -> None:
        from agent_core.memory.manager import MemoryManager

        mock_client = MagicMock()
        mock_memory_cls.return_value = mock_client

        mgr = MemoryManager()
        mgr.create_event(
            memory_id="mem-1",
            actor_id="actor-1",
            session_id="sess-1",
            messages=[("user", "hello"), ("assistant", "hi")],
        )
        mock_client.create_event.assert_called_once()

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("agent_core.memory.manager.Memory")
    def test_get_last_k_turns(self, mock_memory_cls: MagicMock) -> None:
        from agent_core.memory.manager import MemoryManager

        mock_client = MagicMock()
        mock_client.get_last_k_turns.return_value = [{"role": "user", "content": "hi"}]
        mock_memory_cls.return_value = mock_client

        mgr = MemoryManager()
        turns = mgr.get_last_k_turns(
            memory_id="mem-1", actor_id="actor-1", session_id="sess-1", k=3
        )
        assert len(turns) == 1

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("agent_core.memory.manager.Memory")
    def test_retrieve_memories(self, mock_memory_cls: MagicMock) -> None:
        from agent_core.memory.manager import MemoryManager

        mock_client = MagicMock()
        mock_client.retrieve_memories.return_value = []
        mock_memory_cls.return_value = mock_client

        mgr = MemoryManager()
        results = mgr.retrieve_memories(
            memory_id="mem-1", namespace="ns", query="test query"
        )
        assert isinstance(results, list)
