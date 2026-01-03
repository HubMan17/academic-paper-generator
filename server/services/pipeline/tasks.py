import logging
from uuid import UUID

from celery import shared_task

from apps.projects.models import Document

logger = logging.getLogger(__name__)


def update_document_progress(document_id: UUID, progress: int, message: str):
    try:
        Document.objects.filter(id=document_id).update(
            status=Document.Status.GENERATING if progress < 100 else Document.Status.READY,
        )
    except Exception as e:
        logger.warning(f"Failed to update document progress: {e}")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def run_document_task(self, document_id: str, job_id: str, profile: str = "default"):
    from services.pipeline import DocumentRunner

    logger.info(f"Starting document generation: {document_id}, job: {job_id}, profile: {profile}")

    def progress_callback(progress: int, message: str):
        update_document_progress(UUID(document_id), progress, message)
        self.update_state(state='PROGRESS', meta={'progress': progress, 'message': message})

    try:
        Document.objects.filter(id=document_id).update(status=Document.Status.GENERATING)

        runner = DocumentRunner(
            document_id=UUID(document_id),
            profile=profile,
            mock_mode=False,
            progress_callback=progress_callback,
        )

        result = runner.run_full(job_id=UUID(job_id), force=False)

        if result.success:
            Document.objects.filter(id=document_id).update(status=Document.Status.READY)
            logger.info(f"Document generation complete: {document_id}")
        else:
            Document.objects.filter(id=document_id).update(status=Document.Status.ERROR)
            logger.error(f"Document generation failed: {result.errors}")

        return {
            "success": result.success,
            "document_id": result.document_id,
            "artifacts_created": result.artifacts_created,
            "artifacts_cached": result.artifacts_cached,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
        }

    except Exception as e:
        logger.exception(f"Document generation failed: {e}")
        Document.objects.filter(id=document_id).update(status=Document.Status.ERROR)
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def run_section_task(
    self,
    document_id: str,
    section_key: str,
    job_id: str,
    profile: str = "default",
    force: bool = False,
):
    from services.pipeline import DocumentRunner

    logger.info(f"Starting section generation: {document_id}/{section_key}, job: {job_id}")

    def progress_callback(progress: int, message: str):
        self.update_state(state='PROGRESS', meta={'progress': progress, 'message': message})

    try:
        runner = DocumentRunner(
            document_id=UUID(document_id),
            profile=profile,
            mock_mode=False,
            progress_callback=progress_callback,
        )

        result = runner.run_section(
            section_key=section_key,
            job_id=UUID(job_id),
            force=force,
        )

        logger.info(f"Section generation complete: {document_id}/{section_key}")

        return {
            "success": result.success,
            "document_id": result.document_id,
            "section_key": section_key,
            "artifacts_created": result.artifacts_created,
            "artifacts_cached": result.artifacts_cached,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
        }

    except Exception as e:
        logger.exception(f"Section generation failed: {e}")
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def resume_document_task(self, document_id: str, job_id: str, profile: str = "default"):
    from services.pipeline import DocumentRunner

    logger.info(f"Resuming document generation: {document_id}, job: {job_id}")

    def progress_callback(progress: int, message: str):
        update_document_progress(UUID(document_id), progress, message)
        self.update_state(state='PROGRESS', meta={'progress': progress, 'message': message})

    try:
        Document.objects.filter(id=document_id).update(status=Document.Status.GENERATING)

        runner = DocumentRunner(
            document_id=UUID(document_id),
            profile=profile,
            mock_mode=False,
            progress_callback=progress_callback,
        )

        result = runner.resume(job_id=UUID(job_id))

        if result.success:
            Document.objects.filter(id=document_id).update(status=Document.Status.READY)
            logger.info(f"Document resume complete: {document_id}")
        else:
            Document.objects.filter(id=document_id).update(status=Document.Status.ERROR)
            logger.error(f"Document resume failed: {result.errors}")

        return {
            "success": result.success,
            "document_id": result.document_id,
            "artifacts_created": result.artifacts_created,
            "artifacts_cached": result.artifacts_cached,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
        }

    except Exception as e:
        logger.exception(f"Document resume failed: {e}")
        Document.objects.filter(id=document_id).update(status=Document.Status.ERROR)
        raise
