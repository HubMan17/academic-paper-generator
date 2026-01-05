import json
import logging
from typing import Any
from uuid import UUID

from apps.projects.models import Artifact, Document, DocumentArtifact, Section
from services.llm import LLMClient
from services.pipeline.ensure import ensure_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import GenerationProfile, get_profile
from services.pipeline.work_types import get_work_type_preset
from services.pipeline.specs import get_sections_for_work_type
from services.pipeline.facts_sanitizer import sanitize_facts_for_llm

logger = logging.getLogger(__name__)

OUTLINE_SYSTEM = """Ты технический писатель для академических работ.
Генерируй структурированный план документа в JSON формате.
Формат ответа:
{
    "title": "Название работы",
    "sections": [
        {"key": "intro", "title": "Введение", "points": ["пункт1", "пункт2"]},
        {"key": "theory", "title": "Теоретическая часть", "points": [...]},
        {"key": "analysis", "title": "Анализ предметной области", "points": [...]},
        {"key": "architecture", "title": "Архитектура системы", "points": [...]},
        {"key": "implementation", "title": "Реализация", "points": [...]},
        {"key": "testing", "title": "Тестирование", "points": [...]},
        {"key": "conclusion", "title": "Заключение", "points": [...]}
    ]
}"""

OUTLINE_V2_SYSTEM = """Ты методист-составитель планов для российских ВУЗов.
Создай детальное оглавление академической работы на основе ТЕМЫ и информации о проекте.

## ПРИНЦИПЫ КАЧЕСТВЕННОГО ОГЛАВЛЕНИЯ

### 1. Логика структуры
- От общего к частному: каждый раздел углубляет предыдущий
- Теория готовит к практике: теоретическая глава даёт базу для практической
- Каждая задача из введения = глава или раздел в основной части
- Названия КОНКРЕТНЫЕ по теме, НЕ абстрактные шаблоны

### 2. Введение (intro)
Введение — сплошной текст БЕЗ подзаголовков. В points укажи элементы:
- Актуальность темы (почему это важно сейчас)
- Цель работы (одна глобальная цель)
- Задачи работы (3-6 шагов к достижению цели, количество зависит от типа работы)
- Объект и предмет исследования
- Методы исследования
- Практическая значимость
- Структура работы

ВАЖНО: points должны быть КРАТКИМИ (2-10 слов), это просто пункты плана, а не полные предложения.

---

## СТРУКТУРЫ ПО ТИПАМ РАБОТ

ВАЖНО: ВСЕ типы работ имеют РОВНО 2 основные главы:
- Глава 1: Теоретическая часть (key="theory")
- Глава 2: Практическая часть (key="practice")

### РЕФЕРАТ (10-15 страниц)
Особенности: обзорная работа, БЕЗ subsections. Секции имеют только points.

Структура:
- Глава 1: Теоретическая часть (~45% объёма)
  - 1.1 Основные понятия и определения
  - 1.2 Классификация и виды
  - 1.3 Современные тенденции
- Глава 2: Практическая часть (~55% объёма)
  - 2.1 Области применения
  - 2.2 Практическое использование
  - 2.3 Перспективы развития

Пример JSON для реферата "Базы данных":
{
  "chapters": [
    {"key": "theory", "title": "1. Теоретическая часть", "sections": [
      {"key": "theory_1", "title": "1.1 Понятие и назначение баз данных", "points": [...]},
      {"key": "theory_2", "title": "1.2 Модели и структуры баз данных", "points": [...]},
      {"key": "theory_3", "title": "1.3 Системы управления базами данных", "points": [...]}
    ]},
    {"key": "practice", "title": "2. Практическая часть", "sections": [
      {"key": "practice_1", "title": "2.1 Области использования БД", "points": [...]},
      {"key": "practice_2", "title": "2.2 Проектирование базы данных", "points": [...]},
      {"key": "practice_3", "title": "2.3 Примеры применения и перспективы", "points": [...]}
    ]}
  ]
}

### КУРСОВАЯ РАБОТА (25-35 страниц)
Особенности: 2 главы с секциями (1.1, 1.2), БЕЗ subsections. Теория + практический пример.

Структура:
- Глава 1: Теоретическая часть (~40% объёма)
  - 1.1 Анализ предметной области и проблемы
  - 1.2 Обзор существующих решений
  - 1.3 Обоснование выбора подхода
- Глава 2: Практическая часть (~60% объёма)
  - 2.1 Постановка задачи и требования
  - 2.2 Проектирование системы
  - 2.3 Реализация основного функционала
  - 2.4 Тестирование и результаты

Пример JSON для курсовой "Разработка веб-приложения":
{
  "chapters": [
    {"key": "theory", "title": "1. Теоретическая часть", "sections": [
      {"key": "theory_1", "title": "1.1 Современные подходы к веб-разработке", "points": [...]},
      {"key": "theory_2", "title": "1.2 Сравнительный анализ фреймворков", "points": [...]},
      {"key": "theory_3", "title": "1.3 Выбор технологического стека", "points": [...]}
    ]},
    {"key": "practice", "title": "2. Практическая часть", "sections": [
      {"key": "practice_1", "title": "2.1 Функциональные требования и сценарии", "points": [...]},
      {"key": "practice_2", "title": "2.2 Проектирование архитектуры и БД", "points": [...]},
      {"key": "practice_3", "title": "2.3 Реализация клиентской и серверной части", "points": [...]},
      {"key": "practice_4", "title": "2.4 Тестирование и развёртывание", "points": [...]}
    ]}
  ]
}

### ДИПЛОМНАЯ РАБОТА (50-80 страниц)
Особенности: 2-3 главы с глубокой детализацией (1.1.1, 1.1.2), полный цикл разработки

Глава 1: Теоретическая часть
Принцип: ПРОБЛЕМА → АНАЛИЗ → ОБОСНОВАНИЕ
- 1.1 Проблематика и контекст
  - 1.1.1 Анализ текущей ситуации
  - 1.1.2 Типичные проблемы и ограничения
- 1.2 Обзор существующих подходов
  - 1.2.1 Первый подход/метод
  - 1.2.2 Второй подход/метод
  - 1.2.3 Сравнительный анализ
- 1.3 Выбор и обоснование решения

Глава 2: Практическая часть
Принцип: ПОСТАНОВКА → ПРОЕКТИРОВАНИЕ → РЕАЛИЗАЦИЯ → ТЕСТИРОВАНИЕ
- 2.1 Постановка задачи
  - 2.1.1 Функциональные требования
  - 2.1.2 Нефункциональные требования
- 2.2 Проектирование
  - 2.2.1 Архитектура системы
  - 2.2.2 Модель данных
  - 2.2.3 Пользовательские сценарии
- 2.3 Реализация
  - 2.3.1 Основные компоненты
  - 2.3.2 Ключевые алгоритмы
- 2.4 Тестирование
  - 2.4.1 Стратегия тестирования
  - 2.4.2 Результаты и оценка качества

---

## ПРАВИЛА НАЗВАНИЙ
1. Названия КОНКРЕТНЫЕ по теме работы:
   ❌ "Теоретические основы" (абстрактно)
   ✅ "Анализ методов автоматизации документооборота" (конкретно)

2. Ни один раздел НЕ называется как сама тема работы
3. Используй термины из предметной области (из facts)
4. Названия должны ясно указывать на содержание

## ФОРМАТ JSON

ОБЯЗАТЕЛЬНАЯ СТРУКТУРА: ровно 2 основные главы (theory + practice) + служебные:
{
    "version": "v2",
    "title": "Полное название работы",
    "work_type": "diploma|course|referat",
    "chapters": [
        {"key": "toc", "title": "Содержание", "is_auto": true},
        {"key": "intro", "title": "Введение", "points": [...]},
        {"key": "theory", "title": "1. Теоретическая часть", "sections": [
            {"key": "theory_1", "title": "1.1 Конкретное название раздела", "points": [...]}
        ]},
        {"key": "practice", "title": "2. Практическая часть", "sections": [
            {"key": "practice_1", "title": "2.1 Конкретное название раздела", "points": [...]}
        ]},
        {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
        {"key": "literature", "title": "Список литературы", "is_auto": true}
    ]
}

ВАЖНО: Названия глав theory и practice должны быть ТОЧНО "1. Теоретическая часть" и "2. Практическая часть" БЕЗ дополнительных подзаголовков. Конкретная тематика отражается в названиях РАЗДЕЛОВ (1.1, 1.2, 2.1, 2.2).

КРИТИЧНО: ТОЛЬКО 2 основные главы (key="theory" и key="practice"). НЕ создавай главы 3, 4, 5!
- Для РЕФЕРАТА: sections БЕЗ subsections, секции имеют только points
- Для КУРСОВОЙ: sections с points, БЕЗ subsections
- Для ДИПЛОМА: sections с subsections (1.1.1, 1.1.2)

ВАЖНО: Генерируй названия ИНДИВИДУАЛЬНО для каждой темы на основе facts и описания проекта."""

