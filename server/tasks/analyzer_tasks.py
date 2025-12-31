from celery import shared_task

from services.analyzer import RepoAnalyzer


@shared_task(bind=True, max_retries=3)
def analyze_repository(self, repo_url: str) -> dict:
    try:
        analyzer = RepoAnalyzer(repo_url)
        return analyzer.analyze()
    except Exception as exc:
        self.retry(exc=exc, countdown=60)
