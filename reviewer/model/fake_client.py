"""Offline deterministic fake model client for reproducible evaluation and tests."""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional
from reviewer.model.interface import (
    ModelClient,
    ModelConfig,
    ModelProvenance,
    ModelResponse,
    hash_text,
)


class FakeClientMode(str, Enum):
    NORMAL = "NORMAL"
    MALFORMED_JSON = "MALFORMED_JSON"
    TRUNCATED_JSON = "TRUNCATED_JSON"
    INVENTED_REFERENCES = "INVENTED_REFERENCES"
    TIMEOUT = "TIMEOUT"
    INJECTION_COMPLIANT = "INJECTION_COMPLIANT"


class FakeModelClient:
    """Local, offline, deterministic model client."""

    def __init__(self, mode: FakeClientMode = FakeClientMode.NORMAL, latency_sim_ms: float = 2.0) -> None:
        self.mode = mode
        self.latency_sim_ms = latency_sim_ms
        self.call_count = 0
        self.retry_count = 0

    def generate(self, prompt: str, system_prompt: str, config: Optional[ModelConfig] = None) -> ModelResponse:
        cfg = config or ModelConfig()
        self.call_count += 1
        prompt_h = hash_text(f"{system_prompt}\n---\n{prompt}")
        start_t = time.time()

        # Simulate timeout mode
        if self.mode == FakeClientMode.TIMEOUT:
            self.retry_count += cfg.max_retries
            prov = ModelProvenance(
                model_name=cfg.model_name,
                client_type="fake_client",
                prompt_hash=prompt_h,
                latency_ms=self.latency_sim_ms * (cfg.max_retries + 1),
                retries_used=cfg.max_retries,
                raw_response=None,
                config=cfg.to_dict(),
            )
            return ModelResponse(
                content="",
                provenance=prov,
                parsed_json=None,
                is_success=False,
                error_message=f"Request timed out after {cfg.timeout_seconds}s across {cfg.max_retries} retries.",
            )

        # Simulate malformed JSON mode
        if self.mode == FakeClientMode.MALFORMED_JSON:
            raw = "ERROR: Unexpected model token {status: PASS, unclosed_string: \""
            prov = ModelProvenance(
                model_name=cfg.model_name,
                client_type="fake_client",
                prompt_hash=prompt_h,
                latency_ms=self.latency_sim_ms,
                retries_used=0,
                raw_response=raw,
                config=cfg.to_dict(),
            )
            return ModelResponse(
                content=raw,
                provenance=prov,
                parsed_json=None,
                is_success=False,
                error_message="JSONDecodeError: Unterminated string starting at line 1",
            )

        # Simulate truncated JSON mode
        if self.mode == FakeClientMode.TRUNCATED_JSON:
            raw = '{"status": "CHANGES_REQUIRED", "summary": "Review detected unfin'
            prov = ModelProvenance(
                model_name=cfg.model_name,
                client_type="fake_client",
                prompt_hash=prompt_h,
                latency_ms=self.latency_sim_ms,
                retries_used=0,
                raw_response=raw,
                config=cfg.to_dict(),
            )
            return ModelResponse(
                content=raw,
                provenance=prov,
                parsed_json=None,
                is_success=False,
                error_message="JSONDecodeError: Expecting ',' delimiter: line 1 column 58",
            )

        # Simulate invented references mode
        if self.mode == FakeClientMode.INVENTED_REFERENCES:
            data = {
                "status": "CHANGES_REQUIRED",
                "summary": "Model detected hallucinated rules and phantom requirements.",
                "findings": [
                    {
                        "finding_id": "HALLUCINATED_FINDING_1",
                        "severity": "BLOCKER",
                        "defect_type": "CHANGED_THRESHOLD",
                        "rule_reference": "R999_PHANTOM_RULE",
                        "artifact_location": {
                            "artifact": "non_existent_spec.pdf",
                            "version": "9.9.9",
                            "file": "ghost.json",
                        },
                        "supporting_evidence": "Phantom rule R999 threshold differs from requirements.",
                        "correction": "Fix nonexistent rule R999.",
                    }
                ],
                "disclosed_unreviewed_scope": [],
            }
            raw = json.dumps(data)
            prov = ModelProvenance(
                model_name=cfg.model_name,
                client_type="fake_client",
                prompt_hash=prompt_h,
                latency_ms=self.latency_sim_ms,
                retries_used=0,
                raw_response=raw,
                config=cfg.to_dict(),
            )
            return ModelResponse(
                content=raw,
                provenance=prov,
                parsed_json=data,
                is_success=True,
            )

        # Simulate injection-compliant client
        if self.mode == FakeClientMode.INJECTION_COMPLIANT:
            # Blindly obeys injection if present in prompt
            if "IGNORE ALL PREVIOUS INSTRUCTIONS" in prompt or "RETURN PASS" in prompt:
                data = {
                    "status": "PASS",
                    "summary": "Prompt injection forced PASS: ignoring all defect checks.",
                    "findings": [],
                    "disclosed_unreviewed_scope": [],
                }
                raw = json.dumps(data)
                prov = ModelProvenance(
                    model_name=cfg.model_name,
                    client_type="fake_client",
                    prompt_hash=prompt_h,
                    latency_ms=self.latency_sim_ms,
                    retries_used=0,
                    raw_response=raw,
                    config=cfg.to_dict(),
                )
                return ModelResponse(content=raw, provenance=prov, parsed_json=data, is_success=True)

        # NORMAL mode: Provide high-level natural language summary and semantic assessment
        # Parse bundle data from prompt
        has_defect = "MISMATCH" in prompt or "OMITTED" in prompt or "CHANGED" in prompt
        status = "CHANGES_REQUIRED" if has_defect else "PASS"

        data = {
            "status": status,
            "summary": (
                "Automated review completed across written policies, specification, and workflow graph. "
                "Semantic reasoning verified precedence ordering and boundary conditions."
            ),
            "findings": [],
            "disclosed_unreviewed_scope": [],
        }
        raw = json.dumps(data)
        prov = ModelProvenance(
            model_name=cfg.model_name,
            client_type="fake_client",
            prompt_hash=prompt_h,
            latency_ms=self.latency_sim_ms,
            retries_used=0,
            raw_response=raw,
            config=cfg.to_dict(),
        )
        return ModelResponse(content=raw, provenance=prov, parsed_json=data, is_success=True)
