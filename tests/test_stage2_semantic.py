"""Stage 2 tests: Deterministic semantic checks, graph traversal, AST evaluation, and counterexamples."""

import unittest
from reviewer.schemas.models import (
    Condition,
    EvidenceLocation,
    LinkedPythonSnippet,
    Operator,
    SourceRequirement,
    SpecificationRule,
    TimeUnit,
    WorkflowBranch,
    WorkflowGraph,
    WorkflowNode,
)
from reviewer.engine.graph import analyze_workflow_graph, execute_workflow_route
from reviewer.engine.ast_inspector import inspect_python_snippet_safety, get_ast_interpreter
from reviewer.engine.counterexample import find_behavioral_counterexamples


class TestStage2Semantic(unittest.TestCase):
    def test_workflow_graph_dead_end_and_unreachable(self):
        nodes = {
            "start": WorkflowNode("start", "decision", EvidenceLocation("wf", "1", "w.json", 1)),
            "dead_node": WorkflowNode("dead_node", "decision", EvidenceLocation("wf", "1", "w.json", 2)),
            "orphan": WorkflowNode("orphan", "terminal", EvidenceLocation("wf", "1", "w.json", 3), action_route="queue"),
        }
        branches = [
            WorkflowBranch("b1", "start", "dead_node", 1, EvidenceLocation("wf", "1", "w.json", 4)),
        ]
        wf = WorkflowGraph("1.0", "start", nodes, branches, EvidenceLocation("wf", "1", "w.json", 1))
        findings = analyze_workflow_graph(wf)

        types = [f.defect_type for f in findings]
        self.assertIn("UNREACHABLE_WORKFLOW_NODE", types)
        self.assertIn("DEAD_END_WORKFLOW_NODE", types)

    def test_safe_ast_interpreter_disagreement(self):
        code_buggy = """def route_ticket(ticket):
    if ticket.get("urgent") is True:
        return "normal queue"  # Bug: should be priority queue
    return "normal queue"
"""
        snip = LinkedPythonSnippet("snip1", "1.0", "route_ticket", code_buggy, EvidenceLocation("script", "1", "r.py", 1))
        findings = inspect_python_snippet_safety(snip)
        self.assertEqual(len(findings), 0)  # Valid syntax

        interp = get_ast_interpreter(snip)
        self.assertIsNotNone(interp)
        res = interp.evaluate({"urgent": True})
        self.assertEqual(res, "normal queue")

    def test_counterexample_synthesis(self):
        reqs = [
            SourceRequirement("R2", "p2", "1.0", 1, Condition("urgent", Operator.EQ.value, True), "priority queue", "urgent -> priority", EvidenceLocation("req", "1", "r.md", 1)),
            SourceRequirement("R_def", "p3", "1.0", 2, Condition.always_true(), "normal queue", "default normal", EvidenceLocation("req", "1", "r.md", 2), is_default=True),
        ]
        specs = [
            # Specification has buggy route
            SpecificationRule("SPEC-R2", "1.0", 1, Condition("urgent", Operator.EQ.value, True), "normal queue", EvidenceLocation("spec", "1", "s.json", 1), source_requirement_id="R2"),
            SpecificationRule("SPEC-DEF", "1.0", 2, Condition.always_true(), "normal queue", EvidenceLocation("spec", "1", "s.json", 2), source_requirement_id="R_def"),
        ]
        wf = WorkflowGraph("1.0", "term_normal", {"term_normal": WorkflowNode("term_normal", "terminal", EvidenceLocation("wf", "1", "w.json", 1), action_route="normal queue")}, [], EvidenceLocation("wf", "1", "w.json", 1))
        findings = find_behavioral_counterexamples(reqs, specs, wf, [])
        self.assertTrue(len(findings) > 0)
        ce_finding = next(f for f in findings if f.counterexample)
        self.assertEqual(ce_finding.counterexample["expected_route"], "priority queue")
        self.assertEqual(ce_finding.counterexample["actual_route"], "normal queue")
        self.assertEqual(ce_finding.counterexample["ticket_input"]["urgent"], True)


if __name__ == "__main__":
    unittest.main()
