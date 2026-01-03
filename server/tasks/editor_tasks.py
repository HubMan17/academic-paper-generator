import asyncio
import time
import uuid

from celery import shared_task
from django.utils import timezone

from apps.projects.models import Document, DocumentArtifact
from services.editor import EditorService, EditLevel
from services.editor.validator import quality_report_to_dict
from services.editor.assembler import document_edited_to_dict


def _save_trace(document, steps: list, job_id: str = None):
    DocumentArtifact.objects.update_or_create(
        document=document,
        kind=DocumentArtifact.Kind.TRACE,
        job_id=uuid.UUID(job_id) if job_id else None,
        defaults={
            'format': DocumentArtifact.Format.JSON,
            'data_json': {'steps': steps, 'pipeline': 'editor'},
            'source': 'editor_tasks',
            'version': 'v1',
        }
    )


@shared_task(bind=True, max_retries=2)
def run_editor_pipeline_task(
    self,
    document_id: str,
    level: int = 1,
    force: bool = False,
    job_id: str = None
):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return {'error': f'Document {document_id} not found'}

    steps = []
    start_time = time.time()

    try:
        service = EditorService()
        edit_level = EditLevel(level)

        result = asyncio.run(
            service.run_full_pipeline(
                document_id=uuid.UUID(document_id),
                level=edit_level,
                force=force,
            )
        )

        steps.append({
            'name': 'editor_pipeline',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - start_time) * 1000),
            'level': level,
            'sections_edited': len(result.sections),
            'transitions_count': len(result.transitions),
        })
        _save_trace(document, steps, job_id)

        return {
            'status': 'success',
            'document_id': document_id,
            'level': level,
            'sections_count': len(result.sections),
            'job_id': job_id,
        }

    except Exception as exc:
        steps.append({
            'name': 'editor_pipeline',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - start_time) * 1000),
            'error': str(exc),
        })
        _save_trace(document, steps, job_id)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1))

        document.status = Document.Status.ERROR
        document.save(update_fields=['status', 'updated_at'])

        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(exc),
            'job_id': job_id
        }


@shared_task(bind=True, max_retries=2)
def run_editor_analyze_task(self, document_id: str, job_id: str = None):
    from services.editor import analyze_document

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return {'error': f'Document {document_id} not found'}

    steps = []
    start_time = time.time()

    try:
        service = EditorService()
        sections = service._get_sections_data(document)

        quality_report = analyze_document(sections)

        artifact = DocumentArtifact.objects.create(
            document=document,
            kind=DocumentArtifact.Kind.QUALITY_REPORT,
            format=DocumentArtifact.Format.JSON,
            data_json=quality_report_to_dict(quality_report),
            version='v1',
            job_id=uuid.UUID(job_id) if job_id else None,
        )

        steps.append({
            'name': 'analyze',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - start_time) * 1000),
            'artifact_id': str(artifact.id),
        })
        _save_trace(document, steps, job_id)

        return {
            'status': 'success',
            'document_id': document_id,
            'artifact_id': str(artifact.id),
            'job_id': job_id,
            'total_chars': quality_report.total_chars,
            'total_words': quality_report.total_words,
            'style_markers': sum(quality_report.style_marker_counts.values()),
        }

    except Exception as exc:
        steps.append({
            'name': 'analyze',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - start_time) * 1000),
            'error': str(exc),
        })
        _save_trace(document, steps, job_id)

        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(exc),
            'job_id': job_id
        }
