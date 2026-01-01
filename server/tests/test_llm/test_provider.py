import pytest
from unittest.mock import Mock, patch, MagicMock
from openai import APITimeoutError, RateLimitError, APIError, APIConnectionError, OpenAIError

from services.llm.provider_openai import OpenAIProvider
from services.llm.errors import (
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
    LLMConfigError,
)


@pytest.fixture
def mock_settings():
    with patch('services.llm.provider_openai.settings') as mock:
        mock.OPENAI_API_KEY = 'test-key'
        mock.OPENAI_MODEL_DEFAULT = 'gpt-4o-mini'
        mock.LLM_TIMEOUT_S = 60
        yield mock


@pytest.fixture
def mock_openai_client():
    with patch('services.llm.provider_openai.OpenAI') as mock:
        yield mock


class TestOpenAIProviderInit:
    def test_raises_config_error_when_no_api_key(self):
        with patch('services.llm.provider_openai.settings') as mock:
            mock.OPENAI_API_KEY = None
            with pytest.raises(LLMConfigError, match="OPENAI_API_KEY not configured"):
                OpenAIProvider()

    def test_creates_client_with_api_key(self, mock_settings, mock_openai_client):
        provider = OpenAIProvider()
        mock_openai_client.assert_called_once_with(api_key='test-key')

    def test_default_model_property(self, mock_settings, mock_openai_client):
        provider = OpenAIProvider()
        assert provider.default_model == 'gpt-4o-mini'


class TestOpenAIProviderErrors:
    @pytest.fixture
    def provider(self, mock_settings, mock_openai_client):
        return OpenAIProvider()

    def test_timeout_error_converted(self, provider, mock_openai_client):
        mock_openai_client.return_value.chat.completions.create.side_effect = APITimeoutError(request=Mock())
        with pytest.raises(LLMTimeoutError, match="Timeout after"):
            provider.chat_completion("sys", "user")

    def test_rate_limit_error_converted(self, provider, mock_openai_client):
        mock_openai_client.return_value.chat.completions.create.side_effect = RateLimitError(
            message="rate limit",
            response=Mock(status_code=429),
            body=None,
        )
        with pytest.raises(LLMRateLimitError, match="Rate limit exceeded"):
            provider.chat_completion("sys", "user")

    def test_connection_error_converted(self, provider, mock_openai_client):
        mock_openai_client.return_value.chat.completions.create.side_effect = APIConnectionError(request=Mock())
        with pytest.raises(LLMProviderError):
            provider.chat_completion("sys", "user")

    def test_api_error_converted(self, provider, mock_openai_client):
        error = APIError(
            message="internal error",
            request=Mock(),
            body=None,
        )
        error.status_code = 500
        mock_openai_client.return_value.chat.completions.create.side_effect = error
        with pytest.raises(LLMProviderError) as exc_info:
            provider.chat_completion("sys", "user")
        assert exc_info.value.status_code == 500

    def test_generic_openai_error_converted(self, provider, mock_openai_client):
        mock_openai_client.return_value.chat.completions.create.side_effect = OpenAIError("unknown error")
        with pytest.raises(LLMProviderError):
            provider.chat_completion("sys", "user")


class TestOpenAIProviderResponse:
    @pytest.fixture
    def provider(self, mock_settings, mock_openai_client):
        return OpenAIProvider()

    def test_successful_response(self, provider, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_response.id = "test-id"
        mock_openai_client.return_value.chat.completions.create.return_value = mock_response

        result = provider.chat_completion("system", "user")

        assert result.text == "Hello!"
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15
        assert result.response_id == "test-id"
        assert result.latency_ms >= 0

    def test_none_usage_handled(self, provider, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage = None
        mock_response.id = "test-id"
        mock_openai_client.return_value.chat.completions.create.return_value = mock_response

        result = provider.chat_completion("system", "user")

        assert result.text == "Hello!"
        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0
        assert result.usage.total_tokens == 0

    def test_none_content_handled(self, provider, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_response.id = "test-id"
        mock_openai_client.return_value.chat.completions.create.return_value = mock_response

        result = provider.chat_completion("system", "user")

        assert result.text == ""
