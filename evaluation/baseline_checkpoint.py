"""Preserved initial working checkpoint of the reviewer (Baseline).

Characteristics of initial checkpoint:
- Simple metadata & rule ID matching.
- No unit normalization (e.g. 0.5 hours treated as mismatch against 30 minutes).
- No workflow graph traversal / path reachability check.
- No AST inspection of linked Python scripts.
- No combinatorial ticket input synthesis / counterexample generation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List
from reviewer.schemas.models import (
    EvidenceLocation,
    Finding,
    ReviewBundle,
    ReviewReport,
    ReviewStatus,
    Severity,
)


class BaselineWorkflowReviewer:
    """Initial working checkpoint implementation."""

    def review(self, bundle: ReviewBundle) -> ReviewReport:
        start_time = time.time()
        findings: List[Finding] = []

        # Simple ID and string matching
        spec_rule_map = {s.source_requirement_id: s for s in bundle.specification if s.source_requirement_id}
        spec_rule_ids = set(spec_rule_map.keys())

        # Check for omissions purely by ID
        for req in bundle.requirements:
            if req.is_ambiguous:
                findings.append(
                    Finding(
                        finding_id=f"AMBIGUOUS_{req.id}",
                        severity=Severity.WARNING,
                        defect_type="AMBIGUOUS_REQUIREMENT",
                        artifact_location=req.evidence_location,
                        supporting_evidence=f"Ambiguous requirement: {req.raw_text}",
                        correction="Clarify requirement.",
                        rule_reference=req.id,
                    )
                )
                continue

            if req.id not in spec_rule_ids and not req.is_default:
                findings.append(
                    Finding(
                        finding_id=f"OMITTED_{req.id}",
                        severity=Severity.BLOCKER,
                        defect_type="OMITTED_REQUIREMENT",
                        artifact_location=req.evidence_location,
                        supporting_evidence=f"Rule {req.id} not found in spec.",
                        correction="Add rule to spec.",
                        rule_reference=req.id,
                    )
                )
            elif req.id in spec_rule_map:
                spec_rule = spec_rule_map[req.id]
                # Literal value match (fails on unit conversion 0.5h != 30m)
                if spec_rule.condition.value != req.condition.value:
                    findings.append(
                        Finding(
                            finding_id=f"VALUE_MISMATCH_{req.id}",
                            severity=Severity.BLOCKER,
                            defect_type="CHANGED_THRESHOLD",
                            artifact_location=spec_rule.evidence_location,
                            supporting_evidence=f"Literal value mismatch: {spec_rule.condition.value} vs {req.condition.value}",
                            correction="Align literal value.",
                            rule_reference=req.id,
                        )
                    )

        # Baseline does NOT traverse workflow graph or execute AST scripts!
        has_blocker = any(f.severity == Severity.BLOCKER for f in findings)
        has_warning = any(f.severity == Severity.WARNING for f in findings)

        if has_blocker:
            status = ReviewStatus.CHANGES_REQUIRED
        elif has_warning:
            status = ReviewStatus.INCOMPLETE
        else:
            status = ReviewStatus.PASS

        elapsed_ms = (time.time() - start_time) * 1000.0
        return ReviewReport(
            status=status,
            summary="Baseline review completed using simple ID and literal attribute matching.",
            findings=findings,
            coverage={"total_requirements": len(bundle.requirements), "reviewed_count": len(bundle.requirements)},
            check_results={"blocker_count": sum(1 for f in findings if f.severity == Severity.BLOCKER)},
            provenance={"runtime_ms": round(elapsed_ms, 2), "client_type": "BaselineCheckpoint"},
        )
