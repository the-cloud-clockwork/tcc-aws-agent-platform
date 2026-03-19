"""Safe condition expression parser.

Parses simple ``"field op value"`` expressions into safe callables.
No ``eval()`` — only operator-based comparisons.

Examples::

    parse_condition("status == success")
    parse_condition("score >= 0.7")
    parse_condition("result.matched == true")
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Any

OPERATORS: dict[str, Callable[..., bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}

_BOOL_LITERALS = {"true": True, "false": False, "none": None}


def _coerce_value(raw: str) -> int | float | bool | str | None:
    """Coerce a string token into a typed Python value."""
    lower = raw.lower()
    if lower in _BOOL_LITERALS:
        return _BOOL_LITERALS[lower]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    # Strip surrounding quotes if present
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return raw[1:-1]
    return raw


def _resolve_attr(obj: Any, dotted_path: str) -> Any:
    """Resolve a dotted attribute path on an object or dict."""
    current = obj
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def parse_condition(expr: str) -> Callable[[Any], bool]:
    """Parse ``'field op value'`` into a safe callable.

    Parameters
    ----------
    expr:
        Expression string, e.g. ``"status == success"``,
        ``"score >= 0.7"``, ``"result.matched == true"``.

    Returns
    -------
    A callable that takes a single argument (state/dict) and
    returns ``True``/``False``.

    Raises
    ------
    ValueError
        If the expression cannot be parsed or uses an unknown operator.
    """
    parts = expr.strip().split(None, 2)  # max 3 tokens
    if len(parts) != 3:
        raise ValueError(
            f"Condition must be 'field op value', got {len(parts)} tokens: {expr!r}"
        )

    field, op_str, raw_value = parts

    if op_str not in OPERATORS:
        raise ValueError(f"Unknown operator {op_str!r} in condition: {expr!r}")

    op_fn = OPERATORS[op_str]
    expected = _coerce_value(raw_value)

    def _check(state: Any) -> bool:
        actual = _resolve_attr(state, field)
        if actual is None:
            return False
        try:
            return bool(op_fn(actual, expected))
        except (TypeError, ValueError):
            return False

    return _check
