import asyncio
import time
from typing import Any

from django.conf import settings
from openai import OpenAI, AsyncOpenAI, APITimeoutError, RateLimitError, APIError, APIConnectionError, OpenAIError

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
        self._async_client = AsyncOpenAI(api_key=api_key)
        self._default_model = getattr(settings, 'OPENAI_MODEL_DEFAULT', DEFAULT_MODEL)
        self._timeout = getattr(settings, 'LLM_TIMEOUT_S', DEFAULT_TIMEOUT_S)

    @property
    def default_model(self) -> str:
        return self._default_model

    def _uses_completion_tokens_param(self, model: str) -> bool:
        new_api_models = ("gpt-4o", "o1-preview", "o1-mini", "o1", "gpt-5")
        return any(model.startswith(prefix) for prefix in new_api_models)

    def _uses_responses_api(self, model: str) -> bool:
        return model.startswith("gpt-5")

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

        if self._uses_responses_api(model):
            return self._responses_api_call(
                system, user, model, temperature, max_tokens, response_format, start
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "timeout": self._timeout,
        }

        if max_tokens is not None:
            if self._uses_completion_tokens_param(model):
                kwargs["max_completion_tokens"] = max_tokens
            else:
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

    def _responses_api_call(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, Any] | None,
        start: float,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": user,
            "temperature": temperature,
        }

        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens

        if response_format and response_format.get("type") == "json_object":
            kwargs["text"] = {"format": {"type": "json_object"}}

        try:
            response = self._client.responses.create(**kwargs)
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
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            )
        else:
            provider_usage = ProviderUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )

        return ProviderResponse(
            text=response.output_text or "",
            usage=provider_usage,
            response_id=response.id,
            latency_ms=latency_ms,
        )

    async def achat_completion(
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

        if self._uses_responses_api(model):
            return await self._aresponses_api_call(
                system, user, model, temperature, max_tokens, response_format, start
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "timeout": self._timeout,
        }

        if max_tokens is not None:
            if self._uses_completion_tokens_param(model):
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = await self._async_client.chat.completions.create(**kwargs)
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

    async def _aresponses_api_call(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, Any] | None,
        start: float,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": user,
            "temperature": temperature,
        }

        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens

        if response_format and response_format.get("type") == "json_object":
            kwargs["text"] = {"format": {"type": "json_object"}}

        try:
            response = await self._async_client.responses.create(**kwargs)
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
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            )
        else:
            provider_usage = ProviderUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )

        return ProviderResponse(
            text=response.output_text or "",
            usage=provider_usage,
            response_id=response.id,
            latency_ms=latency_ms,
        )
