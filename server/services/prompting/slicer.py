from typing import Any
from .schema import ContextPack, DebugInfo
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

    trimmed_layers, trims_applied = trim_context(
        layers=layers,
        budget=DEFAULT_BUDGET,
        selected_facts=selected_facts
    )

    rendered = render_prompt(spec, trimmed_layers)

    debug = DebugInfo(
        selected_fact_refs=fact_refs,
        selection_reason=f"Selected {len(selected_facts)} facts by tags/keys",
        trims_applied=trims_applied
    )

    return ContextPack(
        section_key=section_key,
        layers=trimmed_layers,
        rendered_prompt=rendered,
        budget=DEFAULT_BUDGET,
        debug=debug
    )
