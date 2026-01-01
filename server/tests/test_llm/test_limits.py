import pytest
from django.test import override_settings
from services.llm.limits import check_input_limits
from services.llm.errors import LLMInputTooLargeError


class TestCheckInputLimits:
    @override_settings(LLM_MAX_CHARS_TOTAL=100)
    def test_raises_when_exceeded(self):
        with pytest.raises(LLMInputTooLargeError) as exc_info:
            check_input_limits("x" * 50, "y" * 60)
        assert exc_info.value.actual == 110
        assert exc_info.value.limit == 100

    @override_settings(LLM_MAX_CHARS_TOTAL=100)
    def test_passes_when_within_limit(self):
        check_input_limits("x" * 30, "y" * 30)

    @override_settings(LLM_MAX_CHARS_TOTAL=100)
    def test_passes_at_exact_limit(self):
        check_input_limits("x" * 50, "y" * 50)

    def test_uses_default_limit(self):
        check_input_limits("x" * 1000, "y" * 1000)
