"""Live real model client supporting Gemini / OpenAI APIs via standard library urllib.

Runs purely offline by default if API key is not present, falling back to FakeModelClient.
Labels results explicitly as live vs fake.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from reviewer.model.interface import (
    ModelClient,
    ModelConfig,
    ModelProvenance,
    ModelResponse,
    hash_text,
)


class RealModelClient:
    """Live model client connector using standard library urllib."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        api_type: str = "gemini",  # "gemini" or "openai"
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        self.api_type = api_type
        self.call_count = 0
        self.retry_count = 0

    def generate(self, prompt: str, system_prompt: str, config: Optional[ModelConfig] = None) -> ModelResponse:
        cfg = config or ModelConfig(model_name=self.model_name)
        prompt_h = hash_text(f"{system_prompt}\n---\n{prompt}")

        if not self.api_key:
            # Fallback when offline or no API key provided
            prov = ModelProvenance(
                model_name=cfg.model_name,
                client_type="real_client_unconfigured",
                prompt_hash=prompt_h,
                latency_ms=0.0,
                retries_used=0,
                raw_response=None,
                config=cfg.to_dict(),
            )
            return ModelResponse(
                content="",
                provenance=prov,
                parsed_json=None,
                is_success=False,
                error_message="No API key provided (GEMINI_API_KEY / OPENAI_API_KEY not set). Real model performance was not measured.",
            )

        self.call_count += 1
        start_t = time.time()
        retries = 0

        while retries <= cfg.max_retries:
            try:
                if self.api_type == "gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
                    payload = {
                        "contents": [
                            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}
                        ],
                        "generationConfig": {
                            "temperature": cfg.temperature,
                            "maxOutputTokens": cfg.max_tokens,
                            "responseMimeType": "application/json",
                        },
                    }
                else:
                    # OpenAI compatible endpoint
                    url = "https://api.openai.com/v1/chat/completions"
                    payload = {
                        "model": self.model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": cfg.temperature,
                        "response_format": {"type": "json_object"},
                    }

                req_data = json.dumps(payload).encode("utf-8")
                headers = {"Content-Type": "application/json"}
                if self.api_type != "gemini":
                    headers["Authorization"] = f"Bearer {self.api_key}"

                req = urllib.request.Request(url, data=req_data, headers=headers)
                with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)

                elapsed_ms = (time.time() - start_t) * 1000.0

                # Extract generated text
                if self.api_type == "gemini":
                    content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    content = res_json["choices"][0]["message"]["content"]

                parsed_json = json.loads(content)

                prov = ModelProvenance(
                    model_name=cfg.model_name,
                    client_type="real_client_live",
                    prompt_hash=prompt_h,
                    latency_ms=round(elapsed_ms, 2),
                    retries_used=retries,
                    raw_response=content,
                    config=cfg.to_dict(),
                )
                return ModelResponse(
                    content=content,
                    provenance=prov,
                    parsed_json=parsed_json,
                    is_success=True,
                )

            except Exception as e:
                retries += 1
                self.retry_count += 1
                if retries > cfg.max_retries:
                    elapsed_ms = (time.time() - start_t) * 1000.0
                    prov = ModelProvenance(
                        model_name=cfg.model_name,
                        client_type="real_client_live_failed",
                        prompt_hash=prompt_h,
                        latency_ms=round(elapsed_ms, 2),
                        retries_used=retries - 1,
                        raw_response=None,
                        config=cfg.to_dict(),
                    )
                    return ModelResponse(
                        content="",
                        provenance=prov,
                        parsed_json=None,
                        is_success=False,
                        error_message=f"Live model call failed after {cfg.max_retries} retries: {e}",
                    )
                time.sleep(0.5 * retries)

        return ModelResponse(
            content="",
            provenance=ModelProvenance(model_name=cfg.model_name, client_type="real_client_live_failed", prompt_hash=prompt_h),
            is_success=False,
            error_message="Unknown execution error",
        )
