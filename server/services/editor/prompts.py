from .schema import EditLevel


EDIT_PLAN_SYSTEM = """Ты — редактор академических текстов. Твоя задача — составить план редактирования документа.

Анализируй:
- Какие секции требуют правок
- Где нужны переходы между секциями
- Какие термины нужно унифицировать
- Общие проблемы стиля

Отвечай строго в JSON формате."""


def get_edit_plan_user(
    outline: dict,
    section_summaries: list[dict],
    metrics: dict,
    level: EditLevel
) -> str:
    level_desc = {
        EditLevel.LEVEL_1: "Базовая редактура: убрать повторы, выровнять стиль, добавить переходы",
        EditLevel.LEVEL_2: "Средняя редактура: + перестройка абзацев, усиление логики",
        EditLevel.LEVEL_3: "Полная редактура под ВУЗ: + цель/задачи/объект/предмет, контроль объёма",
    }

    return f"""# ПЛАН ДОКУМЕНТА
{_format_outline(outline)}

# КРАТКОЕ СОДЕРЖАНИЕ СЕКЦИЙ
{_format_summaries(section_summaries)}

# МЕТРИКИ КАЧЕСТВА
{_format_metrics(metrics)}

# УРОВЕНЬ РЕДАКТУРЫ
{level_desc.get(level, level_desc[EditLevel.LEVEL_1])}

# ЗАДАЧА
Составь план редактирования. Верни JSON:
{{
  "sections_to_edit": [
    {{
      "key": "intro",
      "action": "edit|rewrite|expand",
      "priority": 1,
      "issues": ["проблема 1", "проблема 2"],
      "suggestions": ["что сделать"]
    }}
  ],
  "transitions_needed": [["intro", "theory"], ["theory", "architecture"]],
  "terms_to_unify": ["API", "REST API", "АПИ"],
  "global_notes": ["общие замечания по документу"]
}}"""


GLOSSARY_SYSTEM = """Ты — технический редактор. Твоя задача — составить глоссарий терминов для академического документа.

Для каждого термина определи:
- Каноническое написание
- Варианты написания, которые встречаются в тексте
- Краткий контекст использования

Отвечай строго в JSON формате."""


def get_glossary_user(term_candidates: list[str], text_excerpts: str) -> str:
    return f"""# КАНДИДАТЫ В ТЕРМИНЫ
{', '.join(term_candidates)}

# ПРИМЕРЫ ИЗ ТЕКСТА
{text_excerpts}

# ЗАДАЧА
Составь глоссарий. Для каждого значимого термина определи каноническое написание.
Верни JSON:
{{
  "terms": [
    {{
      "canonical": "REST API",
      "variants": ["REST-API", "REST api", "РЕСТ АПИ"],
      "context": "интерфейс взаимодействия"
    }}
  ]
}}"""


SECTION_EDIT_SYSTEM_L1 = """Ты — редактор академических текстов на русском языке.

Твоя задача — отредактировать текст секции БЕЗ ИЗМЕНЕНИЯ СМЫСЛА:
- Убрать повторы слов и фраз
- Выровнять академический стиль
- Убрать канцеляризмы и воду
- Сделать переходы между абзацами плавными
- Унифицировать терминологию по глоссарию

ЗАПРЕЩЕНО:
- Добавлять новые факты
- Менять структуру или порядок мысли
- Удалять важную информацию
- Писать "отсутствует информация"

Если данных мало — формулируй нейтрально: "в рамках данной работы акцент сделан на..."

Верни только отредактированный текст, без пояснений."""


SECTION_EDIT_SYSTEM_L2 = """Ты — редактор академических текстов на русском языке.

Твоя задача — глубоко отредактировать текст секции:
- Всё из базовой редактуры (повторы, стиль, канцеляризмы)
- Перестроить абзацы для лучшей логики
- Усилить связность и аргументацию
- Расширить слишком краткие места (если есть материал)

ЗАПРЕЩЕНО:
- Выдумывать факты
- Кардинально менять содержание
- Писать об отсутствии информации

Верни только отредактированный текст, без пояснений."""


SECTION_EDIT_SYSTEM_L3 = """Ты — редактор академических текстов для ВУЗа.

Твоя задача — привести текст в соответствие с требованиями ВУЗа:
- Всё из средней редактуры
- Для введения: чётко выделить цель, задачи, объект, предмет исследования
- Использовать «ожидаемые» академические формулировки
- Контролировать объём (не раздувать, не сокращать критично)

ЗАПРЕЩЕНО:
- Выдумывать факты
- Писать об отсутствии данных явно

Верни только отредактированный текст, без пояснений."""


def get_section_edit_system(level: EditLevel) -> str:
    if level == EditLevel.LEVEL_3:
        return SECTION_EDIT_SYSTEM_L3
    elif level == EditLevel.LEVEL_2:
        return SECTION_EDIT_SYSTEM_L2
    return SECTION_EDIT_SYSTEM_L1


