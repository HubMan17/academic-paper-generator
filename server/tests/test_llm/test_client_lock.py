import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import timedelta

from django.utils import timezone

from apps.llm.models import LLMCall
from services.llm.client import LLMClient
from services.llm.types import ProviderResponse, ProviderUsage


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


@pytest.mark.django_db
class TestClientLock:
    def test_creates_lock_on_first_call(self, mock_settings, mock_provider):
        mock_provider.chat_completion.return_value = create_response()

        client = LLMClient()
        result = client.generate_text("system", "user", use_cache=True)

        assert LLMCall.objects.count() == 1
        record = LLMCall.objects.first()
        assert record.status == LLMCall.Status.SUCCESS
        assert record.response_text == "test response"

    def test_returns_cached_result_on_second_call(self, mock_settings, mock_provider):
        mock_provider.chat_completion.return_value = create_response("first call")

        client = LLMClient()
        result1 = client.generate_text("system", "user", use_cache=True)
        result2 = client.generate_text("system", "user", use_cache=True)

        assert mock_provider.chat_completion.call_count == 1
        assert result1.text == "first call"
        assert result2.text == "first call"
        assert result2.meta.cached == True

    def test_no_cache_when_disabled(self, mock_settings, mock_provider):
        mock_provider.chat_completion.side_effect = [
            create_response("first"),
            create_response("second"),
        ]

        client = LLMClient()
        result1 = client.generate_text("system", "user", use_cache=False)
        result2 = client.generate_text("system", "user", use_cache=False)

        assert mock_provider.chat_completion.call_count == 2
        assert result1.text == "first"
        assert result2.text == "second"

    def test_model_stored_correctly(self, mock_settings, mock_provider):
        mock_provider.chat_completion.return_value = create_response()

        client = LLMClient()
        client.generate_text("system", "user", model="gpt-4o", use_cache=True)

        record = LLMCall.objects.first()
        assert record.model == "gpt-4o"
        assert record.meta["model"] == "gpt-4o"

    def test_failed_call_marked_as_failed(self, mock_settings, mock_provider):
        from services.llm.errors import LLMTimeoutError
        mock_provider.chat_completion.side_effect = LLMTimeoutError("timeout")

        client = LLMClient()
        with pytest.raises(LLMTimeoutError):
            client.generate_text("system", "user", use_cache=True)

        record = LLMCall.objects.first()
        assert record.status == LLMCall.Status.FAILED
        assert "timeout" in record.error.lower()


@pytest.mark.django_db
class TestClientLockJson:
    def test_json_cache_works(self, mock_settings, mock_provider):
        mock_provider.chat_completion.return_value = create_response('{"key": "value"}')

        client = LLMClient()
        result1 = client.generate_json("system", "user", use_cache=True)
        result2 = client.generate_json("system", "user", use_cache=True)

        assert mock_provider.chat_completion.call_count == 1
        assert result1.data == {"key": "value"}
        assert result2.data == {"key": "value"}
        assert result2.meta.cached == True


@pytest.mark.django_db
class TestStaleLockRecovery:
    def test_stale_lock_can_be_acquired(self, mock_settings, mock_provider):
        stale_time = timezone.now() - timedelta(seconds=300)
        LLMCall.objects.create(
            fingerprint="test_fp_123",
            model="gpt-4o-mini",
            status=LLMCall.Status.IN_PROGRESS,
        )
        LLMCall.objects.filter(fingerprint="test_fp_123").update(updated_at=stale_time)

        client = LLMClient()
        acquired = client._try_acquire_stale_lock("test_fp_123")

        assert acquired == True
        record = LLMCall.objects.get(fingerprint="test_fp_123")
        assert record.status == LLMCall.Status.IN_PROGRESS
        assert record.updated_at > stale_time

    def test_fresh_lock_not_acquired(self, mock_settings, mock_provider):
        LLMCall.objects.create(
            fingerprint="test_fp_fresh",
            model="gpt-4o-mini",
            status=LLMCall.Status.IN_PROGRESS,
        )

        client = LLMClient()
        acquired = client._try_acquire_stale_lock("test_fp_fresh")

        assert acquired == False

    def test_failed_stale_can_be_retried(self, mock_settings, mock_provider):
        stale_time = timezone.now() - timedelta(seconds=300)
        LLMCall.objects.create(
            fingerprint="test_fp_failed",
            model="gpt-4o-mini",
            status=LLMCall.Status.FAILED,
            error="previous error",
        )
        LLMCall.objects.filter(fingerprint="test_fp_failed").update(updated_at=stale_time)

        client = LLMClient()
        acquired = client._try_acquire_stale_lock("test_fp_failed")

        assert acquired == True
        record = LLMCall.objects.get(fingerprint="test_fp_failed")
        assert record.status == LLMCall.Status.IN_PROGRESS
        assert record.error is None


@pytest.mark.django_db
class TestLockTimeout:
    def test_lock_timeout_calculated_correctly(self, mock_settings, mock_provider):
        mock_settings.LLM_TIMEOUT_S = 30
        mock_settings.LLM_MAX_RETRIES = 3

        client = LLMClient()
        timeout = client._get_lock_timeout()

        assert timeout == 30 * 3 + 30
