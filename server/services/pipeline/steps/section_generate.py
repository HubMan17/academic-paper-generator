import logging
import re
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.projects.models import Document, DocumentArtifact, Section
from services.llm import LLMClient
from services.pipeline.ensure import ensure_artifact, get_success_artifact, invalidate_assembly_artifacts
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import get_profile
from services.pipeline.specs import get_section_spec

logger = logging.getLogger(__name__)

MOCK_SECTION_TEXT = """# {title}

Это тестовый контент для секции **{key}**.

## Содержание

Данный раздел содержит описание {key} части работы.
Текст сгенерирован в режиме MOCK для тестирования.

### Основные пункты

1. Первый пункт раздела
2. Второй пункт раздела
3. Третий пункт раздела

Более подробное содержание будет добавлено при реальной генерации.
"""


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def ensure_section(
    document_id: UUID,
    section_key: str,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
) -> DocumentArtifact:
    from services.pipeline.steps.context_pack import ensure_context_pack

    section_kind = ArtifactKind.section(section_key)
    trace_kind = ArtifactKind.llm_trace(section_key)
    prof = get_profile(profile)
    spec = get_section_spec(section_key)

    document = Document.objects.get(id=document_id)
    section = document.sections.get(key=section_key)

    section.status = Section.Status.RUNNING
    section.save(update_fields=['status', 'updated_at'])

    def builder() -> dict[str, Any]:
        context_pack_artifact = get_success_artifact(document_id, ArtifactKind.context_pack(section_key))
        if not context_pack_artifact:
            context_pack_artifact = ensure_context_pack(
                document_id=document_id,
                section_key=section_key,
                force=False,
                job_id=job_id,
                profile=profile,
            )

        if mock_mode:
            title = spec.title if spec else section.title
            content_text = MOCK_SECTION_TEXT.format(title=title, key=section_key)
            meta = {
                "mock": True,
                "profile": profile,
                "context_pack_artifact_id": str(context_pack_artifact.id),
            }
            llm_trace_data = None
        else:
            rendered_prompt = context_pack_artifact.data_json.get("rendered_prompt", {})
            system_prompt = rendered_prompt.get("system", "")
            user_prompt = rendered_prompt.get("user", "")

            if not user_prompt:
                raise ValueError(f"No rendered_prompt in context_pack for section {section_key}")

            budget = prof.get_budget_for_section(section_key)
            llm_client = LLMClient()

            result = llm_client.generate_text(
                system=system_prompt,
                user=user_prompt,
                temperature=budget.temperature,
                max_tokens=budget.max_output_tokens,
            )
            content_text = result.text

            estimated_tokens = context_pack_artifact.data_json.get("budget", {}).get("estimated_input_tokens")
            actual_tokens = result.meta.prompt_tokens or 0
            estimation_error = None
            if estimated_tokens and estimated_tokens > 0 and actual_tokens > 0:
                estimation_error = round((actual_tokens / estimated_tokens) - 1.0, 3)

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
                "context_pack_artifact_id": str(context_pack_artifact.id),
            }

            llm_trace_data = {
                "operation": "section_generate",
                "section_key": section_key,
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": meta["tokens"],
                "cost_estimate": result.meta.cost_estimate,
                "estimated_input_tokens": estimated_tokens,
                "estimation_error_ratio": estimation_error,
                "context_pack_artifact_id": str(context_pack_artifact.id),
            }

        word_count = count_words(content_text)
        char_count = len(content_text)

        sources_used = context_pack_artifact.data_json.get("selected_facts", {}).get("keys", [])

        if llm_trace_data:
            DocumentArtifact.objects.create(
                document=document,
                section=section,
                job_id=job_id,
                kind=trace_kind,
                format=DocumentArtifact.Format.JSON,
                data_json=llm_trace_data,
                source="llm",
                version="v1",
                meta={"status": "success"},
            )

        return {
            "content_text": content_text,
            "format": DocumentArtifact.Format.MARKDOWN,
            "meta": {
                **meta,
                "word_count": word_count,
                "char_count": char_count,
                "sources_used": sources_used,
            },
        }

    try:
        existing_artifact = get_success_artifact(document_id, section_kind)

        artifact = ensure_artifact(
            document_id=document_id,
            kind=section_kind,
            builder_fn=builder,
            force=force,
            job_id=job_id,
            section_key=section_key,
        )

        is_new_artifact = artifact.id != (existing_artifact.id if existing_artifact else None)

        if is_new_artifact:
            invalidated = invalidate_assembly_artifacts(document_id)
            if invalidated:
                logger.info(f"Section {section_key} regenerated, invalidated: {invalidated}")

        with transaction.atomic():
            section.text_current = artifact.content_text or ""
            section.version += 1
            section.last_artifact = artifact
            section.status = Section.Status.SUCCESS
            section.last_error = ""
            section.save(update_fields=[
                'text_current', 'version', 'last_artifact',
                'status', 'last_error', 'updated_at'
            ])

        return artifact

    except Exception as e:
        section.status = Section.Status.FAILED
        section.last_error = str(e)[:1000]
        section.save(update_fields=['status', 'last_error', 'updated_at'])
        raise
