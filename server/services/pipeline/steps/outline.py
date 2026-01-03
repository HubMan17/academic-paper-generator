import json
import logging
from typing import Any
from uuid import UUID

from apps.projects.models import Artifact, Document, DocumentArtifact
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

OUTLINE_V2_SYSTEM = """Ты технический писатель для академических работ.
Генерируй структурированный план документа в JSON формате v2.

ВАЖНО: Структура должна соответствовать указанному типу работы и содержать главы с секциями.

Формат ответа:
{
    "version": "v2",
    "title": "Название работы",
    "work_type": "diploma",
    "chapters": [
        {
            "key": "toc",
            "title": "Содержание",
            "is_auto": true
        },
        {
            "key": "intro",
            "title": "Введение",
            "points": ["Актуальность", "Цели и задачи", "Объект и предмет"]
        },
        {
            "key": "theory",
            "title": "Теоретическая часть",
            "sections": [
                {"key": "concepts", "title": "1.1 Основные понятия", "points": ["..."]},
                {"key": "technologies", "title": "1.2 Обзор технологий", "points": ["..."]}
            ]
        },
        {
            "key": "practice",
            "title": "Практическая часть",
            "sections": [
                {"key": "analysis", "title": "2.1 Анализ требований", "points": ["..."]},
                {"key": "architecture", "title": "2.2 Архитектура", "points": ["..."]},
                {"key": "implementation", "title": "2.3 Реализация", "points": ["..."]},
                {"key": "testing", "title": "2.4 Тестирование", "points": ["..."]}
            ]
        },
        {
            "key": "conclusion",
            "title": "Заключение",
            "points": ["Выводы", "Перспективы развития"]
        },
        {
            "key": "literature",
            "title": "Список литературы",
            "is_auto": true
        }
    ]
}"""

OUTLINE_V2_USER_TEMPLATE = """На основе анализа репозитория:
{facts_json}

Тип работы: {work_type_name}
Тема: {topic_title}
Описание: {topic_description}

Требования:
- Целевой объём: {target_pages_min}-{target_pages_max} страниц
- Язык: {language}
- Уровень стиля: {style_level}

Структура должна включать:
- Теоретическая часть: {theory_count} секций
- Практическая часть: {practice_count} секций

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
    "work_type": "course",
    "chapters": [
        {"key": "toc", "title": "Содержание", "is_auto": True},
        {"key": "intro", "title": "Введение", "points": ["Актуальность", "Цели и задачи"]},
        {
            "key": "theory",
            "title": "Теоретическая часть",
            "sections": [
                {"key": "concepts", "title": "1.1 Основные понятия", "points": ["Определения", "Терминология"]},
                {"key": "technologies", "title": "1.2 Обзор технологий", "points": ["Фреймворки", "Инструменты"]},
            ]
        },
        {
            "key": "practice",
            "title": "Практическая часть",
            "sections": [
                {"key": "analysis", "title": "2.1 Анализ требований", "points": ["Требования", "Бизнес-логика"]},
                {"key": "architecture", "title": "2.2 Архитектура", "points": ["Компоненты", "Связи"]},
                {"key": "implementation", "title": "2.3 Реализация", "points": ["Алгоритмы", "Код"]},
            ]
        },
        {"key": "conclusion", "title": "Заключение", "points": ["Выводы", "Перспективы"]},
        {"key": "literature", "title": "Список литературы", "is_auto": True},
    ]
}


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

            result = llm_client.generate_json(
                system=OUTLINE_SYSTEM,
                user=user_prompt,
                temperature=prof.default_budget.temperature * 0.5,
                max_tokens=prof.default_budget.max_output_tokens,
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
            )

            result = llm_client.generate_json(
                system=OUTLINE_V2_SYSTEM,
                user=user_prompt,
                temperature=prof.default_budget.temperature * 0.5,
                max_tokens=prof.default_budget.max_output_tokens,
            )
            outline_data = result.data
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

    for i, (key, title) in enumerate(preset.theory_sections):
        theory_sections.append({
            "key": key,
            "title": f"1.{i+1} {title}",
            "points": []
        })

    for i, (key, title) in enumerate(preset.practice_sections):
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
