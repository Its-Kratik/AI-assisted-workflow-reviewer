"""Concrete counterexample generation and ticket synthesis.

Synthesizes partition boundaries and combinatorial test tickets to probe:
- Boundary conditions (inclusive vs exclusive >= vs >)
- Missing category / None values
- Urgent flags and precedence inversions
- Interacting rules and priority overrides
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Set, Tuple
from reviewer.schemas.models import (
    Condition,
    EvidenceLocation,
    Finding,
    LinkedPythonSnippet,
    Severity,
    SourceRequirement,
    SpecificationRule,
    WorkflowGraph,
)
from reviewer.engine.expression import evaluate_condition
from reviewer.engine.graph import execute_workflow_route
from reviewer.engine.ast_inspector import get_ast_interpreter
from reviewer.engine.units import normalize_numeric_value


def extract_domain_thresholds(
    requirements: List[SourceRequirement],
    specs: List[SpecificationRule],
    workflow: WorkflowGraph,
) -> Set[float]:
    """Collect all numeric threshold values mentioned across artifacts (normalized to minutes)."""
    thresholds: Set[float] = {0.0, 15.0, 25.0, 30.0, 60.0}

    def _collect_from_cond(cond: Optional[Condition]) -> None:
        if not cond:
            return
        if cond.value is not None and isinstance(cond.value, (int, float)):
            norm_val, _ = normalize_numeric_value(cond.value, cond.unit)
            thresholds.add(norm_val)
        for sub in cond.conditions:
            _collect_from_cond(sub)

    for r in requirements:
        _collect_from_cond(r.condition)
    for s in specs:
        _collect_from_cond(s.condition)
    for b in workflow.branches:
        _collect_from_cond(b.condition)

    return thresholds


def generate_candidate_tickets(
    requirements: List[SourceRequirement],
    specs: List[SpecificationRule],
    workflow: WorkflowGraph,
) -> List[Dict[str, Any]]:
    """Synthesize a finite partition of candidate ticket inputs for exhaustive domain checking."""
    thresholds = extract_domain_thresholds(requirements, specs, workflow)

    # Build numeric values around each threshold to test boundaries
    waiting_times: Set[float] = {0.0}
    for t in thresholds:
        waiting_times.add(max(0.0, t - 5.0))
        waiting_times.add(max(0.0, t - 0.001))
        waiting_times.add(t)
        waiting_times.add(t + 0.001)
        waiting_times.add(t + 5.0)

    categories = [None, "billing", "technical", "urgent_inquiry"]
    urgencies = [False, True]

    tickets: List[Dict[str, Any]] = []
    for cat in categories:
        for urg in urgencies:
            for wt in sorted(waiting_times):
                tickets.append({
                    "category": cat,
                    "urgent": urg,
                    "waiting_time": wt,
                    "waiting_time_minutes": wt,
                })

    return tickets


def evaluate_requirements_route(requirements: List[SourceRequirement], ticket: Dict[str, Any]) -> Tuple[Optional[str], Optional[SourceRequirement]]:
    """Evaluate effective requirements in strict precedence order to determine expected route."""
    for req in sorted(requirements, key=lambda r: r.precedence):
        if evaluate_condition(req.condition, ticket):
            return req.target_route, req
    return None, None


def evaluate_spec_route(specs: List[SpecificationRule], ticket: Dict[str, Any]) -> Tuple[Optional[str], Optional[SpecificationRule]]:
    """Evaluate specification rules in precedence order."""
    for spec in sorted(specs, key=lambda s: s.precedence):
        if evaluate_condition(spec.condition, ticket):
            return spec.target_route, spec
    return None, None


def find_behavioral_counterexamples(
    effective_reqs: List[SourceRequirement],
    specs: List[SpecificationRule],
    workflow: WorkflowGraph,
    snippets: List[LinkedPythonSnippet],
) -> List[Finding]:
    """Exhaustively verify candidate ticket space across all artifacts and return counterexamples."""
    findings: List[Finding] = []
    candidate_tickets = generate_candidate_tickets(effective_reqs, specs, workflow)

    # Prepare AST interpreters for snippets
    interpreters = [(s, get_ast_interpreter(s)) for s in snippets]

    seen_mismatches: Set[str] = set()

    for ticket in candidate_tickets:
        expected_route, matched_req = evaluate_requirements_route(effective_reqs, ticket)
        if not expected_route or not matched_req:
            continue

        req_ref = matched_req.id

        # 1. Check against Specification
        spec_route, matched_spec = evaluate_spec_route(specs, ticket)
        if spec_route != expected_route:
            mismatch_key = f"SPEC_MISMATCH_{req_ref}_{expected_route}_{spec_route}"
            if mismatch_key not in seen_mismatches:
                seen_mismatches.add(mismatch_key)
                loc = matched_spec.evidence_location if matched_spec else effective_reqs[0].evidence_location
                findings.append(
                    Finding(
                        finding_id=f"SPEC_BEHAVIOR_MISMATCH_{req_ref}",
                        severity=Severity.BLOCKER,
                        defect_type="SPECIFICATION_DISAGREEMENT",
                        artifact_location=loc,
                        supporting_evidence=(
                            f"Specification routes ticket to '{spec_route}' but effective requirement "
                            f"'{req_ref}' specifies '{expected_route}'."
                        ),
                        correction=f"Align specification rule precedence/condition with requirement '{req_ref}'.",
                        rule_reference=req_ref,
                        counterexample={
                            "ticket_input": ticket,
                            "expected_route": expected_route,
                            "actual_route": spec_route,
                            "disagreeing_artifact": "specification",
                        },
                    )
                )

        # 2. Check against Workflow Graph
        wf_route, visited_nodes = execute_workflow_route(workflow, ticket)
        if wf_route != expected_route:
            mismatch_key = f"WF_MISMATCH_{req_ref}_{expected_route}_{wf_route}"
            if mismatch_key not in seen_mismatches:
                seen_mismatches.add(mismatch_key)
                findings.append(
                    Finding(
                        finding_id=f"WORKFLOW_BEHAVIOR_MISMATCH_{req_ref}",
                        severity=Severity.BLOCKER,
                        defect_type="WORKFLOW_ROUTE_MISMATCH",
                        artifact_location=workflow.evidence_location,
                        supporting_evidence=(
                            f"Workflow graph routes ticket to '{wf_route}' (visited: {visited_nodes}) "
                            f"but requirement '{req_ref}' requires '{expected_route}'."
                        ),
                        correction=f"Update workflow branch conditions/destinations for rule '{req_ref}'.",
                        rule_reference=req_ref,
                        counterexample={
                            "ticket_input": ticket,
                            "expected_route": expected_route,
                            "actual_route": wf_route,
                            "visited_nodes": visited_nodes,
                            "disagreeing_artifact": "workflow",
                        },
                    )
                )

        # 3. Check against Linked Python Snippets
        for snippet, interp in interpreters:
            if interp is None:
                continue
            script_route = interp.evaluate(ticket)
            if script_route != expected_route:
                mismatch_key = f"SCRIPT_MISMATCH_{snippet.snippet_id}_{req_ref}_{expected_route}_{script_route}"
                if mismatch_key not in seen_mismatches:
                    seen_mismatches.add(mismatch_key)
                    findings.append(
                        Finding(
                            finding_id=f"SCRIPT_DISAGREEMENT_{snippet.snippet_id}_{req_ref}",
                            severity=Severity.BLOCKER,
                            defect_type="SCRIPT_DISAGREEMENT",
                            artifact_location=snippet.evidence_location,
                            supporting_evidence=(
                                f"Script function '{snippet.function_name}' returned '{script_route}' "
                                f"for ticket, expected '{expected_route}' under rule '{req_ref}'."
                            ),
                            correction=f"Fix routing logic in snippet '{snippet.snippet_id}' to match '{req_ref}'.",
                            rule_reference=req_ref,
                            counterexample={
                                "ticket_input": ticket,
                                "expected_route": expected_route,
                                "actual_route": script_route,
                                "disagreeing_artifact": f"script:{snippet.snippet_id}",
                            },
                        )
                    )

    return findings
