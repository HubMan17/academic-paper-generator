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

OUTLINE_V2_SYSTEM = """Ты методист-составитель учебных планов для ВУЗов.
Создай детальный план работы, как это принято в российских университетах.

ВАЖНЫЕ ПРАВИЛА:
1. Структура должна соответствовать типу работы (реферат, курсовая, диплом).
2. Каждый раздел должен быть логически завершённым и понятным.
3. Названия разделов должны быть конкретными, не абстрактными.
4. Для курсовых и дипломов теория разбивается на подпункты (1.1.1, 1.1.2).
5. Для рефератов подпункты НЕ нужны - это короткая работа.

Формат JSON:
{
    "version": "v2",
    "title": "Название работы",
    "work_type": "course",
    "chapters": [
        {"key": "toc", "title": "Содержание", "is_auto": true},
        {
            "key": "intro",
            "title": "Введение",
            "points": ["Актуальность темы", "Цель и задачи работы", "Объект и предмет исследования"]
        },
        {
            "key": "theory",
            "title": "Теоретическая часть",
            "sections": [
                {
                    "key": "paradigms",
                    "title": "1.1 Парадигмы программирования и место ООП",
                    "subsections": [
                        {"key": "paradigms_intro", "title": "1.1.1 Понятие парадигмы программирования"},
                        {"key": "paradigms_oop", "title": "1.1.2 Причины появления объектно-ориентированного подхода"}
                    ]
                },
                {
                    "key": "oop_basics",
                    "title": "1.2 Базовые понятия ООП",
                    "subsections": [
                        {"key": "oop_class", "title": "1.2.1 Объект и класс"},
                        {"key": "oop_attrs", "title": "1.2.2 Атрибуты и методы"},
                        {"key": "oop_interface", "title": "1.2.3 Интерфейс и контракт"}
                    ]
                },
                {
                    "key": "oop_principles",
                    "title": "1.3 Основные принципы ООП",
                    "subsections": [
                        {"key": "encapsulation", "title": "1.3.1 Инкапсуляция"},
                        {"key": "inheritance", "title": "1.3.2 Наследование"},
                        {"key": "polymorphism", "title": "1.3.3 Полиморфизм"},
                        {"key": "abstraction", "title": "1.3.4 Абстракция"}
                    ]
                }
            ]
        },
        {
            "key": "practice",
            "title": "Практическая часть",
            "sections": [
                {"key": "analysis", "title": "2.1 Анализ требований", "points": ["..."]},
                {"key": "architecture", "title": "2.2 Архитектура системы", "points": ["..."]},
                {"key": "implementation", "title": "2.3 Реализация", "points": ["..."]},
                {"key": "testing", "title": "2.4 Тестирование", "points": ["..."]}
            ]
        },
        {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
        {"key": "literature", "title": "Список литературы", "is_auto": true}
    ]
}

ВАЖНО:
- Для курсовых и дипломов используй subsections для детализации теории.
- Для рефератов НЕ используй subsections - просто sections с points."""

OUTLINE_V2_USER_TEMPLATE = """На основе анализа репозитория:
{facts_json}

Тип работы: {work_type_name}
Тема: {topic_title}
Описание: {topic_description}

Требования:
- Целевой объём: {target_pages_min}-{target_pages_max} страниц
- Язык: {language}
- Уровень стиля: {style_level}

Бюджет по словам:
- Теоретическая часть: ~{theory_words_budget} слов ВСЕГО
- Практическая часть: ~{practice_words_budget} слов ВСЕГО

Структура должна включать:
- Теоретическая часть: {theory_count} секций
- Практическая часть: {practice_count} секций
{subsections_note}
Создай детальный план (outline) с конкретными пунктами (points) для каждой секции.
Пункты должны отражать реальное содержание на основе facts."""

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
                facts_json=json.dumps(facts, ensure_ascii=False, indent=2)[:8000],
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

            outline_max_tokens = max(4000, prof.default_budget.max_output_tokens * 2)

            result = llm_client.generate_json(
                system=OUTLINE_V2_SYSTEM,
                user=user_prompt,
                temperature=prof.default_budget.temperature * 0.5,
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
    sections = get_sections_for_work_type(work_type)

    theory_sections = []
    practice_sections = []

    for i, (key, title, _) in enumerate(preset.theory_sections):
        theory_sections.append({
            "key": key,
            "title": f"1.{i+1} {title}",
            "points": []
        })

    for i, (key, title, _) in enumerate(preset.practice_sections):
        practice_sections.append({
            "key": key,
            "title": f"2.{i+1} {title}",
            "points": []
        })

    return {
        "version": "v2",
        "title": topic_title,
        "work_type": work_type,
        "chapters": [
            {"key": "toc", "title": "Содержание", "is_auto": True},
            {"key": "intro", "title": "Введение", "points": ["Актуальность", "Цели и задачи"]},
            {
                "key": "theory",
                "title": "Теоретическая часть",
                "sections": theory_sections
            },
            {
                "key": "practice",
                "title": "Практическая часть",
                "sections": practice_sections
            },
            {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
            {"key": "literature", "title": "Список литературы", "is_auto": True},
        ]
    }
