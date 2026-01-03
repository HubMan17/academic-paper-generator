import time
import uuid

from celery import shared_task
from django.utils import timezone

from apps.projects.models import Document, DocumentArtifact, Section
from services.documents import DocumentService


def _save_trace(document, steps: list, job_id: str = None):
    DocumentArtifact.objects.update_or_create(
        document=document,
        kind=DocumentArtifact.Kind.TRACE,
        job_id=uuid.UUID(job_id) if job_id else None,
        defaults={
            'format': DocumentArtifact.Format.JSON,
            'data_json': {'steps': steps},
            'source': 'document_tasks',
            'version': 'v1',
        }
    )


@shared_task(bind=True, max_retries=3)
def generate_outline_task(self, document_id: str, job_id: str = None):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return {'error': f'Document {document_id} not found'}

    steps = []
    start_time = time.time()

    try:
        service = DocumentService(mock_mode=False)
        artifact = service.generate_outline(document, job_id=job_id)

        steps.append({
            'name': 'outline',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - start_time) * 1000),
            'artifact_id': str(artifact.id),
        })
        _save_trace(document, steps, job_id)

        return {
            'status': 'success',
            'document_id': document_id,
            'artifact_id': str(artifact.id),
            'job_id': job_id
        }

    except Exception as exc:
        steps.append({
            'name': 'outline',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - start_time) * 1000),
            'error': str(exc),
        })
        _save_trace(document, steps, job_id)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(exc),
            'job_id': job_id
        }


@shared_task(bind=True, max_retries=3)
def generate_section_task(self, document_id: str, section_key: str, job_id: str = None):
    try:
        document = Document.objects.get(id=document_id)
        section = document.sections.get(key=section_key)
    except Document.DoesNotExist:
        return {'error': f'Document {document_id} not found'}
    except Section.DoesNotExist:
        return {'error': f'Section {section_key} not found'}

    steps = []
    service = DocumentService(mock_mode=False)

    try:
        step_start = time.time()
        context_pack_artifact = service.build_context_pack(document, section_key, job_id=job_id)
        steps.append({
            'name': f'context_pack:{section_key}',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - step_start) * 1000),
            'artifact_id': str(context_pack_artifact.id),
        })

        step_start = time.time()
        section_artifact = service.generate_section_text(document, section, job_id=job_id)
        steps.append({
            'name': f'section:{section_key}',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - step_start) * 1000),
            'artifact_id': str(section_artifact.id),
            'version': section.version,
        })

        step_start = time.time()
        summary_artifact = service.summarize_section(document, section, job_id=job_id)
        steps.append({
            'name': f'summary:{section_key}',
            'started_at': timezone.now().isoformat(),
            'ms': int((time.time() - step_start) * 1000),
            'artifact_id': str(summary_artifact.id),
        })

        _save_trace(document, steps, job_id)

        return {
            'status': 'success',
            'document_id': document_id,
            'section_key': section_key,
            'artifact_id': str(section_artifact.id),
            'context_pack_id': str(context_pack_artifact.id),
            'summary_id': str(summary_artifact.id),
            'version': section.version,
            'job_id': job_id
        }

    except Exception as exc:
        steps.append({
            'name': f'section:{section_key}',
            'started_at': timezone.now().isoformat(),
            'ms': 0,
            'error': str(exc),
        })
        _save_trace(document, steps, job_id)

        if self.request.retries < self.max_retries:
            section.status = Section.Status.QUEUED
            section.save(update_fields=['status', 'updated_at'])
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

        return {
            'status': 'error',
            'document_id': document_id,
            'section_key': section_key,
            'error': str(exc),
            'job_id': job_id
        }