OUTLINE_V2_USER_TEMPLATE = """## ИНФОРМАЦИЯ О ПРОЕКТЕ (facts.json)
{facts_json}

## ПАРАМЕТРЫ РАБОТЫ
- Тип работы: {work_type_name}
- Тема: {topic_title}
- Описание: {topic_description}
- Целевой объём: {target_pages_min}-{target_pages_max} страниц
- Язык: русский

## ТРЕБОВАНИЯ К СТРУКТУРЕ
ОБЯЗАТЕЛЬНО 2 основные главы:
- Глава 1 (key="theory"): Теоретическая часть — {theory_count} раздела (~{theory_words_budget} слов)
- Глава 2 (key="practice"): Практическая часть — {practice_count} раздела (~{practice_words_budget} слов)
{subsections_note}

## ЗАДАЧА
Создай оглавление с РОВНО 2 основными главами (theory + practice), которое:
1. Отражает КОНКРЕТНУЮ тему "{topic_title}" — названия разделов должны быть специфичны для этой темы
2. Использует терминологию из facts (технологии, архитектура, модули проекта)
3. Следует логике: Проблема → Анализ → Решение → Реализация → Тестирование
4. Имеет связные переходы между разделами (теория готовит к практике)

## ВАЖНО ДЛЯ ВВЕДЕНИЯ
В points для intro укажи конкретные формулировки для данной темы:
- Актуальность: почему "{topic_title}" важно сейчас?
- Цель: что должно быть достигнуто?
- Задачи: какие шаги нужны для достижения цели?
- Объект: что изучается в широком смысле?
- Предмет: какой конкретный аспект?

Верни JSON с оглавлением."""

