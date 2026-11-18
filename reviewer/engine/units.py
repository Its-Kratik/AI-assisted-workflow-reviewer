"""Unit normalization and boundary utilities."""

from __future__ import annotations

from typing import Any, Optional, Tuple
from reviewer.schemas.models import TimeUnit


def normalize_numeric_value(value: Any, unit: Optional[str] = None) -> Tuple[float, Optional[str]]:
    """Convert numeric value with declared time units to standard unit (minutes)."""
    if value is None:
        return 0.0, None
    try:
        fval = float(value)
    except (ValueError, TypeError):
        return 0.0, unit

    if unit:
        u = unit.lower().strip()
        if u in ("s", "sec", "second", "seconds"):
            return fval / 60.0, "minutes"
        elif u in ("m", "min", "minute", "minutes"):
            return fval, "minutes"
        elif u in ("h", "hr", "hour", "hours"):
            return fval * 60.0, "minutes"
        elif u in ("d", "day", "days"):
            return fval * 1440.0, "minutes"
    return fval, unit


def are_numeric_conditions_equivalent(
    op1: str, val1: Any, unit1: Optional[str],
    op2: str, val2: Any, unit2: Optional[str]
) -> bool:
    """Check if two numeric comparison conditions are semantically equivalent."""
    norm_val1, norm_unit1 = normalize_numeric_value(val1, unit1)
    norm_val2, norm_unit2 = normalize_numeric_value(val2, unit2)

    # Unit types must be compatible if specified
    if norm_unit1 != norm_unit2:
        return False

    if op1 != op2:
        return False

    return abs(norm_val1 - norm_val2) < 1e-6
