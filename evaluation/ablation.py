"""Controlled ablation experiment: reviewer with AST Script Inspector disabled.

Disables linked Python snippet inspection and execution while holding all inputs,
graph checks, unit normalization, and guardrails fixed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List
from reviewer.schemas.models import (
    ReviewBundle,
    ReviewReport,
    ReviewStatus,
    Finding,
    Severity,
)
from reviewer.engine.approvals import derive_effective_requirements
from reviewer.engine.graph import analyze_workflow_graph
from reviewer.engine.counterexample import find_behavioral_counterexamples
from reviewer.engine.expression import are_conditions_semantically_equivalent, condition_to_text
from reviewer.model.fake_client import FakeModelClient
from reviewer.model.prompt import SYSTEM_PROMPT, build_reviewer_prompt
from reviewer.model.guardrails import validate_and_reconcile_model_output


class AblationWorkflowReviewer:
    """Reviewer with AST Script Inspector mechanism deliberately disabled."""

    def __init__(self) -> None:
        self.model_client = FakeModelClient()

    def review(self, bundle: ReviewBundle) -> ReviewReport:
        start_time = time.time()
        findings = []

        # 1. Ambiguous requirements
        for req in bundle.requirements:
            if req.is_ambiguous:
                findings.append(
                    # Warning for unreviewed scope
                    Finding(
                        finding_id=f"AMBIGUOUS_{req.id}",
                        severity=Severity.WARNING,
                        defect_type="AMBIGUOUS_REQUIREMENT",
                        artifact_location=req.evidence_location,
                        supporting_evidence=f"Ambiguous: {req.raw_text}",
                        correction="Clarify.",
                        rule_reference=req.id,
                    )
                )

        # 2. Approvals
        effective_reqs, approval_findings = derive_effective_requirements(
            bundle.requirements, bundle.approvals
        )
        findings.extend(approval_findings)
        reviewable_reqs = [r for r in effective_reqs if not r.is_ambiguous and not r.unsupported_content]

        # 3. [ABLATION] SNIPPET AST INSPECTION IS OMITTED HERE!
        # bundle.snippets are NOT checked for syntax or behavior

        # 4. Graph checks
        findings.extend(analyze_workflow_graph(bundle.workflow))

        # 5. Spec checks
        spec_req_ids = {s.source_requirement_id for s in bundle.specification if s.source_requirement_id}
        spec_by_req = {s.source_requirement_id: s for s in bundle.specification if s.source_requirement_id}

        for req in reviewable_reqs:
            if req.id not in spec_req_ids and not req.is_default:
                findings.append(
                    Finding(
                        finding_id=f"OMITTED_IN_SPEC_{req.id}",
                        severity=Severity.BLOCKER,
                        defect_type="OMITTED_REQUIREMENT",
                        artifact_location=req.evidence_location,
                        supporting_evidence=f"Missing from spec: {req.id}",
                        correction="Add to spec.",
                        rule_reference=req.id,
                    )
                )
            elif req.id in spec_by_req:
                srule = spec_by_req[req.id]
                if srule.target_route != req.target_route:
                    findings.append(
                        Finding(
                            finding_id=f"ROUTE_MISMATCH_{req.id}",
                            severity=Severity.BLOCKER,
                            defect_type="CHANGED_ROUTE",
                            artifact_location=srule.evidence_location,
                            supporting_evidence=f"Route mismatch: {srule.target_route} vs {req.target_route}",
                            correction="Fix route.",
                            rule_reference=req.id,
                        )
                    )
                if not are_conditions_semantically_equivalent(srule.condition, req.condition):
                    findings.append(
                        Finding(
                            finding_id=f"THRESHOLD_MISMATCH_{req.id}",
                            severity=Severity.BLOCKER,
                            defect_type="CHANGED_THRESHOLD",
                            artifact_location=srule.evidence_location,
                            supporting_evidence=f"Condition mismatch: {condition_to_text(srule.condition)}",
                            correction="Fix condition.",
                            rule_reference=req.id,
                        )
                    )

        # 6. Behavioral counterexamples (WITHOUT snippets passed in!)
        if len(reviewable_reqs) == len(effective_reqs):
            findings.extend(
                find_behavioral_counterexamples(
                    effective_reqs=reviewable_reqs,
                    specs=bundle.specification,
                    workflow=bundle.workflow,
                    snippets=[],  # Empty snippets list -> Python code is NOT evaluated!
                )
            )

        coverage = {
            "total_requirements": len(effective_reqs),
            "reviewed_count": len(reviewable_reqs),
            "unreviewed_requirements": [r.id for r in effective_reqs if r.is_ambiguous],
        }

        # Model reconciliation
        prompt = build_reviewer_prompt(bundle)
        mresp = self.model_client.generate(prompt, SYSTEM_PROMPT)
        status, summary, final_findings, meta = validate_and_reconcile_model_output(
            model_resp=mresp,
            deterministic_findings=findings,
            bundle=bundle,
            coverage=coverage,
        )

        elapsed_ms = (time.time() - start_time) * 1000.0
        return ReviewReport(
            status=status,
            summary=summary,
            findings=final_findings,
            coverage=coverage,
            check_results={"blocker_count": sum(1 for f in final_findings if f.severity.value == "BLOCKER")},
            provenance={"runtime_ms": round(elapsed_ms, 2), "client_type": "Ablation_NoScriptInspection"},
        )
