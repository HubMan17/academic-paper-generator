import json
from typing import Any
from .schema import SectionSpec, ContextLayer, RenderedPrompt, OutlineMode


def assemble_context(
    spec: SectionSpec,
    selected_facts: list[dict[str, Any]],
    outline: dict[str, Any],
    summaries: list[dict[str, Any]],
    global_context: str = ""
) -> ContextLayer:
    outline_excerpt = _extract_outline_excerpt(outline, spec.outline_mode, spec.key)
    facts_slice = _format_facts(selected_facts)
    summaries_text = _format_summaries(summaries)
    constraints_text = _format_constraints(spec)

    return ContextLayer(
        global_context=global_context,
        outline_excerpt=outline_excerpt,
        facts_slice=facts_slice,
        summaries=summaries_text,
        constraints=constraints_text
    )


def render_prompt(spec: SectionSpec, layers: ContextLayer) -> RenderedPrompt:
    system_prompt = _build_system_prompt(spec)
    user_prompt = _build_user_prompt(spec, layers)

    return RenderedPrompt(system=system_prompt, user=user_prompt)


def _build_system_prompt(spec: SectionSpec) -> str:
    style_instructions = {
        "academic": "Используй строго академический стиль изложения.",
        "business": "Используй деловой стиль изложения."
    }

    style = style_instructions.get(spec.style_profile, style_instructions["academic"])

    return f"""Ты генератор академических текстов для документации программного проекта.

{style}

ВАЖНО:
- НЕ повторяй информацию из предыдущих секций (summaries)
- НЕ добавляй факты, которых нет в предоставленных данных
- Если информации недостаточно, пиши "нет данных" или опусти этот пункт
- Ссылайся только на факты из раздела FACTS
"""


def _build_user_prompt(spec: SectionSpec, layers: ContextLayer) -> str:
    sections = []

    if layers.global_context:
        sections.append(f"# GLOBAL CONTEXT\n{layers.global_context}")

    if layers.outline_excerpt:
        sections.append(f"# OUTLINE\n{layers.outline_excerpt}")

    if layers.facts_slice:
        sections.append(f"# FACTS\n{layers.facts_slice}")

    if layers.summaries:
        sections.append(f"# PREVIOUS SECTIONS (не повторяй эту информацию)\n{layers.summaries}")

    if layers.constraints:
        sections.append(f"# CONSTRAINTS\n{layers.constraints}")

    sections.append(f"\n# TASK\nСгенерируй секцию '{spec.key}' документа.")

    return "\n\n".join(sections)


def _extract_outline_excerpt(
    outline: dict[str, Any],
    mode: OutlineMode,
    section_key: str
) -> str:
    if not outline:
        return ""

    if mode == OutlineMode.FULL:
        return json.dumps(outline, ensure_ascii=False, indent=2)

    sections = outline.get("sections", [])
    if not sections:
        return ""

    title = outline.get("title", "")

    if mode == OutlineMode.STRUCTURE:
        lines = []
        if title:
            lines.append(f"Название: {title}")
            lines.append("")
        lines.append("Структура:")
        for i, s in enumerate(sections, 1):
            s_title = s.get("title", "")
            s_key = s.get("key", "")
            marker = ">" if s_key == section_key else " "
            lines.append(f"{marker} {i}. {s_title}")
        return "\n".join(lines)

    if mode == OutlineMode.LOCAL:
        current_idx = None
        for i, s in enumerate(sections):
            if s.get("key") == section_key:
                current_idx = i
                break

        if current_idx is None:
            return ""

        start = max(0, current_idx - 1)
        end = min(len(sections), current_idx + 2)
        window = sections[start:end]

        lines = []
        if title:
            lines.append(f"Название: {title}")
            lines.append("")

        for s in window:
            s_key = s.get("key", "")
            s_title = s.get("title", "")
            points = s.get("points", [])
            marker = ">" if s_key == section_key else " "
            lines.append(f"{marker} [{s_key}] {s_title}")
            for p in points[:5]:
                lines.append(f"    - {p}")

        return "\n".join(lines)

    return ""


def _format_facts(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return ""

    lines = []
    for fact in facts:
        fact_id = fact.get("id", "unknown")
        text = fact.get("text", "")
        details = fact.get("details", "")

        if text:
            lines.append(f"[{fact_id}] {text}")
            if details:
                lines.append(f"  Details: {details}")

    return "\n".join(lines)


def _format_summaries(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return ""

    lines = []
    for summary in summaries:
        section_key = summary.get("section_key", "unknown")
        points = summary.get("points", [])

        if points:
            lines.append(f"Секция '{section_key}':")
            for point in points:
                lines.append(f"  - {point}")

    return "\n".join(lines)


def _format_constraints(spec: SectionSpec) -> str:
    lines = []

    min_chars, max_chars = spec.target_chars
    lines.append(f"Объём: {min_chars}-{max_chars} символов")

    for constraint in spec.constraints:
        lines.append(f"- {constraint}")

    return "\n".join(lines)
