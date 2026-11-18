"""Preserved debugging examples and regression tests.

Records:
1. Python class-scope attribute shadowing bug (field: Optional[str] shadowing dataclasses.field)
2. Ticket unit normalization default bug (unspecified ticket unit inheriting condition unit 'hours')
3. Restricted AST inspection bug (.get() method and Assign omitted from supported grammar)
"""

import unittest
from reviewer.schemas.models import Condition, Operator, SourceRequirement, EvidenceLocation
from reviewer.engine.expression import evaluate_condition
from reviewer.engine.ast_inspector import inspect_python_snippet_safety, get_ast_interpreter
from reviewer.schemas.models import LinkedPythonSnippet


class TestDebuggingRegressions(unittest.TestCase):
    def test_regression_1_dataclass_attribute_shadowing(self):
        """Regression 1: Ensure Condition class instantiation does not fail due to 'field' shadowing."""
        # Prior to fix: `conditions: List[Condition] = field(default_factory=list)` failed with
        # TypeError: 'NoneType' object is not callable because `field: Optional[str] = None` shadowed dataclasses.field.
        c = Condition(field="category", operator=Operator.IS_NULL.value)
        self.assertEqual(c.field, "category")
        self.assertEqual(len(c.conditions), 0)

        # Compound condition instantiation
        c_compound = Condition(
            logical_op="AND",
            conditions=[Condition(field="urgent", operator=Operator.EQ.value, value=True)]
        )
        self.assertEqual(len(c_compound.conditions), 1)

    def test_regression_2_unit_normalization_ticket_default(self):
        """Regression 2: Unspecified ticket waiting_time must default to minutes, not inherit condition unit.

        Prior to fix: evaluate_condition used:
            ticket_unit = ticket.get(f"{field_name}_unit") or (cond.unit if cond.unit else None)
        When cond.unit was 'hours' (0.5 hours = 30 minutes) and ticket had waiting_time=0.999 (minutes),
        ticket_unit became 'hours' -> 0.999 * 60 = 59.94 minutes >= 30 minutes -> false match!
        """
        cond_hours = Condition(field="waiting_time", operator=Operator.GTE.value, value=0.5, unit="hours")

        # Ticket with waiting_time = 0.999 minutes (clearly < 30 minutes)
        ticket_minutes = {"waiting_time": 0.999}
        self.assertFalse(evaluate_condition(cond_hours, ticket_minutes))

        # Ticket with waiting_time = 35 minutes (>= 30 minutes)
        ticket_escalation = {"waiting_time": 35.0}
        self.assertTrue(evaluate_condition(cond_hours, ticket_escalation))

    def test_regression_3_ast_dict_get_and_assignment(self):
        """Regression 3: Ensure restricted Python subset allows ticket.get() and assignment statements.

        Prior to fix: AST validator rejected ast.Call and ast.Assign as unsupported,
        and interpreter failed to evaluate ticket.get("category"), defaulting to None
        and causing false script disagreement for all tickets.
        """
        code = """def route_ticket(ticket):
    cat = ticket.get("category")
    if cat is None:
        return "manual review"
    if ticket.get("urgent") is True:
        return "priority queue"
    wt = ticket.get("waiting_time", 0.0)
    if wt >= 30:
        return "escalation"
    return "normal queue"
"""
        snip = LinkedPythonSnippet("test_snip", "1.0", "route_ticket", code, EvidenceLocation("script", "1", "t.py", 1))
        findings = inspect_python_snippet_safety(snip)
        self.assertEqual(len(findings), 0, "Valid snippet must not have safety violations")

        interp = get_ast_interpreter(snip)
        self.assertIsNotNone(interp)
        # Test routing cases
        self.assertEqual(interp.evaluate({"category": None}), "manual review")
        self.assertEqual(interp.evaluate({"category": "billing", "urgent": True}), "priority queue")
        self.assertEqual(interp.evaluate({"category": "billing", "urgent": False, "waiting_time": 35}), "escalation")
        self.assertEqual(interp.evaluate({"category": "billing", "urgent": False, "waiting_time": 10}), "normal queue")


if __name__ == "__main__":
    unittest.main()
