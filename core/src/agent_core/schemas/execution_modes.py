"""ExecutionModes schema -- per-mode enablement flags."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

# Domain aliases used in YAML blueprints
_DOMAIN_TO_PLATFORM = {
    "backtest": "simulation",
    "paper": "staging",
    "live": "production",
}


class ExecutionModes(BaseModel):
    """Declares which execution modes an agent or strategy supports."""

    model_config = ConfigDict(frozen=True)

    simulation: bool = True
    staging: bool = False
    production: bool = False

    @model_validator(mode="before")
    @classmethod
    def _resolve_domain_aliases(cls, data: Any) -> Any:
        """Map domain names (backtest/paper/live) to platform names."""
        if not isinstance(data, dict):
            return data
        resolved = dict(data)
        for alias, canonical in _DOMAIN_TO_PLATFORM.items():
            if alias in resolved and canonical not in resolved:
                resolved[canonical] = resolved.pop(alias)
            elif alias in resolved:
                resolved.pop(alias)
        return resolved
