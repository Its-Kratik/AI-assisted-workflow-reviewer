"""Deterministic semantic review engine.

Compares effective requirements with specification, reachable workflow paths,
branch destinations, and linked Python code.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
from reviewer.schemas.models import (
    ApprovalRecord,
    Condition,
    EvidenceLocation,
    Finding,
    LinkedPythonSnippet,
    ReviewBundle,
    ReviewReport,
    ReviewStatus,
    Severity,
    SourceRequirement,
    SpecificationRule,
    WorkflowGraph,
)
from reviewer.engine.approvals import derive_effective_requirements
from reviewer.engine.graph import analyze_workflow_graph
from reviewer.engine.ast_inspector import inspect_python_snippet_safety
from reviewer.engine.counterexample import find_behavioral_counterexamples
from reviewer.engine.expression import are_conditions_semantically_equivalent, condition_to_text


def run_deterministic_review(bundle: ReviewBundle) -> Tuple[List[Finding], Dict[str, Any], List[SourceRequirement]]:
    """Execute complete deterministic cross-artifact semantic checks.

    Returns:
        Tuple of (findings_list, coverage_dict, effective_requirements)
    """
    findings: List[Finding] = []

    # 1. Check for Ambiguous or Unsupported Source Content
    for req in bundle.requirements:
        if req.is_ambiguous:
            findings.append(
                Finding(
                    finding_id=f"AMBIGUOUS_REQUIREMENT_{req.id}",
                    severity=Severity.WARNING,  # Incomplete trigger (unreviewed scope)
                    defect_type="AMBIGUOUS_REQUIREMENT",
                    artifact_location=req.evidence_location,
                    supporting_evidence=f"Requirement '{req.id}' is marked ambiguous: {req.ambiguity_reason}",
                    correction="Disclose unreviewed scope or clarify ambiguous requirement text.",
                    rule_reference=req.id,
                )
            )
        if req.unsupported_content:
            findings.append(
                Finding(
                    finding_id=f"UNSUPPORTED_CONTENT_{req.id}",
                    severity=Severity.WARNING,
                    defect_type="UNSUPPORTED_SYNTAX",
                    artifact_location=req.evidence_location,
                    supporting_evidence=f"Requirement '{req.id}' contains unsupported syntax: {req.unsupported_content}",
                    correction="Convert requirement to supported structured condition syntax.",
                    rule_reference=req.id,
                )
            )

    # 2. Derive Effective Requirements & Detect Contradictory Approvals
    effective_reqs, approval_findings = derive_effective_requirements(
        bundle.requirements, bundle.approvals
    )
    findings.extend(approval_findings)

    # Reviewable subset: requirements that are unambiguous and supported
    reviewable_reqs = [r for r in effective_reqs if not r.is_ambiguous and not r.unsupported_content]

    # 3. Check Python Snippet Safety & Restricted Subset
    for snippet in bundle.snippets:
        snippet_findings = inspect_python_snippet_safety(snippet)
        findings.extend(snippet_findings)

    # 4. Check Workflow Graph Topology (Reachability, Dead ends, Entry)
    graph_findings = analyze_workflow_graph(bundle.workflow)
    findings.extend(graph_findings)

    # 5. Check Omitted Requirements (Specification & Workflow coverage)
    spec_req_ids = {s.source_requirement_id for s in bundle.specification if s.source_requirement_id}
    spec_by_req = {s.source_requirement_id: s for s in bundle.specification if s.source_requirement_id}

    for req in reviewable_reqs:
        # Check if omitted in specification
        if req.id not in spec_req_ids and not req.is_default:
            findings.append(
                Finding(
                    finding_id=f"OMITTED_IN_SPEC_{req.id}",
                    severity=Severity.BLOCKER,
                    defect_type="OMITTED_REQUIREMENT",
                    artifact_location=req.evidence_location,  # Omission receives source reference
                    supporting_evidence=f"Effective requirement '{req.id}' ({req.raw_text}) is missing from specification.",
                    correction=f"Add specification rule implementing '{req.id}'.",
                    rule_reference=req.id,
                )
            )
        elif req.id in spec_by_req:
            spec_rule = spec_by_req[req.id]
            # Check route alignment
            if spec_rule.target_route != req.target_route:
                findings.append(
                    Finding(
                        finding_id=f"ROUTE_MISMATCH_SPEC_{req.id}",
                        severity=Severity.BLOCKER,
                        defect_type="CHANGED_ROUTE",
                        artifact_location=spec_rule.evidence_location,
                        supporting_evidence=(
                            f"Spec rule '{spec_rule.rule_id}' routes to '{spec_rule.target_route}', "
                            f"but requirement '{req.id}' specifies '{req.target_route}'."
                        ),
                        correction=f"Update route for '{spec_rule.rule_id}' to '{req.target_route}'.",
                        rule_reference=req.id,
                    )
                )

            # Check condition equivalence directly
            if not are_conditions_semantically_equivalent(spec_rule.condition, req.condition):
                findings.append(
                    Finding(
                        finding_id=f"THRESHOLD_MISMATCH_SPEC_{req.id}",
                        severity=Severity.BLOCKER,
                        defect_type="CHANGED_THRESHOLD",
                        artifact_location=spec_rule.evidence_location,
                        supporting_evidence=(
                            f"Spec rule '{spec_rule.rule_id}' condition ({condition_to_text(spec_rule.condition)}) "
                            f"disagrees with requirement '{req.id}' condition ({condition_to_text(req.condition)})."
                        ),
                        correction=f"Align spec rule condition with effective requirement '{req.id}'.",
                        rule_reference=req.id,
                    )
                )

    # 6. Behavioral Counterexample Synthesis across Finite Domain Partitions
    # Only run behavioral comparison if all requirements are reviewable and unambiguous
    if len(reviewable_reqs) == len(effective_reqs):
        behavioral_findings = find_behavioral_counterexamples(
            effective_reqs=reviewable_reqs,
            specs=bundle.specification,
            workflow=bundle.workflow,
            snippets=bundle.snippets,
        )
        findings.extend(behavioral_findings)

    # Calculate coverage
    total_req_count = len(effective_reqs)
    covered_ids = [r.id for r in effective_reqs if not r.is_ambiguous and not r.unsupported_content]
    unreviewed_ids = [
        {"id": r.id, "reason": r.ambiguity_reason or r.unsupported_content}
        for r in effective_reqs
        if r.is_ambiguous or r.unsupported_content
    ]

    coverage = {
        "total_requirements": total_req_count,
        "reviewed_count": len(covered_ids),
        "covered_requirement_ids": covered_ids,
        "unreviewed_requirements": unreviewed_ids,
        "coverage_percentage": (len(covered_ids) / total_req_count * 100.0) if total_req_count > 0 else 100.0,
    }

    return findings, coverage, effective_reqs
