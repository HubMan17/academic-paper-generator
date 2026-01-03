import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from services.llm.client import LLMClient
from services.llm.types import ProviderResponse, ProviderUsage
from services.llm.errors import (
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
)


@pytest.fixture
def mock_settings():
    with patch('services.llm.client.settings') as mock:
        mock.LLM_MAX_RETRIES = 3
        mock.LLM_TIMEOUT_S = 60
        yield mock


@pytest.fixture
def mock_provider():
    with patch('services.llm.client.OpenAIProvider') as mock:
        provider = MagicMock()
        provider.default_model = 'gpt-4o-mini'
        mock.return_value = provider
        yield provider


@pytest.fixture
def mock_sleep():
    with patch('services.llm.client.sleep_with_backoff') as mock:
        yield mock


def create_response(text: str = "test response") -> ProviderResponse:
    return ProviderResponse(
        text=text,
        usage=ProviderUsage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        response_id="test-id",
        latency_ms=100,
    )


class TestClientRetry:
    def test_no_retry_on_success(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.return_value = create_response()

        client = LLMClient()
        result = client.generate_text("sys", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 1
        assert mock_sleep.call_count == 0
        assert result.text == "test response"

    def test_retry_on_timeout(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.side_effect = [
            LLMTimeoutError("timeout"),
            LLMTimeoutError("timeout"),
            create_response("success after retry"),
        ]

        client = LLMClient()
        result = client.generate_text("sys", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 3
        assert mock_sleep.call_count == 2
        assert result.text == "success after retry"
        assert result.meta.attempts == 3

    def test_retry_on_rate_limit(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.side_effect = [
            LLMRateLimitError("rate limit"),
            create_response("success"),
        ]

        client = LLMClient()
        result = client.generate_text("sys", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 2
        assert mock_sleep.call_count == 1
        assert result.text == "success"
        assert result.meta.attempts == 2

    def test_retry_on_retryable_provider_error(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.side_effect = [
            LLMProviderError("server error", status_code=500),
            create_response("success"),
        ]

        client = LLMClient()
        result = client.generate_text("sys", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 2
        assert result.text == "success"

    def test_no_retry_on_non_retryable_error(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.side_effect = LLMProviderError("bad request", status_code=400)

        client = LLMClient()

        with pytest.raises(LLMProviderError) as exc_info:
            client.generate_text("sys", "user", use_cache=False)

        assert exc_info.value.status_code == 400
        assert mock_provider.chat_completion.call_count == 1
        assert mock_sleep.call_count == 0

    def test_raises_after_max_retries(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.side_effect = LLMTimeoutError("timeout")

        client = LLMClient()

        with pytest.raises(LLMTimeoutError):
            client.generate_text("sys", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 3
        assert mock_sleep.call_count == 2


class TestClientRetryJson:
    def test_retry_on_timeout_json(self, mock_settings, mock_provider, mock_sleep):
        mock_provider.chat_completion.side_effect = [
            LLMTimeoutError("timeout"),
            create_response('{"key": "value"}'),
        ]

        client = LLMClient()
        result = client.generate_json("sys", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 2
        assert result.data == {"key": "value"}
        assert result.meta.attempts == 2
