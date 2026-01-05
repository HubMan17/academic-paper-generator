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


PRACTICE_SECTION_KEYS = {
    'practice', 'analysis', 'architecture', 'implementation', 'testing', 'design', 'development'
}

PRACTICE_GUARDRAILS = """
## СТРОГИЕ ТРЕБОВАНИЯ ДЛЯ ПРАКТИЧЕСКОЙ ЧАСТИ

### ОБЯЗАТЕЛЬНЫЙ МИНИМУМ:

1. **ТАБЛИЦА СУЩНОСТЕЙ** (минимум 6 строк):
   - Используй ТОЛЬКО модели из раздела FACTS.models
   - Формат: | Сущность | Атрибуты | Связи | Назначение |

2. **ТАБЛИЦА API ENDPOINTS** (ТОЛЬКО если есть в FACTS.api.endpoints):
   - Используй ТОЛЬКО endpoints из FACTS.api.endpoints
   - НЕ ВЫДУМЫВАЙ endpoints типа /api/v1/tasks, /auth/login если их нет в FACTS
   - Если endpoints нет — замени таблицу API на таблицу "Этапы пайплайна" из FACTS.pipeline.steps

3. **АЛГОРИТМ/ПАЙПЛАЙН** (если есть в FACTS.pipeline):
   - Используй реальные шаги из FACTS.pipeline.steps
   - Формат: Input → Step1 → Step2 → ... → Output

4. **СУЩНОСТИ ИЗ FACTS** (минимум 4):
   - Называй ТОЛЬКО классы/модули из FACTS.models или FACTS.pipeline
   - Document, Section, Artifact, DocumentArtifact — из FACTS, не выдумывай

### КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:

❌ ВЫДУМЫВАТЬ endpoints, которых нет в FACTS.api.endpoints
❌ ВЫДУМЫВАТЬ модели, которых нет в FACTS.models
❌ Использовать типовые endpoints (/tasks, /users, /auth) если их нет в FACTS
❌ Писать "нет данных", "информация отсутствует"
❌ Описание папок репозитория как "сущностей"

### ЕСЛИ ДАННЫХ НЕТ:

Если в FACTS нет нужной информации — НЕ упоминай этот аспект.
Лучше написать меньше, но правдиво, чем много но выдуманного.
"""

ANTI_HALLUCINATION_RULES = """
## ПРАВИЛО АНТИГАЛЛЮЦИНАЦИИ

КРИТИЧЕСКИ ВАЖНО: Ты МОЖЕШЬ использовать ТОЛЬКО данные из раздела FACTS.
Любой endpoint, модель, класс или технология, которых нет в FACTS — это ГАЛЛЮЦИНАЦИЯ.

Примеры ЗАПРЕЩЁННЫХ галлюцинаций:
- "/api/v1/tasks" — если этого endpoint нет в FACTS.api.endpoints
- "TaskModel" — если этой модели нет в FACTS.models
- "Redis для кеширования" — если Redis не упомянут в FACTS.runtime.dependencies

Если ты не уверен, есть ли что-то в FACTS — НЕ ПИШИ об этом.
"""


def _is_practice_section(spec: SectionSpec) -> bool:
    if spec.key.startswith('practice_'):
        return True
    if spec.key in PRACTICE_SECTION_KEYS:
        return True
    key_lower = spec.key.lower()
    practice_markers = ['practice', 'implementation', 'testing', 'architecture', 'api', 'analysis']
    return any(marker in key_lower for marker in practice_markers)


def _build_system_prompt(spec: SectionSpec) -> str:
    style_instructions = {
        "academic": "Используй строго академический стиль изложения.",
        "business": "Используй деловой стиль изложения."
    }

    style = style_instructions.get(spec.style_profile, style_instructions["academic"])

    is_practice = _is_practice_section(spec)
    practice_rules = PRACTICE_GUARDRAILS if is_practice else ""
    anti_hallucination = ANTI_HALLUCINATION_RULES if is_practice else ""

    return f"""Ты генератор академических текстов для документации программного проекта.

{style}

ВАЖНО:
- НЕ повторяй информацию из предыдущих секций (summaries)
- НЕ добавляй факты, которых нет в предоставленных данных
- ЗАПРЕЩЕНО писать "нет данных", "информация отсутствует" — просто пропусти этот пункт
- Ссылайся ТОЛЬКО на факты из раздела FACTS
{practice_rules}
{anti_hallucination}
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
