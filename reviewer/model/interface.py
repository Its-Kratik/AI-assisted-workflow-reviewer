"""Model-client interface, configuration, and provenance structures."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, Protocol


@dataclass
class ModelConfig:
    model_name: str = "fake-model-cpu"
    temperature: float = 0.0
    timeout_seconds: float = 5.0
    max_retries: int = 2
    max_tokens: int = 2048

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelProvenance:
    model_name: str
    client_type: str  # "fake_client", "real_client", "cached"
    prompt_hash: str
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    retries_used: int = 0
    raw_response: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelResponse:
    content: str
    provenance: ModelProvenance
    parsed_json: Optional[Dict[str, Any]] = None
    is_success: bool = True
    error_message: Optional[str] = None


class ModelClient(Protocol):
    """Protocol for model clients (real API or local fake)."""

    def generate(self, prompt: str, system_prompt: str, config: Optional[ModelConfig] = None) -> ModelResponse:
        ...


def hash_text(text: str) -> str:
    """Generate SHA-256 hash for provenance and cache invalidation."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
