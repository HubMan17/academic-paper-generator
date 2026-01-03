from typing import Any
from .schema import Budget, ContextLayer


DEFAULT_BUDGET = Budget(
    max_input_tokens_approx=4000,
    max_output_tokens=2000,
    soft_char_limit=16000
)


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
) -> tuple[ContextLayer, list[str]]:
    trims_applied = []
    current_size = estimate_context_size(layers)

    if current_size <= budget.soft_char_limit:
        return layers, trims_applied

    trimmed_layers = ContextLayer(
        global_context=layers.global_context,
        outline_excerpt=layers.outline_excerpt,
        facts_slice=layers.facts_slice,
        summaries=layers.summaries,
        constraints=layers.constraints
    )

    if current_size > budget.soft_char_limit:
        trimmed_layers.facts_slice = _trim_facts_details(selected_facts)
        trims_applied.append("facts_details_trimmed")
        current_size = estimate_context_size(trimmed_layers)

    if current_size > budget.soft_char_limit:
        trimmed_layers.outline_excerpt = _trim_outline_to_headings(
            trimmed_layers.outline_excerpt
        )
        trims_applied.append("outline_reduced_to_headings")
        current_size = estimate_context_size(trimmed_layers)

    if current_size > budget.soft_char_limit:
        trimmed_layers.summaries = _trim_summaries(
            trimmed_layers.summaries,
            max_length=2000
        )
        trims_applied.append("summaries_trimmed")

    return trimmed_layers, trims_applied


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
