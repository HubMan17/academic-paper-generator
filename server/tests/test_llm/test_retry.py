import pytest
from services.llm.retry import calculate_backoff, BACKOFF_BASE, BACKOFF_CAP, JITTER_MIN, JITTER_MAX


class TestCalculateBackoff:
    def test_exponential_growth(self):
        b1 = calculate_backoff(1)
        b2 = calculate_backoff(2)
        b3 = calculate_backoff(3)

        base1 = BACKOFF_BASE * 1
        base2 = BACKOFF_BASE * 2
        base3 = BACKOFF_BASE * 4

        assert base1 * JITTER_MIN <= b1 <= base1 * JITTER_MAX
        assert base2 * JITTER_MIN <= b2 <= base2 * JITTER_MAX
        assert base3 * JITTER_MIN <= b3 <= base3 * JITTER_MAX

    def test_respects_cap(self):
        backoff = calculate_backoff(100)
        assert backoff <= BACKOFF_CAP * JITTER_MAX

    def test_jitter_in_range(self):
        for attempt in range(1, 10):
            backoff = calculate_backoff(attempt)
            expected_base = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
            assert backoff >= expected_base * JITTER_MIN
            assert backoff <= expected_base * JITTER_MAX

    def test_returns_positive(self):
        for attempt in range(1, 20):
            assert calculate_backoff(attempt) > 0
