import json
import logging
from typing import Any
from uuid import UUID

from apps.projects.models import Artifact, Document, DocumentArtifact
from services.llm import LLMClient
from services.pipeline.ensure import ensure_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import GenerationProfile, get_profile

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
