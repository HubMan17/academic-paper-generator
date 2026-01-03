from typing import Optional

from services.llm import LLMClient
from .schema import (
    EditLevel,
    SectionEdited,
    EditPlan,
    Glossary,
)
from . import prompts


def edit_section(
    llm_client: LLMClient,
    section_key: str,
    section_text: str,
    prev_section_text: str,
    next_section_text: str,
    glossary: Glossary,
    edit_plan: EditPlan,
    level: EditLevel = EditLevel.LEVEL_1,
    idempotency_key: Optional[str] = None,
) -> SectionEdited:
    section_plan = _get_section_plan(edit_plan, section_key)
    suggestions = section_plan.suggestions if section_plan else []

    glossary_terms = [
        {"canonical": t.canonical, "variants": t.variants}
        for t in glossary.terms[:15]
    ]

    system_prompt = prompts.get_section_edit_system(level)
    user_prompt = prompts.get_section_edit_user(
        section_key=section_key,
        section_text=section_text,
        prev_excerpt=prev_section_text,
        next_excerpt=next_section_text,
        glossary_terms=glossary_terms,
        edit_suggestions=suggestions,
    )

    result = llm_client.generate_text(
        system=system_prompt,
        user=user_prompt,
        max_tokens=4000,
    )

    edited_text = result.text.strip()
    changes_made = _detect_changes(section_text, edited_text)

    return SectionEdited(
        key=section_key,
        original_text=section_text,
        edited_text=edited_text,
        changes_made=changes_made,
        llm_trace_id=None,
    )


def _get_section_plan(edit_plan: EditPlan, section_key: str):
    for s in edit_plan.sections_to_edit:
        if s.key == section_key:
            return s
    return None


def _detect_changes(original: str, edited: str) -> list[str]:
    changes = []

    orig_len = len(original)
    edit_len = len(edited)
    diff_percent = abs(edit_len - orig_len) / max(orig_len, 1) * 100

    if diff_percent > 20:
        if edit_len > orig_len:
            changes.append(f"Расширен текст (+{diff_percent:.0f}%)")
        else:
            changes.append(f"Сокращён текст (-{diff_percent:.0f}%)")

    orig_sentences = _count_sentences(original)
    edit_sentences = _count_sentences(edited)
    if abs(orig_sentences - edit_sentences) > 2:
        changes.append(f"Изменено количество предложений: {orig_sentences} → {edit_sentences}")

    orig_paragraphs = original.count('\n\n')
    edit_paragraphs = edited.count('\n\n')
    if orig_paragraphs != edit_paragraphs:
        changes.append(f"Изменена структура абзацев: {orig_paragraphs} → {edit_paragraphs}")

    if not changes:
        changes.append("Стилистическая правка")

    return changes


def _count_sentences(text: str) -> int:
    import re
    sentences = re.split(r'[.!?]+', text)
    return len([s for s in sentences if s.strip()])


def section_edited_to_dict(section: SectionEdited) -> dict:
    return {
        "key": section.key,
        "original_char_count": len(section.original_text),
        "edited_char_count": len(section.edited_text),
        "changes_made": section.changes_made,
        "llm_trace_id": section.llm_trace_id,
    }


def edit_sections_batch(
    llm_client: LLMClient,
    sections: list[dict],
    glossary: Glossary,
    edit_plan: EditPlan,
    level: EditLevel = EditLevel.LEVEL_1,
    idempotency_prefix: Optional[str] = None,
    skip_completed: Optional[set[str]] = None,
) -> dict[str, SectionEdited]:
    skip_completed = skip_completed or set()
    results: dict[str, SectionEdited] = {}

    sections_by_key = {s["key"]: s for s in sections}
    ordered_keys = [s["key"] for s in sections]

    sections_to_process = [
        s for s in edit_plan.sections_to_edit
        if s.key not in skip_completed and s.key in sections_by_key
    ]

    for section_plan in sections_to_process:
        key = section_plan.key
        section = sections_by_key[key]

        key_index = ordered_keys.index(key)
        prev_text = ""
        next_text = ""

        if key_index > 0:
            prev_key = ordered_keys[key_index - 1]
            prev_text = sections_by_key[prev_key].get("text", "")

        if key_index < len(ordered_keys) - 1:
            next_key = ordered_keys[key_index + 1]
            next_text = sections_by_key[next_key].get("text", "")

        idempotency_key = None
        if idempotency_prefix:
            idempotency_key = f"{idempotency_prefix}:section:{key}"

        result = edit_section(
            llm_client=llm_client,
            section_key=key,
            section_text=section.get("text", ""),
            prev_section_text=prev_text,
            next_section_text=next_text,
            glossary=glossary,
            edit_plan=edit_plan,
            level=level,
            idempotency_key=idempotency_key,
        )

        results[key] = result

    return results
