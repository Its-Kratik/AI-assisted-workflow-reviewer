"""Core Reviewer orchestrator.

Coordinates:
- Content-hash-based cache validation and invalidation
- Stage 1 effective requirements derivation
- Stage 2 deterministic semantic checks & counterexample generation
- Stage 3 model synthesis & guardrail reconciliation
"""

from __future__ import annotations

import json
import time
from typing import Dict, Optional
from reviewer.schemas.models import (
    ReviewBundle,
    ReviewReport,
    ReviewStatus,
)
from reviewer.engine.semantic_checker import run_deterministic_review
from reviewer.model.interface import ModelClient, ModelConfig, hash_text
from reviewer.model.fake_client import FakeModelClient
from reviewer.model.prompt import SYSTEM_PROMPT, build_reviewer_prompt
from reviewer.model.guardrails import validate_and_reconcile_model_output


class WorkflowReviewer:
    """Production-grade AI-assisted workflow reviewer."""

    def __init__(self, model_client: Optional[ModelClient] = None, enable_caching: bool = True) -> None:
        self.model_client = model_client or FakeModelClient()
        self.enable_caching = enable_caching
        self._cache: Dict[str, ReviewReport] = {}

    def compute_bundle_hash(self, bundle: ReviewBundle) -> str:
        """Compute an exact SHA-256 fingerprint across all bundle artifacts."""
        serialized = json.dumps(bundle.to_dict(), sort_keys=True)
        return hash_text(serialized)

    def review(self, bundle: ReviewBundle, config: Optional[ModelConfig] = None) -> ReviewReport:
        """Execute full cumulative review across all stages."""
        bundle_hash = self.compute_bundle_hash(bundle)

        # 1. Caching check: Changed artifacts or approvals must NOT reuse a stale passing report
        if self.enable_caching and bundle_hash in self._cache:
            cached_report = self._cache[bundle_hash]
            cached_report.provenance["cache_hit"] = True
            return cached_report

        start_time = time.time()

        # 2. Stage 1 & 2: Deterministic Semantic Review & Counterexample Synthesis
        deterministic_findings, coverage, effective_reqs = run_deterministic_review(bundle)

        # 3. Stage 3: Model Review Prompt Execution
        prompt = build_reviewer_prompt(bundle)
        model_response = self.model_client.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            config=config,
        )

        # 4. Stage 3: Guardrails, Validation, Hallucination Filter & Reconcile
        status, summary, final_findings, check_meta = validate_and_reconcile_model_output(
            model_resp=model_response,
            deterministic_findings=deterministic_findings,
            bundle=bundle,
            coverage=coverage,
        )

        elapsed_ms = (time.time() - start_time) * 1000.0

        provenance = {
            "bundle_id": bundle.bundle_id,
            "bundle_hash": bundle_hash,
            "runtime_ms": round(elapsed_ms, 2),
            "client_type": getattr(self.model_client, "__class__", type(self.model_client)).__name__,
            "model_metadata": check_meta,
            "effective_rule_count": len(effective_reqs),
            "cache_hit": False,
        }

        check_results = {
            "deterministic_finding_count": len(deterministic_findings),
            "total_finding_count": len(final_findings),
            "blocker_count": sum(1 for f in final_findings if f.severity.value == "BLOCKER"),
            "warning_count": sum(1 for f in final_findings if f.severity.value == "WARNING"),
            "info_count": sum(1 for f in final_findings if f.severity.value == "INFO"),
        }

        report = ReviewReport(
            status=status,
            summary=summary,
            findings=final_findings,
            coverage=coverage,
            check_results=check_results,
            provenance=provenance,
        )

        if self.enable_caching:
            self._cache[bundle_hash] = report

        return report