def get_section_edit_user(
    section_key: str,
    section_text: str,
    prev_excerpt: str,
    next_excerpt: str,
    glossary_terms: list[dict],
    edit_suggestions: list[str]
) -> str:
    glossary_str = "\n".join(
        f"- {t['canonical']}: {', '.join(t.get('variants', []))}"
        for t in glossary_terms
    ) if glossary_terms else "Нет специфичных терминов"

    suggestions_str = "\n".join(f"- {s}" for s in edit_suggestions) if edit_suggestions else "Общая редактура"

    prev_str = f"...{prev_excerpt[-500:]}" if prev_excerpt else "(начало документа)"
    next_str = f"{next_excerpt[:500]}..." if next_excerpt else "(конец документа)"

    return f"""# КОНТЕКСТ: ПРЕДЫДУЩАЯ СЕКЦИЯ (конец)
{prev_str}

# СЕКЦИЯ ДЛЯ РЕДАКТИРОВАНИЯ: {section_key}
{section_text}

# КОНТЕКСТ: СЛЕДУЮЩАЯ СЕКЦИЯ (начало)
{next_str}

# ГЛОССАРИЙ ТЕРМИНОВ
{glossary_str}

# УКАЗАНИЯ ПО РЕДАКТУРЕ
{suggestions_str}

# ЗАДАЧА
Отредактируй текст секции. Верни только отредактированный текст."""


TRANSITION_SYSTEM = """Ты — редактор академических текстов. Твоя задача — написать плавный переход между секциями.

Переход должен:
- Связать конец предыдущей секции с началом следующей
- Быть кратким (1-3 предложения)
- Соответствовать академическому стилю
- Не повторять уже сказанное

Верни только текст перехода, без пояснений."""


def get_transition_user(
    from_section_key: str,
    from_section_end: str,
    to_section_key: str,
    to_section_start: str
) -> str:
    return f"""# КОНЕЦ СЕКЦИИ "{from_section_key}"
...{from_section_end[-800:]}

# НАЧАЛО СЕКЦИИ "{to_section_key}"
{to_section_start[:800]}...

# ЗАДАЧА
Напиши переход (1-3 предложения), который можно вставить между этими секциями."""


CHAPTER_CONCLUSION_SYSTEM = """Ты — редактор академических текстов. Твоя задача — написать краткие выводы по главе.

Выводы должны:
- Содержать 3-5 ключевых пунктов
- Обобщать содержание главы
- Быть в формате маркированного списка
- Соответствовать академическому стилю

Верни JSON с массивом bullets."""


def get_chapter_conclusion_user(
    chapter_title: str,
    section_summaries: list[dict]
) -> str:
    summaries_str = "\n\n".join(
        f"### {s['title']}\n{s['summary']}"
        for s in section_summaries
    )

    return f"""# ГЛАВА: {chapter_title}

# СОДЕРЖАНИЕ СЕКЦИЙ
{summaries_str}

# ЗАДАЧА
Сформулируй выводы по главе. Верни JSON:
{{
  "bullets": [
    "вывод 1",
    "вывод 2",
    "вывод 3"
  ]
}}"""


FINAL_CONCLUSION_SYSTEM = """Ты — редактор академических текстов. Твоя задача — написать заключение документа.

Заключение должно:
- Обобщить проделанную работу
- Сформулировать основные результаты
- Указать перспективы развития (кратко)
- НЕ повторять текст секций дословно

Соответствовать академическому стилю. Объём: 1-2 страницы."""


def get_final_conclusion_user(
    document_title: str,
    chapter_conclusions: list[dict],
    original_conclusion: str
) -> str:
    conclusions_str = "\n\n".join(
        f"### {c['chapter_title']}\n" + "\n".join(f"- {b}" for b in c['bullets'])
        for c in chapter_conclusions
    )

    return f"""# ДОКУМЕНТ: {document_title}

# ВЫВОДЫ ПО ГЛАВАМ
{conclusions_str}

# ТЕКУЩЕЕ ЗАКЛЮЧЕНИЕ
{original_conclusion}

# ЗАДАЧА
Перепиши заключение, чтобы оно:
- Обобщало результаты работы
- Не повторяло текст дословно
- Указывало перспективы (1 абзац)

Верни только текст заключения."""


def _format_outline(outline: dict) -> str:
    if not outline:
        return "Outline не задан"

    lines = []
    for chapter in outline.get("chapters", []):
        lines.append(f"## {chapter.get('title', 'Без названия')}")
        for section in chapter.get("sections", []):
            lines.append(f"  - {section.get('title', '')}")
    return "\n".join(lines)


def _format_summaries(summaries: list[dict]) -> str:
    if not summaries:
        return "Саммари не заданы"

    lines = []
    for s in summaries:
        lines.append(f"### {s.get('key', '')}: {s.get('title', '')}")
        lines.append(s.get("summary", "")[:300])
        lines.append("")
    return "\n".join(lines)


def _format_metrics(metrics: dict) -> str:
    if not metrics:
        return "Метрики не заданы"

    lines = [
        f"Всего символов: {metrics.get('total_chars', 0)}",
        f"Всего слов: {metrics.get('total_words', 0)}",
        f"Коротких секций: {len(metrics.get('short_sections', []))}",
        f"Пустых секций: {len(metrics.get('empty_sections', []))}",
        f"Глобальных повторов: {len(metrics.get('global_repeats', []))}",
    ]

    if metrics.get("style_issues"):
        lines.append("Проблемы стиля:")
        for issue in metrics["style_issues"][:5]:
            lines.append(f"  - {issue}")

    return "\n".join(lines)
