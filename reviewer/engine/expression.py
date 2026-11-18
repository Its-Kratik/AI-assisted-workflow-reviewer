"""Structured condition expression evaluation and equivalence checks.

Supports:
- Missing values (is_null, is_not_null)
- Numeric comparisons (==, !=, <, <=, >, >=) with inclusive/exclusive boundaries
- Declared time units (minutes, hours, seconds, days)
- Equality and set membership (in, not_in)
- Nested AND / OR / NOT expressions
- Canonical normalization and equivalence testing
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set
from reviewer.schemas.models import Condition, LogicalOp, Operator
from reviewer.engine.units import normalize_numeric_value, are_numeric_conditions_equivalent


def evaluate_condition(cond: Condition, ticket: Dict[str, Any]) -> bool:
    """Evaluate a Condition against a ticket dictionary."""
    if cond.operator == Operator.ALWAYS_TRUE.value or (not cond.field and not cond.conditions and not cond.operator):
        return True

    # Compound boolean operator
    if cond.logical_op:
        op = cond.logical_op.upper()
        if op == LogicalOp.AND.value:
            return all(evaluate_condition(c, ticket) for c in cond.conditions)
        elif op == LogicalOp.OR.value:
            return any(evaluate_condition(c, ticket) for c in cond.conditions)
        elif op == LogicalOp.NOT.value:
            if not cond.conditions:
                return True
            return not evaluate_condition(cond.conditions[0], ticket)
        else:
            raise ValueError(f"Unsupported logical operator: {cond.logical_op}")

    # Atomic condition
    field_name = cond.field
    if field_name is None:
        return True

    ticket_val = ticket.get(field_name)
    target_val = cond.value
    operator = cond.operator

    # Missing value handling
    if operator == Operator.IS_NULL.value or operator == "missing":
        return ticket_val is None
    if operator == Operator.IS_NOT_NULL.value or operator == "exists":
        return ticket_val is not None

    # If ticket_val is None and checking non-null operators
    if ticket_val is None:
        return False

    # Numeric comparison with unit conversion
    if operator in (Operator.LT.value, Operator.LTE.value, Operator.GT.value, Operator.GTE.value):
        try:
            norm_target, _ = normalize_numeric_value(target_val, cond.unit)
            # Ticket values without explicit unit are assumed to be in the standard domain base unit: minutes
            ticket_unit = ticket.get(f"{field_name}_unit") or ("minutes" if cond.unit in ("minutes", "hours", "seconds", "days", "m", "h", "s", "d") else None)
            norm_ticket, _ = normalize_numeric_value(ticket_val, ticket_unit)

            if operator == Operator.LT.value:
                return norm_ticket < norm_target
            elif operator == Operator.LTE.value:
                return norm_ticket <= norm_target
            elif operator == Operator.GT.value:
                return norm_ticket > norm_target
            elif operator == Operator.GTE.value:
                return norm_ticket >= norm_target
        except (ValueError, TypeError):
            return False

    # Equality and set membership
    if operator == Operator.EQ.value:
        return ticket_val == target_val
    elif operator == Operator.NEQ.value:
        return ticket_val != target_val
    elif operator == Operator.IN.value:
        return ticket_val in (target_val if isinstance(target_val, (list, tuple, set)) else [target_val])
    elif operator == Operator.NOT_IN.value:
        return ticket_val not in (target_val if isinstance(target_val, (list, tuple, set)) else [target_val])

    return False


def condition_to_text(cond: Condition) -> str:
    """Human-readable representation of a condition for evidence and reporting."""
    if cond.operator == Operator.ALWAYS_TRUE.value or (not cond.field and not cond.conditions):
        return "True"
    if cond.logical_op:
        sub = [condition_to_text(c) for c in cond.conditions]
        if cond.logical_op == LogicalOp.NOT.value:
            return f"NOT ({sub[0]})" if sub else "NOT ()"
        return f" {cond.logical_op} ".join(f"({s})" for s in sub)

    unit_str = f" {cond.unit}" if cond.unit else ""
    return f"{cond.field} {cond.operator} {cond.value}{unit_str}"


def are_conditions_semantically_equivalent(c1: Condition, c2: Condition) -> bool:
    """Check if two Condition ASTs are semantically equivalent."""
    # Fast path for identical representations
    if c1.to_dict() == c2.to_dict():
        return True

    # Normalize always true
    is_c1_true = (c1.operator == Operator.ALWAYS_TRUE.value) or (not c1.field and not c1.conditions and not c1.logical_op)
    is_c2_true = (c2.operator == Operator.ALWAYS_TRUE.value) or (not c2.field and not c2.conditions and not c2.logical_op)
    if is_c1_true and is_c2_true:
        return True
    if is_c1_true != is_c2_true:
        return False

    # Both are compound
    if c1.logical_op and c2.logical_op:
        if c1.logical_op != c2.logical_op:
            return False
        if len(c1.conditions) != len(c2.conditions):
            return False
        # For commutative ops (AND, OR), match permutations
        if c1.logical_op in (LogicalOp.AND.value, LogicalOp.OR.value):
            matched_indices = set()
            for sub1 in c1.conditions:
                found = False
                for idx, sub2 in enumerate(c2.conditions):
                    if idx not in matched_indices and are_conditions_semantically_equivalent(sub1, sub2):
                        matched_indices.add(idx)
                        found = True
                        break
                if not found:
                    return False
            return True
        elif c1.logical_op == LogicalOp.NOT.value:
            return are_conditions_semantically_equivalent(c1.conditions[0], c2.conditions[0])

    # Both are atomic
    if c1.field and c2.field:
        if c1.field != c2.field:
            return False

        # Missing values
        if c1.operator in (Operator.IS_NULL.value, "missing") and c2.operator in (Operator.IS_NULL.value, "missing"):
            return True
        if c1.operator in (Operator.IS_NOT_NULL.value, "exists") and c2.operator in (Operator.IS_NOT_NULL.value, "exists"):
            return True

        # Numeric comparisons
        if c1.operator in (Operator.LT.value, Operator.LTE.value, Operator.GT.value, Operator.GTE.value):
            return are_numeric_conditions_equivalent(
                c1.operator, c1.value, c1.unit,
                c2.operator, c2.value, c2.unit
            )

        # Equality
        if c1.operator == c2.operator and c1.value == c2.value:
            return True

    return False
