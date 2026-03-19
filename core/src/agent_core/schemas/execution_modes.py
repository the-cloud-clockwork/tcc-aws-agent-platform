"""ExecutionModes schema -- per-mode enablement flags."""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator


class ExecutionModes(BaseModel):
    """Declares which execution modes an agent or strategy supports.

    Domain repos can register custom aliases by setting ``field_aliases``
    before loading blueprints::

        ExecutionModes.field_aliases = {"backtest": "simulation", ...}
    """

    model_config = ConfigDict(frozen=True)

    field_aliases: ClassVar[dict[str, str]] = {}

    simulation: bool = True
    staging: bool = False
    production: bool = False

    @model_validator(mode="before")
    @classmethod
    def _resolve_field_aliases(cls, data: Any) -> Any:
        """Map registered aliases to canonical platform field names."""
        if not isinstance(data, dict) or not cls.field_aliases:
            return data
        resolved = dict(data)
        for alias, canonical in cls.field_aliases.items():
            if alias in resolved and canonical not in resolved:
                resolved[canonical] = resolved.pop(alias)
            elif alias in resolved:
                resolved.pop(alias)
        return resolved
