from typing import Any
from .schema import Budget, ContextLayer
from .tokens import TokenBudgetEstimator, estimate_text_tokens


DEFAULT_BUDGET = Budget(
    max_input_tokens_approx=4000,
    max_output_tokens=2000,
    soft_char_limit=16000,
    estimated_input_tokens=0
)


def estimate_context_tokens(layers: ContextLayer) -> int:
    total = 0
    total += estimate_text_tokens(layers.global_context)
    total += estimate_text_tokens(layers.outline_excerpt)
    total += estimate_text_tokens(layers.facts_slice)
    total += estimate_text_tokens(layers.summaries)
    total += estimate_text_tokens(layers.constraints)
    return total


def estimate_context_size(layers: ContextLayer) -> int:
    total = 0
    total += len(layers.global_context)
    total += len(layers.outline_excerpt)
    total += len(layers.facts_slice)
    total += len(layers.summaries)
    total += len(layers.constraints)
    return total


def trim_context(
    layers: ContextLayer,
    budget: Budget,
    selected_facts: list[dict[str, Any]]
) -> tuple[ContextLayer, list[str], int]:
    trims_applied = []
    current_tokens = estimate_context_tokens(layers)
    current_chars = estimate_context_size(layers)

    within_token_budget = current_tokens <= budget.max_input_tokens_approx
    within_char_budget = current_chars <= budget.soft_char_limit

    if within_token_budget and within_char_budget:
        return layers, trims_applied, current_tokens

    trimmed_layers = ContextLayer(
        global_context=layers.global_context,
        outline_excerpt=layers.outline_excerpt,
        facts_slice=layers.facts_slice,
        summaries=layers.summaries,
        constraints=layers.constraints
    )

    if current_tokens > budget.max_input_tokens_approx or current_chars > budget.soft_char_limit:
        trimmed_layers.facts_slice = _trim_facts_details(selected_facts)
        trims_applied.append("facts_details_trimmed")
        current_tokens = estimate_context_tokens(trimmed_layers)
        current_chars = estimate_context_size(trimmed_layers)

    if current_tokens > budget.max_input_tokens_approx or current_chars > budget.soft_char_limit:
        trimmed_layers.outline_excerpt = _trim_outline_to_headings(
            trimmed_layers.outline_excerpt
        )
        trims_applied.append("outline_reduced_to_headings")
        current_tokens = estimate_context_tokens(trimmed_layers)
        current_chars = estimate_context_size(trimmed_layers)

    if current_tokens > budget.max_input_tokens_approx or current_chars > budget.soft_char_limit:
        estimator = TokenBudgetEstimator(budget.max_input_tokens_approx)
        target_summary_tokens = max(200, budget.max_input_tokens_approx // 4)
        trimmed_layers.summaries = estimator.trim_to_budget(
            trimmed_layers.summaries,
            target_summary_tokens
        )
        trims_applied.append("summaries_trimmed")
        current_tokens = estimate_context_tokens(trimmed_layers)

    return trimmed_layers, trims_applied, current_tokens


def _trim_facts_details(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return ""

    lines = []
    for fact in facts:
        fact_id = fact.get("id", "unknown")
        text = fact.get("text", "")

        if text:
            lines.append(f"[{fact_id}] {text}")

    return "\n".join(lines)


def _trim_outline_to_headings(outline_text: str) -> str:
    if not outline_text:
        return ""

    lines = outline_text.split("\n")
    headings = [line for line in lines if line.strip().startswith("-") or "title" in line.lower()]

    return "\n".join(headings[:20])


def _trim_summaries(summaries_text: str, max_length: int) -> str:
    if len(summaries_text) <= max_length:
        return summaries_text

    return summaries_text[:max_length] + "..."
