from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMCallMeta:
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_estimate: float = 0.0
    attempts: int = 1
    cached: bool = False
    fingerprint: str = ""
    input_chars: int = 0
    output_chars: int = 0
    error_type: str | None = None
    provider_status: int | None = None


@dataclass
class LLMTextResult:
    text: str
    meta: LLMCallMeta


@dataclass
class LLMJsonResult:
    data: dict[str, Any] | list[Any]
    meta: LLMCallMeta


@dataclass
class ProviderUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ProviderResponse:
    text: str
    usage: ProviderUsage
    response_id: str | None = None
    latency_ms: int = 0
