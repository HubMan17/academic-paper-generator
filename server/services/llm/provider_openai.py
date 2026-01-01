import time
from typing import Any

from django.conf import settings
from openai import OpenAI, APITimeoutError, RateLimitError, APIError, APIConnectionError, OpenAIError

from .errors import (
    LLMConfigError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
)
from .types import ProviderResponse, ProviderUsage
from .pricing import DEFAULT_MODEL, DEFAULT_TIMEOUT_S


class OpenAIProvider:
    def __init__(self):
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise LLMConfigError("OPENAI_API_KEY not configured")

        self._client = OpenAI(api_key=api_key)
        self._default_model = getattr(settings, 'OPENAI_MODEL_DEFAULT', DEFAULT_MODEL)
        self._timeout = getattr(settings, 'LLM_TIMEOUT_S', DEFAULT_TIMEOUT_S)

    @property
    def default_model(self) -> str:
        return self._default_model

    def chat_completion(
        self,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        model = model or self._default_model
        start = time.perf_counter()

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "timeout": self._timeout,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = self._client.chat.completions.create(**kwargs)
        except APITimeoutError as e:
            raise LLMTimeoutError(f"Timeout after {self._timeout}s") from e
        except RateLimitError as e:
            raise LLMRateLimitError("Rate limit exceeded") from e
        except APIConnectionError as e:
            raise LLMProviderError(str(e), status_code=None) from e
        except APIError as e:
            raise LLMProviderError(
                str(e),
                status_code=getattr(e, 'status_code', None)
            ) from e
        except OpenAIError as e:
            raise LLMProviderError(str(e), status_code=None) from e

        latency_ms = int((time.perf_counter() - start) * 1000)

        usage = response.usage
        if usage:
            provider_usage = ProviderUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
        else:
            provider_usage = ProviderUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )

        return ProviderResponse(
            text=response.choices[0].message.content or "",
            usage=provider_usage,
            response_id=response.id,
            latency_ms=latency_ms,
        )
