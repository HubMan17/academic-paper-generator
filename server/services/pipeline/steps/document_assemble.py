import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.projects.models import Document, DocumentArtifact
from services.pipeline.ensure import ensure_artifact, get_success_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.schemas import (
    DocumentDraft, SectionDraft,
    document_draft_to_dict,
)
from services.pipeline.specs import get_all_section_keys

logger = logging.getLogger(__name__)


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def ensure_document_draft(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
) -> DocumentArtifact:
    kind = ArtifactKind.DOCUMENT_DRAFT.value

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)

        outline_artifact = get_success_artifact(document_id, ArtifactKind.OUTLINE.value)
        if not outline_artifact or not outline_artifact.data_json:
            raise ValueError(f"No outline found for document {document_id}")

        outline = outline_artifact.data_json
        title = outline.get("title", document.params.get("title", "Документ"))

        section_keys = get_all_section_keys()
        sections_draft: list[SectionDraft] = []

        for order, key in enumerate(section_keys, start=1):
            section_artifact = get_success_artifact(document_id, ArtifactKind.section(key))
            summary_artifact = get_success_artifact(document_id, ArtifactKind.section_summary(key))

            if not section_artifact:
                logger.warning(f"Section {key} not found, skipping")
                continue

            content_md = section_artifact.content_text or ""
            word_count = count_words(content_md)
            char_count = len(content_md)

            summary_bullets = []
            if summary_artifact and summary_artifact.data_json:
                summary_bullets = summary_artifact.data_json.get("bullets", [])

            sources_used = []
            if section_artifact.meta:
                sources_used = section_artifact.meta.get("sources_used", [])

            section_title = key
            for s in outline.get("sections", []):
                if s.get("key") == key:
                    section_title = s.get("title", key)
                    break

            sections_draft.append(SectionDraft(
                key=key,
                title=section_title,
                order=order,
                content_md=content_md,
                summary_bullets=summary_bullets,
                word_count=word_count,
                char_count=char_count,
                sources_used=sources_used,
            ))

        draft = DocumentDraft(
            document_id=str(document_id),
            title=title,
            outline=outline,
            sections=sections_draft,
            meta={
                "doc_type": document.type,
                "language": document.language,
                "target_pages": document.target_pages,
                "params": document.params,
            },
            created_at=datetime.utcnow(),
        )

        return {
            "data_json": document_draft_to_dict(draft),
            "format": DocumentArtifact.Format.JSON,
            "meta": {
                "section_count": len(sections_draft),
                "total_words": draft.total_words(),
                "total_chars": draft.total_chars(),
            },
        }

    return ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )
