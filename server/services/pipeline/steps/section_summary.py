import logging
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.projects.models import Document, DocumentArtifact, Section
from services.llm import LLMClient
from services.pipeline.ensure import ensure_artifact, get_success_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import get_profile
from services.prompting import make_summary_request, parse_summary_response

logger = logging.getLogger(__name__)


def ensure_section_summary(
    document_id: UUID,
    section_key: str,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
) -> DocumentArtifact:
    kind = ArtifactKind.section_summary(section_key)
    prof = get_profile(profile)

    document = Document.objects.get(id=document_id)
    section = document.sections.get(key=section_key)

    section_artifact = get_success_artifact(document_id, ArtifactKind.section(section_key))
    if not section_artifact:
        raise ValueError(f"Section {section_key} must be generated before summarizing")

    section_text = section_artifact.content_text or section.text_current
    if not section_text:
        raise ValueError(f"Section {section_key} has no text to summarize")

    def builder() -> dict[str, Any]:
        min_bullets, max_bullets = prof.summary_bullets

        if mock_mode:
            bullets = [
                f"Ключевой пункт {i + 1} для секции {section_key}"
                for i in range(min_bullets)
            ]
            summary_text = "\n".join(f"- {b}" for b in bullets)
            meta = {
                "mock": True,
                "profile": profile,
                "bullet_count": len(bullets),
            }
        else:
            summary_request = make_summary_request(section_text, section_key)
            llm_client = LLMClient()

            result = llm_client.generate_text(
                system=summary_request["system"],
                user=summary_request["user"],
                temperature=0.3,
                max_tokens=500,
            )
            summary_text = result.text

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

        summary_data = parse_summary_response(summary_text, section_key)
        bullets = summary_data.get("bullets", [])

        if len(bullets) < min_bullets:
            logger.warning(f"Summary for {section_key} has only {len(bullets)} bullets, expected {min_bullets}")
        if len(bullets) > max_bullets:
            bullets = bullets[:max_bullets]
            summary_data["bullets"] = bullets

        meta["bullet_count"] = len(bullets)

        return {
            "data_json": summary_data,
            "content_text": summary_text,
            "format": DocumentArtifact.Format.JSON,
            "meta": meta,
        }

    artifact = ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
        section_key=section_key,
    )

    with transaction.atomic():
        section.summary_current = artifact.content_text or ""
        section.save(update_fields=['summary_current', 'updated_at'])

    return artifact
