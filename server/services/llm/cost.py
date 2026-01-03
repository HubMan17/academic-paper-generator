from .pricing import MODEL_PRICING, DEFAULT_MODEL


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    input_cost = (prompt_tokens / 1000) * pricing["input"]
    output_cost = (completion_tokens / 1000) * pricing["output"]
    return round(input_cost + output_cost, 6)
