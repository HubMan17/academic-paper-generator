import json
from typing import Any
from .schema import SectionSpec, ContextLayer, RenderedPrompt, OutlineMode, SECTION_OUTPUT_SCHEMA


PRACTICE_SECTION_KEYS = {
    'practice', 'analysis', 'architecture', 'implementation', 'testing', 'design', 'development'
}

PRACTICE_ACADEMIC_TEMPLATE = """
## ОБЯЗАТЕЛЬНАЯ СТРУКТУРА ПРАКТИЧЕСКОЙ СЕКЦИИ

Следуй этой структуре для практической части:

1. ПОСТАНОВКА ЗАДАЧИ И ТРЕБОВАНИЯ
   - Чётко сформулируй решаемую задачу
   - Перечисли функциональные требования (FR) списком
   - Перечисли нефункциональные требования (NFR)

2. АРХИТЕКТУРА (компоненты и взаимодействия)
   - Опиши основные модули/компоненты системы
   - Покажи связи между компонентами
   - Объясни выбор архитектурного паттерна

3. МОДЕЛЬ ДАННЫХ / АРТЕФАКТЫ
   - Опиши ключевые сущности и их атрибуты
   - Покажи связи между сущностями
   - Укажи форматы данных (JSON, etc.)

4. ПАЙПЛАЙН / АЛГОРИТМ
   - Опиши последовательность шагов обработки
   - Приведи псевдокод или блок-схему ключевых алгоритмов
   - Объясни логику принятия решений

5. API / ИНТЕРФЕЙСЫ
   - Перечисли ключевые endpoints/методы
   - Опиши входные и выходные параметры
   - Приведи примеры запросов/ответов

6. ТЕСТИРОВАНИЕ И РЕЗУЛЬТАТЫ
   - Опиши стратегию тестирования
   - Приведи конкретные метрики (до/после, если применимо)
   - Покажи результаты валидации
"""

ANTI_WATER_RULES = """
## АНТИ-ВОДА ПРАВИЛА (СТРОГО СОБЛЮДАТЬ)

ЗАПРЕЩЕНО:
- Общие фразы без конкретики ("система позволяет", "обеспечивает гибкость")
- Обзорные абзацы без технических деталей
- Повторение одной мысли разными словами
- Пустые вводные предложения
- Банальности ("в современном мире", "с развитием технологий")

ОБЯЗАТЕЛЬНО:
- Каждый абзац содержит конкретные факты из FACTS
- Называть конкретные технологии, модули, методы
- Приводить примеры (псевдокод, структуры данных, endpoints)
- Использовать числа и метрики где возможно
- Минимум 70% текста — конкретика из анализа проекта
"""


def _is_practice_section(spec: SectionSpec) -> bool:
    if spec.chapter_key == 'practice':
        return True
    if spec.key.startswith('practice_'):
        return True
    if spec.key in PRACTICE_SECTION_KEYS:
        return True
    return False


def assemble_context(
    spec: SectionSpec,
    selected_facts: list[dict[str, Any]],
    outline: dict[str, Any],
    summaries: list[dict[str, Any]],
    global_context: str = ""
) -> ContextLayer:
    outline_excerpt = _extract_outline_excerpt(outline, spec.outline_mode, spec.key)
    outline_points = _extract_section_points(outline, spec.key)
    facts_slice = _format_facts(selected_facts)
    summaries_text = _format_summaries(summaries)
    constraints_text = _format_constraints(spec)

    return ContextLayer(
        global_context=global_context,
        outline_excerpt=outline_excerpt,
        outline_points=outline_points,
        facts_slice=facts_slice,
        summaries=summaries_text,
        constraints=constraints_text
    )


def render_prompt(spec: SectionSpec, layers: ContextLayer) -> RenderedPrompt:
    system_prompt = _build_system_prompt(spec)
    user_prompt = _build_user_prompt(spec, layers)

    return RenderedPrompt(system=system_prompt, user=user_prompt)


JSON_OUTPUT_INSTRUCTION = """
## ФОРМАТ ОТВЕТА

Ты ДОЛЖЕН вернуть ответ в формате JSON со следующей структурой:
{
  "text": "<сгенерированный текст секции в Markdown>",
  "facts_used": ["fact_id_1", "fact_id_2", ...],
  "outline_points_covered": ["пункт 1", "пункт 2", ...],
  "warnings": ["предупреждение 1", ...]
}

- text: полный текст секции
- facts_used: ID фактов из раздела FACTS, которые ты использовал (в формате [id])
- outline_points_covered: какие пункты из OUTLINE POINTS ты покрыл
- warnings: если данных недостаточно, укажи какие аспекты не удалось раскрыть
"""


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
{JSON_OUTPUT_INSTRUCTION}
"""


def _build_user_prompt(spec: SectionSpec, layers: ContextLayer) -> str:
    sections = []

    if layers.global_context:
        sections.append(f"# GLOBAL CONTEXT\n{layers.global_context}")

    if layers.outline_excerpt:
        sections.append(f"# OUTLINE\n{layers.outline_excerpt}")

    if layers.outline_points:
        sections.append(f"# OUTLINE POINTS FOR THIS SECTION\n{layers.outline_points}\n\nОБЯЗАТЕЛЬНО покрой каждый из перечисленных пунктов в тексте секции.")

    if _is_practice_section(spec):
        sections.append(f"# PRACTICE SECTION TEMPLATE{PRACTICE_ACADEMIC_TEMPLATE}")
        sections.append(f"# QUALITY RULES{ANTI_WATER_RULES}")

    if layers.facts_slice:
        sections.append(f"# FACTS\n{layers.facts_slice}")

    if layers.summaries:
        sections.append(f"# PREVIOUS SECTIONS (не повторяй эту информацию)\n{layers.summaries}")

    if layers.constraints:
        sections.append(f"# CONSTRAINTS\n{layers.constraints}")

    sections.append(f"\n# TASK\nСгенерируй секцию '{spec.key}' документа.")

    return "\n\n".join(sections)


def _extract_section_points(outline: dict[str, Any], section_key: str) -> str:
    if not outline or "sections" not in outline:
        return ""

    sections = outline.get("sections", [])
    for section in sections:
        if section.get("key") == section_key:
            points = section.get("points", [])
            if points:
                lines = []
                for i, point in enumerate(points, 1):
                    lines.append(f"{i}. {point}")
                return "\n".join(lines)
            break

    return ""


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
