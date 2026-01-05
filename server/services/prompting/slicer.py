import hashlib
import json
from typing import Any
from .schema import ContextPack, DebugInfo, Budget, SectionSpec, RenderedPrompt, PROMPT_VERSION
from .registry import get_section_spec
from .selectors import select_facts
from .assembler import assemble_context, render_prompt
from .budget import DEFAULT_BUDGET, trim_context


def compute_prompt_fingerprint(
    rendered: RenderedPrompt,
    spec_key: str,
    fact_ids: list[str],
    budget: Budget
) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "spec_key": spec_key,
        "system": rendered.system,
        "user": rendered.user,
        "fact_ids": sorted(fact_ids),
        "budget": {
            "max_input_tokens_approx": budget.max_input_tokens_approx,
            "max_output_tokens": budget.max_output_tokens,
            "soft_char_limit": budget.soft_char_limit
        }
    }
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()[:16]


def slice_for_section(
    section_key: str,
    facts: dict[str, Any],
    outline: dict[str, Any],
    summaries: list[dict[str, Any]] = None,
    global_context: str = "",
    max_facts: int = 30,
    spec: SectionSpec | None = None
) -> ContextPack:
    if summaries is None:
        summaries = []

    if spec is None:
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
        selection_reason=f"Selected {len(selected_facts)} facts, scored and sorted by weight",
        trims_applied=trims_applied
    )

    fact_ids = [ref.fact_id for ref in fact_refs]
    fingerprint = compute_prompt_fingerprint(
        rendered=rendered,
        spec_key=section_key,
        fact_ids=fact_ids,
        budget=final_budget
    )

    return ContextPack(
        section_key=section_key,
        layers=trimmed_layers,
        rendered_prompt=rendered,
        budget=final_budget,
        debug=debug,
        prompt_version=PROMPT_VERSION,
        prompt_fingerprint=fingerprint
    )
