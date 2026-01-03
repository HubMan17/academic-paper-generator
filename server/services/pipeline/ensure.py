import hashlib
import logging
import traceback
from datetime import datetime
from typing import Any, Callable
from uuid import UUID

from django.db import transaction

from apps.projects.models import Document, DocumentArtifact, Section

logger = logging.getLogger(__name__)


class ArtifactStatus:
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


def compute_content_hash(data: Any) -> str:
    import json
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_success_artifact(document_id: UUID, kind: str) -> DocumentArtifact | None:
    try:
        artifact = DocumentArtifact.objects.filter(
            document_id=document_id,
            kind=kind,
            meta__status=ArtifactStatus.SUCCESS,
        ).order_by('-created_at').first()
        return artifact
    except DocumentArtifact.DoesNotExist:
        return None


def get_artifact_by_kind(document_id: UUID, kind: str) -> DocumentArtifact | None:
    return DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=kind,
    ).order_by('-created_at').first()


def list_section_kinds(document_id: UUID, prefix: str = "section:") -> list[str]:
    artifacts = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind__startswith=prefix,
        meta__status=ArtifactStatus.SUCCESS,
    ).values_list('kind', flat=True).distinct()
    return list(artifacts)


def get_latest_summaries(document_id: UUID, limit: int = 3) -> list[dict]:
    from services.pipeline.kinds import ArtifactKind

    sections = Section.objects.filter(
        document_id=document_id,
        status=Section.Status.SUCCESS,
    ).order_by('-order')[:limit]

    summaries = []
    for section in sections:
        kind = ArtifactKind.section_summary(section.key)
        artifact = get_success_artifact(document_id, kind)
        if artifact and artifact.data_json:
            summaries.append({
                "key": section.key,
                "title": section.title,
                "order": section.order,
                "bullets": artifact.data_json.get("bullets", []),
            })

    return summaries


def ensure_artifact(
    document_id: UUID,
    kind: str,
    builder_fn: Callable[[], dict[str, Any]],
    *,
    force: bool = False,
    job_id: UUID | None = None,
    section_key: str | None = None,
) -> DocumentArtifact:
    document = Document.objects.get(id=document_id)
    section = None
    if section_key:
        section = Section.objects.filter(document=document, key=section_key).first()

    if not force:
        existing = get_success_artifact(document_id, kind)
        if existing:
            logger.info(f"Using cached artifact: {kind} for document {document_id}")
            return existing

    artifact = DocumentArtifact.objects.create(
        document=document,
        section=section,
        job_id=job_id,
        kind=kind,
        format=DocumentArtifact.Format.JSON,
        source="pipeline",
        version="v1",
        meta={
            "status": ArtifactStatus.RUNNING,
            "started_at": datetime.utcnow().isoformat(),
        },
    )

    try:
        result = builder_fn()

        data_json = result.get("data_json")
        content_text = result.get("content_text")
        format_type = result.get("format", DocumentArtifact.Format.JSON)
        extra_meta = result.get("meta", {})

        content_hash = ""
        if data_json:
            content_hash = compute_content_hash(data_json)
        elif content_text:
            content_hash = compute_content_hash(content_text)

        with transaction.atomic():
            artifact.data_json = data_json
            artifact.content_text = content_text
            artifact.format = format_type
            artifact.hash = content_hash
            artifact.meta = {
                **artifact.meta,
                **extra_meta,
                "status": ArtifactStatus.SUCCESS,
                "finished_at": datetime.utcnow().isoformat(),
            }
            artifact.save()

        logger.info(f"Created artifact: {kind} for document {document_id}")
        return artifact

    except Exception as e:
        logger.error(f"Failed to create artifact {kind}: {e}")
        artifact.meta = {
            **artifact.meta,
            "status": ArtifactStatus.FAILED,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "finished_at": datetime.utcnow().isoformat(),
        }
        artifact.save()
        raise


def update_artifact_data(
    artifact: DocumentArtifact,
    data_json: dict | None = None,
    content_text: str | None = None,
    extra_meta: dict | None = None,
) -> DocumentArtifact:
    if data_json is not None:
        artifact.data_json = data_json
        artifact.hash = compute_content_hash(data_json)
    if content_text is not None:
        artifact.content_text = content_text
        if not data_json:
            artifact.hash = compute_content_hash(content_text)
    if extra_meta:
        artifact.meta = {**artifact.meta, **extra_meta}
    artifact.save()
    return artifact


def mark_artifact_success(artifact: DocumentArtifact) -> DocumentArtifact:
    artifact.meta = {
        **artifact.meta,
        "status": ArtifactStatus.SUCCESS,
        "finished_at": datetime.utcnow().isoformat(),
    }
    artifact.save()
    return artifact


def mark_artifact_failed(artifact: DocumentArtifact, error: str) -> DocumentArtifact:
    artifact.meta = {
        **artifact.meta,
        "status": ArtifactStatus.FAILED,
        "error": error,
        "finished_at": datetime.utcnow().isoformat(),
    }
    artifact.save()
    return artifact