OUTLINE_USER_TEMPLATE = """На основе анализа репозитория:
{facts_json}

Создай план для {doc_type} на тему: {title}
Язык: {language}
Целевой объём: {target_pages} страниц
Дополнительные параметры: {params}
"""

MOCK_OUTLINE = {
    "title": "Анализ программного обеспечения",
    "sections": [
        {"key": "intro", "title": "Введение", "points": ["Актуальность", "Цели и задачи"]},
        {"key": "theory", "title": "Теоретическая часть", "points": ["Обзор технологий"]},
        {"key": "analysis", "title": "Анализ предметной области", "points": ["Требования", "Бизнес-логика"]},
        {"key": "architecture", "title": "Архитектура системы", "points": ["Компоненты", "Связи"]},
        {"key": "implementation", "title": "Реализация", "points": ["Алгоритмы", "Код"]},
        {"key": "testing", "title": "Тестирование", "points": ["Стратегия", "Результаты"]},
        {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
    ]
}

MOCK_OUTLINE_V2 = {
    "version": "v2",
    "title": "Анализ программного обеспечения",
    "work_type": "referat",
    "chapters": [
        {"key": "toc", "title": "Содержание", "is_auto": True},
        {"key": "intro", "title": "Введение", "points": ["Актуальность", "Цели и задачи"]},
        {
            "key": "theory",
            "title": "Теоретическая часть",
            "sections": [
                {
                    "key": "concepts",
                    "title": "1.1 Основные понятия и принципы",
                    "subsections": [
                        {"key": "concepts_definitions", "title": "1.1.1 Определения и терминология", "points": ["Ключевые термины"]},
                        {"key": "concepts_basics", "title": "1.1.2 Базовые концепции", "points": ["Фундаментальные принципы"]},
                    ]
                },
                {
                    "key": "approaches",
                    "title": "1.2 Подходы к решению задачи",
                    "subsections": [
                        {"key": "approaches_methods", "title": "1.2.1 Существующие методы", "points": ["Обзор подходов"]},
                        {"key": "approaches_choice", "title": "1.2.2 Критерии выбора", "points": ["Обоснование"]},
                    ]
                },
            ]
        },
        {
            "key": "practice",
            "title": "Практическая часть",
            "sections": [
                {"key": "analysis", "title": "2.1 Анализ предметной области", "points": ["Требования", "Бизнес-логика"]},
                {"key": "implementation", "title": "2.2 Практическое применение", "points": ["Реализация", "Результаты"]},
            ]
        },
        {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
        {"key": "literature", "title": "Список литературы", "is_auto": True},
    ]
}


PRACTICE_SECTION_KEYS = {'analysis', 'architecture', 'implementation', 'testing', 'design', 'development'}

def get_chapter_key_for_section(section_key: str) -> str:
    if section_key in ('intro', 'introduction'):
        return 'intro'
    elif section_key in ('theory', 'theoretical', 'concepts', 'technologies', 'literature_review'):
        return 'theory'
    elif section_key in PRACTICE_SECTION_KEYS:
        return 'practice'
    elif section_key in ('conclusion', 'conclusions', 'summary'):
        return 'conclusion'
    elif section_key in ('literature', 'references', 'bibliography'):
        return 'literature'
    elif section_key in ('toc', 'contents'):
        return 'toc'
    return section_key


def create_sections_from_outline(document: Document, outline_data: dict) -> list[Section]:
    existing_keys = set(document.sections.values_list('key', flat=True))
    created_sections = []
    order = 0

    if outline_data.get('version') == 'v2' or 'chapters' in outline_data:
        for chapter in outline_data.get('chapters', []):
            chapter_key = chapter.get('key', '')
            if chapter.get('is_auto'):
                continue

            if 'sections' in chapter:
                for sec in chapter['sections']:
                    sec_key = sec.get('key', '')
                    if sec_key and sec_key not in existing_keys:
                        section = Section.objects.create(
                            document=document,
                            key=sec_key,
                            chapter_key=chapter_key,
                            title=sec.get('title', sec_key),
                            order=order,
                            depth=2,
                        )
                        created_sections.append(section)
                        existing_keys.add(sec_key)
                        order += 1

                    if 'subsections' in sec:
                        for subsec in sec['subsections']:
                            subsec_key = subsec.get('key', '')
                            if subsec_key and subsec_key not in existing_keys:
                                subsection = Section.objects.create(
                                    document=document,
                                    key=subsec_key,
                                    chapter_key=chapter_key,
                                    parent_key=sec_key,
                                    title=subsec.get('title', subsec_key),
                                    order=order,
                                    depth=3,
                                )
                                created_sections.append(subsection)
                                existing_keys.add(subsec_key)
                                order += 1
            else:
                key = chapter_key
                if key and key not in existing_keys:
                    section = Section.objects.create(
                        document=document,
                        key=key,
                        chapter_key=chapter_key,
                        title=chapter.get('title', key),
                        order=order,
                        depth=1,
                    )
                    created_sections.append(section)
                    existing_keys.add(key)
                    order += 1
    else:
        for sec in outline_data.get('sections', []):
            key = sec.get('key', '')
            if key and key not in existing_keys:
                chapter_key = get_chapter_key_for_section(key)
                depth = 2 if chapter_key == 'practice' else 1
                section = Section.objects.create(
                    document=document,
                    key=key,
                    chapter_key=chapter_key,
                    title=sec.get('title', key),
                    order=order,
                    depth=depth,
                )
                created_sections.append(section)
                existing_keys.add(key)
                order += 1

    logger.info(f"Created {len(created_sections)} sections for document {document.id}")
    return created_sections


def get_facts(document: Document) -> dict:
    artifact = Artifact.objects.filter(
        analysis_run=document.analysis_run,
        kind=Artifact.Kind.FACTS
    ).order_by('-created_at').first()

    if not artifact or not artifact.data:
        raise ValueError(f"No facts for analysis_run {document.analysis_run_id}")
    return artifact.data


def ensure_outline(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
) -> DocumentArtifact:
    kind = ArtifactKind.OUTLINE.value

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)
        prof = get_profile(profile)

        if mock_mode:
            outline_data = MOCK_OUTLINE.copy()
            meta = {
                "mock": True,
                "profile": profile,
            }
        else:
            facts = get_facts(document)
            llm_client = LLMClient()

            user_prompt = OUTLINE_USER_TEMPLATE.format(
                facts_json=json.dumps(facts, ensure_ascii=False, indent=2)[:8000],
                doc_type=document.get_type_display(),
                title=document.params.get('title', 'Анализ программного обеспечения'),
                language=document.language,
                target_pages=document.target_pages,
                params=json.dumps(document.params, ensure_ascii=False)
            )

            outline_max_tokens = max(4000, prof.default_budget.max_output_tokens * 2)

            result = llm_client.generate_json(
                system=OUTLINE_SYSTEM,
                user=user_prompt,
                temperature=prof.default_budget.temperature * 0.5,
                max_tokens=outline_max_tokens,
            )
            outline_data = result.data
            meta = {
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": {
                    "prompt": result.meta.prompt_tokens,
                    "completion": result.meta.completion_tokens,
                    "total": result.meta.total_tokens
                },
                "cost_estimate": result.meta.cost_estimate,
                "profile": profile,
            }

        document.outline_current = None
        document.save(update_fields=['outline_current', 'updated_at'])

        return {
            "data_json": outline_data,
            "format": DocumentArtifact.Format.JSON,
            "meta": meta,
        }

    artifact = ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )

    document = Document.objects.get(id=document_id)
    if document.outline_current != artifact:
        document.outline_current = artifact
        document.save(update_fields=['outline_current', 'updated_at'])

    outline_data = artifact.data_json or {}
    create_sections_from_outline(document, outline_data)

    return artifact


