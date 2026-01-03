import logging
from typing import Any
from uuid import UUID

from apps.projects.models import Document, DocumentArtifact
from services.enrichment import EnrichmentService, enrichment_report_to_dict
from services.pipeline.ensure import ensure_artifact
from services.pipeline.kinds import ArtifactKind

logger = logging.getLogger(__name__)

ENRICHMENT_REPORT_KIND = "enrichment_report:v1"


def ensure_enrichment(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    mock_mode: bool = False,
) -> DocumentArtifact:
    kind = ENRICHMENT_REPORT_KIND

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)

        if document.current_stage != Document.Stage.ENRICHMENT:
            document.current_stage = Document.Stage.ENRICHMENT
            document.status = Document.Status.ENRICHING
            document.save(update_fields=['current_stage', 'status', 'updated_at'])

        service = EnrichmentService(mock_mode=mock_mode)
        report = service.run_enrichment(document_id, job_id=job_id)

        return {
            "data_json": enrichment_report_to_dict(report),
            "format": DocumentArtifact.Format.JSON,
            "meta": {
                "sections_enriched": len(report.sections_enriched),
                "total_words_added": report.total_words_added,
                "total_facts_used": report.total_facts_used,
                "mock": mock_mode,
            },
        }

    artifact = ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )

    return artifact


def ensure_section_enrichment(
    document_id: UUID,
    section_key: str,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    mock_mode: bool = False,
) -> DocumentArtifact:
    kind = ArtifactKind.section_enriched(section_key)

    def builder() -> dict[str, Any]:
        from services.enrichment.schema import enrichment_result_to_dict

        service = EnrichmentService(mock_mode=mock_mode)
        result = service.enrich_single_section(document_id, section_key, job_id=job_id)

        return {
            "data_json": enrichment_result_to_dict(result),
            "content_text": result.enriched_text,
            "format": DocumentArtifact.Format.JSON,
            "meta": {
                "words_added": result.words_added,
                "facts_used": result.facts_used,
                "success": result.success,
                "mock": mock_mode,
            },
        }

    artifact = ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )

    return artifact
