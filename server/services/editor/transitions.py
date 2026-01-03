from typing import Optional

from services.llm import LLMClient
from .schema import Transition, EditPlan
from . import prompts


def generate_transitions(
    llm_client: LLMClient,
    sections: list[dict],
    edit_plan: EditPlan,
    idempotency_prefix: Optional[str] = None,
) -> list[Transition]:
    transitions: list[Transition] = []
    sections_by_key = {s["key"]: s for s in sections}

    for from_key, to_key in edit_plan.transitions_needed:
        if from_key not in sections_by_key or to_key not in sections_by_key:
            continue

        from_section = sections_by_key[from_key]
        to_section = sections_by_key[to_key]

        from_text = from_section.get("text", "")
        to_text = to_section.get("text", "")

        if not from_text or not to_text:
            continue

        idempotency_key = None
        if idempotency_prefix:
            idempotency_key = f"{idempotency_prefix}:transition:{from_key}:{to_key}"

        transition = _generate_single_transition(
            llm_client=llm_client,
            from_key=from_key,
            from_text=from_text,
            to_key=to_key,
            to_text=to_text,
            idempotency_key=idempotency_key,
        )

        if transition:
            transitions.append(transition)

    return transitions


def _generate_single_transition(
    llm_client: LLMClient,
    from_key: str,
    from_text: str,
    to_key: str,
    to_text: str,
    idempotency_key: Optional[str] = None,
) -> Optional[Transition]:
    from_end = from_text[-1000:] if len(from_text) > 1000 else from_text
    to_start = to_text[:1000] if len(to_text) > 1000 else to_text

    user_prompt = prompts.get_transition_user(
        from_section_key=from_key,
        from_section_end=from_end,
        to_section_key=to_key,
        to_section_start=to_start,
    )

    result = llm_client.generate_text(
        system=prompts.TRANSITION_SYSTEM,
        user=user_prompt,
        max_tokens=300,
    )

    transition_text = result.text.strip()

    if len(transition_text) < 20 or len(transition_text) > 500:
        return None

    return Transition(
        from_section=from_key,
        to_section=to_key,
        text=transition_text,
        position="after_from",
    )


def apply_transitions(
    sections: list[dict],
    transitions: list[Transition],
) -> list[dict]:
    transitions_by_from = {t.from_section: t for t in transitions}
    updated_sections = []

    for section in sections:
        key = section.get("key", "")
        text = section.get("text", "")

        if key in transitions_by_from:
            transition = transitions_by_from[key]
            if transition.position == "after_from":
                text = text.rstrip() + "\n\n" + transition.text

        updated_sections.append({
            **section,
            "text": text,
        })

    return updated_sections


def transitions_to_dict(transitions: list[Transition]) -> dict:
    return {
        "version": "v1",
        "transitions": [
            {
                "from_section": t.from_section,
                "to_section": t.to_section,
                "text": t.text,
                "position": t.position,
            }
            for t in transitions
        ],
        "count": len(transitions),
    }
