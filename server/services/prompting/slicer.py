from typing import Any
from .schema import ContextPack, DebugInfo, Budget
from .registry import get_section_spec
from .selectors import select_facts
from .assembler import assemble_context, render_prompt
from .budget import DEFAULT_BUDGET, trim_context


def slice_for_section(
    section_key: str,
    facts: dict[str, Any],
    outline: dict[str, Any],
    summaries: list[dict[str, Any]] = None,
    global_context: str = "",
    max_facts: int = 30
) -> ContextPack:
    if summaries is None:
        summaries = []

    spec = get_section_spec(section_key)

    selected_facts, fact_refs = select_facts(spec, facts, max_facts=max_facts)

    layers = assemble_context(
        spec=spec,
        selected_facts=selected_facts,
        outline=outline,
        summaries=summaries if spec.needs_summaries else [],
        global_context=global_context
    )

    trimmed_layers, trims_applied, estimated_tokens = trim_context(
        layers=layers,
        budget=DEFAULT_BUDGET,
        selected_facts=selected_facts
    )

    rendered = render_prompt(spec, trimmed_layers)

    final_budget = Budget(
        max_input_tokens_approx=DEFAULT_BUDGET.max_input_tokens_approx,
        max_output_tokens=DEFAULT_BUDGET.max_output_tokens,
        soft_char_limit=DEFAULT_BUDGET.soft_char_limit,
        estimated_input_tokens=estimated_tokens
    )

    debug = DebugInfo(
        selected_fact_refs=fact_refs,
        selection_reason=f"Selected {len(selected_facts)} facts by tags/keys",
        trims_applied=trims_applied
    )

    return ContextPack(
        section_key=section_key,
        layers=trimmed_layers,
        rendered_prompt=rendered,
        budget=final_budget,
        debug=debug
    )
