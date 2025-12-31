from celery import shared_task
from django.utils import timezone

from services.analyzer import RepoAnalyzer


@shared_task(bind=True, max_retries=3)
def run_analysis(self, job_id: str, repo_url: str) -> dict:
    from apps.projects.models import AnalysisRun, Artifact

    try:
        analysis_run = AnalysisRun.objects.get(id=job_id)
    except AnalysisRun.DoesNotExist:
        return {'error': f'AnalysisRun {job_id} not found'}

    analysis_run.status = AnalysisRun.Status.RUNNING
    analysis_run.started_at = timezone.now()
    analysis_run.progress = 0
    analysis_run.save(update_fields=['status', 'started_at', 'progress'])

    try:
        analysis_run.progress = 10
        analysis_run.save(update_fields=['progress'])

        analyzer = RepoAnalyzer(repo_url)

        analysis_run.progress = 30
        analysis_run.save(update_fields=['progress'])

        facts = analyzer.analyze()

        analysis_run.progress = 90
        analysis_run.save(update_fields=['progress'])

        if facts.get('repo', {}).get('commit'):
            analysis_run.commit_sha = facts['repo']['commit']

        Artifact.objects.create(
            analysis_run=analysis_run,
            kind=Artifact.Kind.FACTS,
            data=facts
        )

        analysis_run.status = AnalysisRun.Status.SUCCESS
        analysis_run.progress = 100
        analysis_run.finished_at = timezone.now()
        analysis_run.save(update_fields=['status', 'progress', 'finished_at', 'commit_sha'])

        return {
            'status': 'success',
            'job_id': job_id,
            'facts_stored': True
        }

    except Exception as exc:
        analysis_run.status = AnalysisRun.Status.FAILED
        analysis_run.error = str(exc)
        analysis_run.finished_at = timezone.now()
        analysis_run.save(update_fields=['status', 'error', 'finished_at'])

        if self.request.retries < self.max_retries:
            analysis_run.status = AnalysisRun.Status.QUEUED
            analysis_run.error = None
            analysis_run.save(update_fields=['status', 'error'])
            raise self.retry(exc=exc, countdown=60)

        return {
            'status': 'error',
            'job_id': job_id,
            'error': str(exc)
        }
