from celery import shared_task

from apps.projects.models import Document, Section
from services.documents import DocumentService


@shared_task(bind=True, max_retries=3)
def generate_outline_task(self, document_id: str, job_id: str = None):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return {'error': f'Document {document_id} not found'}

    try:
        service = DocumentService(mock_mode=False)
        artifact = service.generate_outline(document, job_id=job_id)

        return {
            'status': 'success',
            'document_id': document_id,
            'artifact_id': str(artifact.id),
            'job_id': job_id
        }

    except Exception as exc:
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

    try:
        service = DocumentService(mock_mode=False)
        artifact = service.generate_section_text(document, section, job_id=job_id)

        return {
            'status': 'success',
            'document_id': document_id,
            'section_key': section_key,
            'artifact_id': str(artifact.id),
            'version': section.version,
            'job_id': job_id
        }

    except Exception as exc:
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
