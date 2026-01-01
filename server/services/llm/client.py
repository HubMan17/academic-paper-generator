import json
import time
from dataclasses import asdict
from typing import Any

from django.conf import settings
from django.db import IntegrityError

from .provider_openai import OpenAIProvider
from .fingerprint import make_fingerprint
from .limits import check_input_limits
from .cost import estimate_cost
from .retry import sleep_with_backoff
from .types import LLMTextResult, LLMJsonResult, LLMCallMeta, ProviderResponse
from .errors import (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMProviderError,
    LLMInvalidJSONError,
    LLMSchemaValidationError,
)
from .pricing import DEFAULT_MAX_RETRIES

LOCK_POLL_INTERVAL = 0.5
LOCK_TIMEOUT = 30


class LLMClient:
    def __init__(self):
        self._provider = OpenAIProvider()

    def generate_text(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        use_cache: bool = True,
    ) -> LLMTextResult:
        check_input_limits(system, user)

        model_name = model or self._provider.default_model
        params = {"temperature": temperature, "max_tokens": max_tokens}
        fingerprint = make_fingerprint(model_name, system, user, params)

        if use_cache:
            got_lock, existing = self._acquire_lock(fingerprint, model_name)

            if not got_lock:
                result = self._handle_existing_record(existing, fingerprint, model_name)
                if result:
                    return result
                got_lock, _ = self._acquire_lock(fingerprint, model_name)

        try:
            result = self._call_with_retries_text(
                system, user, model_name, temperature, max_tokens, fingerprint
            )
        except Exception as e:
            if use_cache:
                self._mark_failed(fingerprint, str(e))
            raise

        if use_cache:
            self._update_cache_text(fingerprint, result)

        return result

    def generate_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        schema: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> LLMJsonResult:
        check_input_limits(system, user)

        model_name = model or self._provider.default_model
        params = {"temperature": temperature, "max_tokens": max_tokens, "json_mode": True}
        fingerprint = make_fingerprint(model_name, system, user, params, schema)

        if use_cache:
            got_lock, existing = self._acquire_lock(fingerprint, model_name)

            if not got_lock:
                result = self._handle_existing_record_json(existing, fingerprint, model_name)
                if result:
                    return result
                got_lock, _ = self._acquire_lock(fingerprint, model_name)

        try:
            result = self._call_with_retries_json(
                system, user, model_name, temperature, max_tokens, fingerprint, schema
            )
        except Exception as e:
            if use_cache:
                self._mark_failed(fingerprint, str(e))
            raise

        if use_cache:
            self._update_cache_json(fingerprint, result)

        return result

    def _acquire_lock(self, fingerprint: str, model: str) -> tuple[bool, Any]:
        from apps.llm.models import LLMCall

        try:
            LLMCall.objects.create(
                fingerprint=fingerprint,
                model=model,
                status=LLMCall.Status.IN_PROGRESS,
            )
            return True, None
        except IntegrityError:
            existing = LLMCall.objects.get(fingerprint=fingerprint)
            return False, existing

    def _handle_existing_record(
        self,
        existing: Any,
        fingerprint: str,
        model: str
    ) -> LLMTextResult | None:
        from apps.llm.models import LLMCall

        if existing.status == LLMCall.Status.SUCCESS:
            return self._build_cached_text_result(existing)

        if existing.status == LLMCall.Status.IN_PROGRESS:
            result = self._wait_for_result(fingerprint)
            if result and result.status == LLMCall.Status.SUCCESS:
                return self._build_cached_text_result(result)

        existing.delete()
        return None

    def _handle_existing_record_json(
        self,
        existing: Any,
        fingerprint: str,
        model: str
    ) -> LLMJsonResult | None:
        from apps.llm.models import LLMCall

        if existing.status == LLMCall.Status.SUCCESS:
            return self._build_cached_json_result(existing)

        if existing.status == LLMCall.Status.IN_PROGRESS:
            result = self._wait_for_result(fingerprint)
            if result and result.status == LLMCall.Status.SUCCESS:
                return self._build_cached_json_result(result)

        existing.delete()
        return None

    def _wait_for_result(self, fingerprint: str) -> Any:
        from apps.llm.models import LLMCall

        start = time.time()
        while time.time() - start < LOCK_TIMEOUT:
            try:
                record = LLMCall.objects.get(fingerprint=fingerprint)
                if record.status != LLMCall.Status.IN_PROGRESS:
                    return record
            except LLMCall.DoesNotExist:
                return None
            time.sleep(LOCK_POLL_INTERVAL)

        return None

    def _build_cached_text_result(self, record: Any) -> LLMTextResult:
        meta = LLMCallMeta(**record.meta)
        meta.cached = True
        return LLMTextResult(text=record.response_text or "", meta=meta)

    def _build_cached_json_result(self, record: Any) -> LLMJsonResult:
        meta = LLMCallMeta(**record.meta)
        meta.cached = True
        return LLMJsonResult(data=record.response_json or {}, meta=meta)

    def _update_cache_text(self, fingerprint: str, result: LLMTextResult) -> None:
        from apps.llm.models import LLMCall

        LLMCall.objects.filter(fingerprint=fingerprint).update(
            status=LLMCall.Status.SUCCESS,
            response_text=result.text,
            meta=asdict(result.meta),
        )

    def _update_cache_json(self, fingerprint: str, result: LLMJsonResult) -> None:
        from apps.llm.models import LLMCall

        LLMCall.objects.filter(fingerprint=fingerprint).update(
            status=LLMCall.Status.SUCCESS,
            response_json=result.data,
            meta=asdict(result.meta),
        )

    def _mark_failed(self, fingerprint: str, error: str) -> None:
        from apps.llm.models import LLMCall

        LLMCall.objects.filter(fingerprint=fingerprint).update(
            status=LLMCall.Status.FAILED,
            error=error,
        )

    def _call_with_retries_text(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        fingerprint: str,
    ) -> LLMTextResult:
        max_retries = getattr(settings, 'LLM_MAX_RETRIES', DEFAULT_MAX_RETRIES)
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self._provider.chat_completion(
                    system=system,
                    user=user,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return self._build_text_result(response, attempt, fingerprint, system, user)
            except (LLMRateLimitError, LLMTimeoutError) as e:
                last_error = e
                if attempt < max_retries:
                    sleep_with_backoff(attempt)
                continue
            except LLMProviderError as e:
                if not e.is_retryable:
                    raise
                last_error = e
                if attempt < max_retries:
                    sleep_with_backoff(attempt)
                continue

        raise last_error

    def _call_with_retries_json(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        fingerprint: str,
        schema: dict[str, Any] | None,
    ) -> LLMJsonResult:
        max_retries = getattr(settings, 'LLM_MAX_RETRIES', DEFAULT_MAX_RETRIES)
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self._provider.chat_completion(
                    system=system,
                    user=user,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )

                text = self._clean_json_response(response.text)

                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    raise LLMInvalidJSONError(f"Invalid JSON: {e}") from e

                if schema:
                    self._validate_schema(data, schema)

                return self._build_json_result(response, data, attempt, fingerprint, system, user)

            except (LLMRateLimitError, LLMTimeoutError) as e:
                last_error = e
                if attempt < max_retries:
                    sleep_with_backoff(attempt)
                continue
            except LLMProviderError as e:
                if not e.is_retryable:
                    raise
                last_error = e
                if attempt < max_retries:
                    sleep_with_backoff(attempt)
                continue

        raise last_error

    def _build_text_result(
        self,
        response: ProviderResponse,
        attempt: int,
        fingerprint: str,
        system: str,
        user: str,
    ) -> LLMTextResult:
        meta = LLMCallMeta(
            model=response.usage.prompt_tokens and self._provider.default_model,
            latency_ms=response.latency_ms,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            cost_estimate=estimate_cost(
                self._provider.default_model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            ),
            attempts=attempt,
            cached=False,
            fingerprint=fingerprint,
            input_chars=len(system) + len(user),
            output_chars=len(response.text),
        )
        return LLMTextResult(text=response.text, meta=meta)

    def _build_json_result(
        self,
        response: ProviderResponse,
        data: dict[str, Any] | list[Any],
        attempt: int,
        fingerprint: str,
        system: str,
        user: str,
    ) -> LLMJsonResult:
        meta = LLMCallMeta(
            model=self._provider.default_model,
            latency_ms=response.latency_ms,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            cost_estimate=estimate_cost(
                self._provider.default_model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            ),
            attempts=attempt,
            cached=False,
            fingerprint=fingerprint,
            input_chars=len(system) + len(user),
            output_chars=len(response.text),
        )
        return LLMJsonResult(data=data, meta=meta)

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            text = "\n".join(lines)
        return text.strip()

    def _validate_schema(self, data: dict[str, Any] | list[Any], schema: dict[str, Any]) -> None:
        try:
            import jsonschema
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            raise LLMSchemaValidationError(f"Schema validation failed: {e.message}") from e
        except ImportError:
            pass