def ensure_outline_v2(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
) -> DocumentArtifact:
    kind = ArtifactKind.OUTLINE_V2.value

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)
        prof = get_profile(profile)

        doc_profile = document.profile
        if not doc_profile:
            work_type = document.type
            topic_title = document.params.get('title', 'Анализ программного обеспечения')
            topic_description = document.params.get('description', '')
            target_pages_min = document.target_pages - 10
            target_pages_max = document.target_pages + 10
            style_level = 1
        else:
            work_type = doc_profile.work_type
            topic_title = doc_profile.topic_title
            topic_description = doc_profile.topic_description
            target_pages_min = doc_profile.target_pages_min
            target_pages_max = doc_profile.target_pages_max
            style_level = doc_profile.style_level

        preset = get_work_type_preset(work_type)

        if mock_mode:
            outline_data = MOCK_OUTLINE_V2.copy()
            outline_data['work_type'] = work_type
            outline_data['title'] = topic_title
            meta = {
                "mock": True,
                "profile": profile,
                "work_type": work_type,
            }
        else:
            facts = get_facts(document)
            clean_facts = sanitize_facts_for_llm(facts)
            llm_client = LLMClient()

            subsections_note = ""
            if preset.use_subsections:
                if work_type == 'referat':
                    subsections_note = "\nВАЖНО: Теоретические секции должны содержать subsections (2-3 подпункта на секцию). Общий объём ВСЕЙ теории: 1100-1500 слов.\n"
                else:
                    subsections_note = "\nВАЖНО: Теоретические секции должны содержать subsections (подпункты 1.1.1, 1.1.2, ...).\n"
            else:
                subsections_note = "\nВАЖНО: НЕ используй subsections - работа слишком короткая. Только sections с points.\n"

            user_prompt = OUTLINE_V2_USER_TEMPLATE.format(
                facts_json=json.dumps(clean_facts, ensure_ascii=False, indent=2)[:8000],
                work_type_name=preset.name,
                topic_title=topic_title,
                topic_description=topic_description or "Не указано",
                target_pages_min=target_pages_min,
                target_pages_max=target_pages_max,
                language=document.language,
                style_level=style_level,
                theory_count=preset.theory_depth,
                practice_count=preset.practice_depth,
                theory_words_budget=preset.theory_words_budget,
                practice_words_budget=preset.practice_words_budget,
                subsections_note=subsections_note,
            )

            logger.info(f"Generating outline v2 for document {document_id}")
            logger.debug(f"User prompt length: {len(user_prompt)} chars")

            if work_type == 'diploma':
                outline_max_tokens = 12000
            elif work_type == 'course':
                outline_max_tokens = 8000
            else:
                outline_max_tokens = 6000

            result = llm_client.generate_json(
                system=OUTLINE_V2_SYSTEM,
                user=user_prompt,
                temperature=min(0.8, prof.default_budget.temperature * 0.9),
                max_tokens=outline_max_tokens,
            )
            outline_data = result.data
            logger.info(f"Outline v2 generated successfully, {len(outline_data.get('chapters', []))} chapters")
            outline_data['version'] = 'v2'
            outline_data['work_type'] = work_type

            meta = {
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": {
                    "prompt": result.meta.prompt_tokens,
                    "completion": result.meta.completion_tokens,
                    "total": result.meta.total_tokens
                },
                "cost_estimate": result.meta.cost_estimate,
                "profile": profile,
                "work_type": work_type,
            }

        document.outline_current = None
        document.save(update_fields=['outline_current', 'updated_at'])

        return {
            "data_json": outline_data,
            "format": DocumentArtifact.Format.JSON,
            "meta": meta,
        }

    artifact = ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )

    document = Document.objects.get(id=document_id)
    if document.outline_current != artifact:
        document.outline_current = artifact
        document.save(update_fields=['outline_current', 'updated_at'])

    outline_data = artifact.data_json or {}
    create_sections_from_outline(document, outline_data)

    return artifact


