import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.projects.models import Document, DocumentArtifact
from services.pipeline.ensure import ensure_artifact, get_success_artifact, get_outline_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.schemas import Toc, TocItem, toc_to_dict

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def extract_headings_from_markdown(content: str) -> list[tuple[int, str]]:
    headings = []
    for line in content.split('\n'):
        match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((level, title))
    return headings


def ensure_toc(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
) -> DocumentArtifact:
    kind = ArtifactKind.TOC.value

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)

        draft_artifact = get_success_artifact(document_id, ArtifactKind.DOCUMENT_DRAFT.value)
        if not draft_artifact or not draft_artifact.data_json:
            outline_artifact = get_outline_artifact(document_id)
            if not outline_artifact or not outline_artifact.data_json:
                raise ValueError(f"No outline or draft found for document {document_id}")

            return build_toc_from_outline(outline_artifact.data_json)

        return build_toc_from_draft(draft_artifact.data_json)

    return ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )


def build_toc_from_outline(outline: dict) -> dict[str, Any]:
    items = []

    for section in outline.get("sections", []):
        key = section.get("key", "")
        title = section.get("title", key)

        items.append(TocItem(
            level=1,
            title=title,
            section_key=key,
            anchor=slugify(title),
        ))

        for point in section.get("points", []):
            items.append(TocItem(
                level=2,
                title=point,
                section_key=key,
                anchor=slugify(point),
            ))

    toc = Toc(items=items, generated_at=datetime.utcnow())

    return {
        "data_json": toc_to_dict(toc),
        "format": DocumentArtifact.Format.JSON,
        "meta": {"source": "outline", "item_count": len(items)},
    }


def build_toc_from_draft(draft: dict) -> dict[str, Any]:
    items = []

    for section in draft.get("sections", []):
        key = section.get("key", "")
        title = section.get("title", key)
        content = section.get("content_md", "")

        items.append(TocItem(
            level=1,
            title=title,
            section_key=key,
            anchor=slugify(title),
        ))

        headings = extract_headings_from_markdown(content)
        for level, heading_title in headings:
            if level > 1:
                items.append(TocItem(
                    level=min(level, 3),
                    title=heading_title,
                    section_key=key,
                    anchor=slugify(heading_title),
                ))

    toc = Toc(items=items, generated_at=datetime.utcnow())

    return {
        "data_json": toc_to_dict(toc),
        "format": DocumentArtifact.Format.JSON,
        "meta": {"source": "draft", "item_count": len(items)},
    }
