"""Guardrails, output validation, hallucination filtering, and prompt injection defense."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from reviewer.schemas.models import (
    EvidenceLocation,
    Finding,
    ReviewBundle,
    ReviewStatus,
    Severity,
    SourceRequirement,
)
from reviewer.model.interface import ModelResponse

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"return\s+(status\s+)?pass",
    r"always\s+approve",
    r"bypass\s+review",
    r"override\s+authority",
    r"system\s*:\s*ignore",
]


def detect_adversarial_injection_attempts(bundle: ReviewBundle) -> List[Finding]:
    """Scan bundle text, snippets, and comments for prompt injection attempts."""
    findings: List[Finding] = []

    def _check_text(text: str, loc: EvidenceLocation, context_name: str) -> None:
        for pat in INJECTION_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                findings.append(
                    Finding(
                        finding_id=f"PROMPT_INJECTION_ATTEMPT_{loc.anchor_id or loc.artifact}",
                        severity=Severity.BLOCKER,
                        defect_type="PROMPT_INJECTION_ATTEMPT",
                        artifact_location=loc,
                        supporting_evidence=(
                            f"Adversarial instruction detected in {context_name}: '{text[:80]}...'. "
                            "Instructions in artifacts cannot alter approval authority or reviewer behavior."
                        ),
                        correction="Remove embedded prompt injection or override attempt from artifact content.",
                    )
                )
                break

    for r in bundle.requirements:
        _check_text(r.raw_text, r.evidence_location, f"requirement '{r.id}'")
    for snip in bundle.snippets:
        _check_text(snip.code, snip.evidence_location, f"snippet '{snip.snippet_id}'")

    return findings


def validate_and_reconcile_model_output(
    model_resp: ModelResponse,
    deterministic_findings: List[Finding],
    bundle: ReviewBundle,
    coverage: Dict[str, Any],
) -> Tuple[ReviewStatus, str, List[Finding], Dict[str, Any]]:
    """Validate model report, verify rule citations, guard against hallucinations, and reconcile status.

    Returns:
        Tuple of (reconciled_status, summary, final_findings, check_metadata)
    """
    valid_rule_ids: Set[str] = {r.id for r in bundle.requirements} | {
        s.rule_id for s in bundle.specification
    }
    final_findings: List[Finding] = list(deterministic_findings)
    unreviewed_scope = list(coverage.get("unreviewed_requirements", []))
    check_metadata: Dict[str, Any] = {
        "model_success": model_resp.is_success,
        "model_error": model_resp.error_message,
        "invented_references_detected": 0,
        "injection_attempts_neutralized": 0,
        "provenance": model_resp.provenance.to_dict(),
    }

    # 1. Handle Model Failure (Timeout, Malformed / Truncated JSON)
    if not model_resp.is_success or model_resp.parsed_json is None:
        unreviewed_scope.append({
            "scope": "model_semantic_synthesis",
            "reason": f"Model failed: {model_resp.error_message}",
        })
        summary = (
            f"Deterministic review completed. Model analysis incomplete due to: {model_resp.error_message}."
        )
    else:
        parsed = model_resp.parsed_json
        summary = parsed.get("summary", "Review completed.")
        for unrev in parsed.get("disclosed_unreviewed_scope", []):
            unreviewed_scope.append({"scope": "model_disclosed", "reason": unrev})

        # 2. Validate model findings & Filter invented references
        for raw_f in parsed.get("findings", []):
            rule_ref = raw_f.get("rule_reference")
            if rule_ref and rule_ref not in valid_rule_ids:
                # Hallucination detected
                check_metadata["invented_references_detected"] += 1
                final_findings.append(
                    Finding(
                        finding_id=f"INVENTED_REFERENCE_{rule_ref}",
                        severity=Severity.WARNING,
                        defect_type="INVENTED_RULE_REFERENCE",
                        artifact_location=EvidenceLocation(
                            artifact="model_output",
                            version="1.0",
                            file="model_response.json",
                            anchor_id=rule_ref,
                        ),
                        supporting_evidence=f"Model cited non-existent rule reference '{rule_ref}'.",
                        correction="Disregard hallucinated rule reference.",
                        rule_reference=rule_ref,
                    )
                )
                continue

            # Model findings that are valid can be incorporated as INFO / WARNING
            try:
                model_finding = Finding.from_dict(raw_f)
                final_findings.append(model_finding)
            except Exception:
                continue

    # 3. Status Reconciler:
    # Rule A: Evidenced BLOCKER -> CHANGES_REQUIRED (disclose unreviewed scope)
    has_blocker = any(f.severity == Severity.BLOCKER for f in final_findings)

    # Check for adversarial injection attempts
    injection_findings = detect_adversarial_injection_attempts(bundle)
    if injection_findings:
        check_metadata["injection_attempts_neutralized"] += len(injection_findings)
        final_findings.extend(injection_findings)
        has_blocker = True

    if has_blocker:
        reconciled_status = ReviewStatus.CHANGES_REQUIRED
    elif unreviewed_scope or not model_resp.is_success:
        # Rule B: Missing evidence, ambiguity, or failure prevents full review and no blocker established -> INCOMPLETE
        reconciled_status = ReviewStatus.INCOMPLETE
    else:
        # Rule C: Complete review of effective requirements within declared supported scope and no blocker -> PASS
        reconciled_status = ReviewStatus.PASS

    coverage["unreviewed_requirements"] = unreviewed_scope
    return reconciled_status, summary, final_findings, check_metadata
