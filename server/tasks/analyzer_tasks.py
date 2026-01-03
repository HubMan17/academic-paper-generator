import time
import traceback

from celery import shared_task
from django.utils import timezone

from services.analyzer import RepoAnalyzer
from services.analyzer.constants import ANALYZER_VERSION


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
    analysis_run.analyzer_version = ANALYZER_VERSION
    analysis_run.save(update_fields=['status', 'started_at', 'progress', 'analyzer_version'])

    Artifact.objects.create(
        analysis_run=analysis_run,
        kind=Artifact.Kind.META,
        source='run_analysis',
        version=ANALYZER_VERSION,
        data={
            'repo_url': repo_url,
            'branch': analysis_run.params.get('branch', 'main'),
            'fingerprint': analysis_run.fingerprint,
            'analyzer_version': ANALYZER_VERSION,
            'params': analysis_run.params,
        }
    )

    trace_steps = []
    current_step = None
    step_start = None

    def start_step(name: str):
        nonlocal current_step, step_start
        current_step = name
        step_start = time.time()

    def end_step(extra: dict = None):
        nonlocal trace_steps
        if current_step and step_start:
            step_data = {
                'name': current_step,
                'started_at': timezone.now().isoformat(),
                'ms': int((time.time() - step_start) * 1000),
            }
            if extra:
                step_data.update(extra)
            trace_steps.append(step_data)

    def save_trace():
        Artifact.objects.update_or_create(
            analysis_run=analysis_run,
            kind=Artifact.Kind.TRACE,
            defaults={
                'source': 'run_analysis',
                'version': ANALYZER_VERSION,
                'data': {'steps': trace_steps},
            }
        )

    try:
        start_step('ingest/clone')
        analysis_run.progress = 10
        analysis_run.save(update_fields=['progress'])

        analyzer = RepoAnalyzer(repo_url)
        end_step()

        start_step('extract/facts')
        analysis_run.progress = 30
        analysis_run.save(update_fields=['progress'])

        facts = analyzer.analyze()
        file_count = len(facts.get('tree', {}).get('modules', []))
        end_step({'files': file_count})

        analysis_run.progress = 90
        analysis_run.save(update_fields=['progress'])

        if facts.get('repo', {}).get('commit'):
            analysis_run.commit_sha = facts['repo']['commit']

        Artifact.objects.create(
            analysis_run=analysis_run,
            kind=Artifact.Kind.FACTS,
            source='analyzer',
            version=ANALYZER_VERSION,
            data=facts
        )

        save_trace()

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
        end_step({'error': str(exc)})
        save_trace()

        Artifact.objects.create(
            analysis_run=analysis_run,
            kind=Artifact.Kind.ERRORS,
            source='run_analysis',
            version=ANALYZER_VERSION,
            data={
                'step': current_step or 'unknown',
                'message': str(exc),
                'exception': type(exc).__name__,
                'traceback': traceback.format_exc(),
                'hint': _get_error_hint(exc),
            }
        )

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


def _get_error_hint(exc: Exception) -> str:
    msg = str(exc).lower()
    if 'clone' in msg or 'git' in msg:
        return 'Check repository access, URL validity, or authentication token'
    if 'permission' in msg or 'access' in msg:
        return 'Check file/repository permissions'
    if 'timeout' in msg:
        return 'Repository might be too large or network is slow'
    if 'not found' in msg or '404' in msg:
        return 'Repository or branch not found'
    return 'Check logs for details'
