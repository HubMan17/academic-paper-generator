import pytest
from services.llm.cost import estimate_cost


class TestEstimateCost:
    def test_gpt4o_mini_pricing(self):
        cost = estimate_cost("gpt-4o-mini", 1000, 1000)
        expected = (1000 / 1000) * 0.00015 + (1000 / 1000) * 0.0006
        assert cost == round(expected, 6)

    def test_gpt4o_pricing(self):
        cost = estimate_cost("gpt-4o", 1000, 500)
        expected = (1000 / 1000) * 0.005 + (500 / 1000) * 0.015
        assert cost == round(expected, 6)

    def test_unknown_model_uses_default(self):
        cost = estimate_cost("unknown-model", 1000, 1000)
        expected = (1000 / 1000) * 0.00015 + (1000 / 1000) * 0.0006
        assert cost == round(expected, 6)

    def test_zero_tokens(self):
        cost = estimate_cost("gpt-4o-mini", 0, 0)
        assert cost == 0.0
