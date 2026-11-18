"""Effective requirements derivation and approval conflict detection.

Rules:
- Top-level approval metadata (approved=True) is trusted.
- Approval claims inside prose or raw_text are ignored / untrusted.
- Detect contradictory approval records without silently choosing a convenient version.
- Preserve revision scope, ordering, and evidence locations.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple
from reviewer.schemas.models import (
    ApprovalRecord,
    Condition,
    EvidenceLocation,
    Finding,
    Severity,
    SourceRequirement,
)


def derive_effective_requirements(
    base_requirements: List[SourceRequirement],
    approvals: List[ApprovalRecord],
) -> Tuple[List[SourceRequirement], List[Finding]]:
    """Derive effective requirements from base requirements and approvals.

    Returns:
        Tuple of (effective_requirements_list, findings_list)
        If contradictory approvals exist, an INCOMPLETE/BLOCKER finding is generated.
    """
    effective_reqs: Dict[str, SourceRequirement] = {
        r.id: copy.deepcopy(r) for r in base_requirements
    }
    findings: List[Finding] = []

    # Group approvals by target_rule_id
    approvals_by_rule: Dict[str, List[ApprovalRecord]] = {}
    for app in approvals:
        approvals_by_rule.setdefault(app.target_rule_id, []).append(app)

    for rule_id, app_list in approvals_by_rule.items():
        if rule_id not in effective_reqs:
            findings.append(
                Finding(
                    finding_id=f"UNKNOWN_TARGET_RULE_{rule_id}",
                    severity=Severity.BLOCKER,
                    defect_type="UNKNOWN_RULE_APPROVAL",
                    artifact_location=app_list[0].evidence_location,
                    supporting_evidence=f"Approval {app_list[0].change_id} targets non-existent rule '{rule_id}'.",
                    correction=f"Verify target_rule_id in approval {app_list[0].change_id}.",
                    rule_reference=rule_id,
                )
            )
            continue

        # Check for contradictory approvals
        approved_changes = [a for a in app_list if a.approved is True]
        unapproved_changes = [a for a in app_list if a.approved is False]

        # Case 1: Contradictory approvals (e.g. one approved=True and another approved=False for same revision,
        # or two approved changes with conflicting thresholds/targets at same precedence)
        if len(approved_changes) > 1:
            # Check if they conflict in proposed condition or route
            c0 = approved_changes[0]
            conflicts = []
            for c_other in approved_changes[1:]:
                cond_conflict = (
                    c0.proposed_condition is not None
                    and c_other.proposed_condition is not None
                    and c0.proposed_condition.to_dict() != c_other.proposed_condition.to_dict()
                )
                route_conflict = (
                    c0.proposed_route is not None
                    and c_other.proposed_route is not None
                    and c0.proposed_route != c_other.proposed_route
                )
                if cond_conflict or route_conflict:
                    conflicts.append((c0, c_other))

            if conflicts:
                findings.append(
                    Finding(
                        finding_id=f"CONTRADICTORY_APPROVAL_{rule_id}",
                        severity=Severity.WARNING,
                        defect_type="CONTRADICTORY_APPROVAL_RECORDS",
                        artifact_location=conflicts[0][1].evidence_location,
                        supporting_evidence=(
                            f"Contradictory approved changes detected for rule '{rule_id}': "
                            f"{conflicts[0][0].change_id} vs {conflicts[0][1].change_id}. "
                            "Cannot silently pick a convenient version."
                        ),
                        correction="Resolve contradictory approval records before deploying.",
                        rule_reference=rule_id,
                    )
                )
                target_req = effective_reqs[rule_id]
                target_req.is_ambiguous = True
                target_req.ambiguity_reason = (
                    f"Contradictory approvals: {conflicts[0][0].change_id} vs {conflicts[0][1].change_id}"
                )
                continue

        # Sort approved changes chronologically by timestamp
        approved_changes.sort(key=lambda a: a.timestamp)

        # Apply each approved change
        for app in approved_changes:
            target_req = effective_reqs[rule_id]
            if app.proposed_condition is not None:
                target_req.condition = app.proposed_condition
            if app.proposed_route is not None:
                target_req.target_route = app.proposed_route
            if app.proposed_precedence is not None:
                target_req.precedence = app.proposed_precedence
            # Update evidence location to link to the approval
            target_req.version = f"{target_req.version}+rev_{app.change_id}"

    # Return sorted by precedence
    sorted_effective = sorted(effective_reqs.values(), key=lambda r: r.precedence)
    return sorted_effective, findings