def build_outline_v2_from_preset(
    work_type: str,
    topic_title: str,
    topic_description: str = "",
) -> dict[str, Any]:
    preset = get_work_type_preset(work_type)

    theory_sections = []
    practice_sections = []

    for i in range(preset.theory_sections_count):
        theory_sections.append({
            "key": f"theory_{i+1}",
            "title": f"1.{i+1} Раздел теоретической части {i+1}",
            "points": []
        })

    for i in range(preset.practice_sections_count):
        practice_sections.append({
            "key": f"practice_{i+1}",
            "title": f"2.{i+1} Раздел практической части {i+1}",
            "points": []
        })

    return {
        "version": "v2",
        "title": topic_title,
        "work_type": work_type,
        "chapters": [
            {"key": "toc", "title": "Содержание", "is_auto": True},
            {
                "key": "intro",
                "title": "Введение",
                "points": ["Актуальность", "Цель", "Задачи", "Объект и предмет", "Методы", "Значимость", "Структура"]
            },
            {
                "key": "theory",
                "title": "1. Теоретическая часть",
                "sections": theory_sections
            },
            {
                "key": "practice",
                "title": "2. Практическая часть",
                "sections": practice_sections
            },
            {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
            {"key": "literature", "title": "Список литературы", "is_auto": True},
            {"key": "appendix", "title": "Приложения", "is_auto": True},
        ]
    }
