"""Memory branching for strategy exploration.

Allows agents to create "what-if" branches of their memory state,
explore alternative strategies, and merge or discard branches.
Useful for the Strategy Evaluation agent comparing multiple approaches.

Maps to AgentCore Memory's session branching capability.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MemoryBranch(BaseModel):
    """A branch in the memory tree."""

    branch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_branch_id: str | None = None
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    state: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"  # "active", "merged", "discarded"
    metrics: dict[str, float] = Field(default_factory=dict)


class MemoryBranchManager:
    """Manages memory branches for strategy exploration.

    In POC (Phase 1): branches stored in-memory dict.
    In Production (Phase 2): branches stored in AgentCore Memory with
    session branching API.

    Usage:
        mgr = MemoryBranchManager(session_id="sfn-exec-123")
        branch = mgr.create_branch("aggressive_strategy", base_state={...})
        mgr.update_branch(branch.branch_id, new_state={...})
        best = mgr.compare_branches(["branch-a", "branch-b"], metric="sharpe_ratio")
        mgr.merge_branch(best.branch_id)  # Promote to main
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._branches: dict[str, MemoryBranch] = {}
        self._main_state: dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    def create_branch(
        self,
        name: str,
        base_state: dict[str, Any] | None = None,
        parent_branch_id: str | None = None,
        description: str = "",
    ) -> MemoryBranch:
        """Create a new memory branch.

        Args:
            name: Human-readable branch name (e.g., "conservative_strategy").
            base_state: Initial state (deep-copied). Defaults to main state.
            parent_branch_id: Branch to fork from (None = fork from main).
            description: What this branch explores.

        Returns:
            New MemoryBranch.
        """
        if base_state is None:
            if parent_branch_id and parent_branch_id in self._branches:
                base_state = copy.deepcopy(self._branches[parent_branch_id].state)
            else:
                base_state = copy.deepcopy(self._main_state)

        branch = MemoryBranch(
            parent_branch_id=parent_branch_id,
            name=name,
            description=description,
            state=base_state,
        )

        self._branches[branch.branch_id] = branch
        logger.info(
            "Created memory branch '%s' (id=%s) for session %s",
            name, branch.branch_id, self._session_id,
        )
        return branch

    def update_branch(
        self,
        branch_id: str,
        state_updates: dict[str, Any] | None = None,
        metrics: dict[str, float] | None = None,
    ) -> MemoryBranch:
        """Update a branch's state and/or metrics."""
        branch = self._branches.get(branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")
        if branch.status != "active":
            raise ValueError(f"Branch {branch_id} is {branch.status}, cannot update")

        if state_updates:
            branch.state.update(state_updates)
        if metrics:
            branch.metrics.update(metrics)

        return branch

    def get_branch(self, branch_id: str) -> MemoryBranch | None:
        """Get a branch by ID."""
        return self._branches.get(branch_id)

    def list_branches(self, status: str | None = None) -> list[MemoryBranch]:
        """List all branches, optionally filtered by status."""
        branches = list(self._branches.values())
        if status:
            branches = [b for b in branches if b.status == status]
        return branches

    def compare_branches(
        self,
        branch_ids: list[str],
        metric: str,
        higher_is_better: bool = True,
    ) -> MemoryBranch | None:
        """Compare branches by a specific metric and return the best.

        Args:
            branch_ids: Branch IDs to compare.
            metric: Metric key to compare (e.g., "sharpe_ratio", "max_drawdown").
            higher_is_better: If True, highest metric wins.

        Returns:
            Best branch, or None if no branches have the metric.
        """
        candidates = []
        for bid in branch_ids:
            branch = self._branches.get(bid)
            if branch and metric in branch.metrics:
                candidates.append(branch)

        if not candidates:
            return None

        return max(candidates, key=lambda b: b.metrics[metric]) if higher_is_better else min(candidates, key=lambda b: b.metrics[metric])

    def merge_branch(self, branch_id: str) -> dict[str, Any]:
        """Merge a branch into main state.

        The branch state becomes the new main state.
        Branch is marked as 'merged'.
        """
        branch = self._branches.get(branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")

        self._main_state = copy.deepcopy(branch.state)
        branch.status = "merged"

        logger.info("Merged branch '%s' into main for session %s", branch.name, self._session_id)
        return self._main_state

    def discard_branch(self, branch_id: str) -> None:
        """Discard a branch without merging."""
        branch = self._branches.get(branch_id)
        if branch:
            branch.status = "discarded"
            logger.info("Discarded branch '%s' for session %s", branch.name, self._session_id)
