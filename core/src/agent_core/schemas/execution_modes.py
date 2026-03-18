"""ExecutionModes schema -- per-mode enablement flags."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExecutionModes(BaseModel):
    """Declares which execution modes an agent or strategy supports."""

    model_config = ConfigDict(frozen=True)

    simulation: bool = True
    staging: bool = False
    production: bool = False
