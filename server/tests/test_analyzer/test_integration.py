import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, AnalysisRun, Artifact
from apps.projects.views import _make_analysis_fingerprint
from services.analyzer.constants import ANALYZER_VERSION


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestFingerprint:
    def test_same_inputs_same_fingerprint(self):
        fp1 = _make_analysis_fingerprint('https://github.com/test/repo', 'main', {'branch': 'main'})
        fp2 = _make_analysis_fingerprint('https://github.com/test/repo', 'main', {'branch': 'main'})
        assert fp1 == fp2

    def test_different_branch_different_fingerprint(self):
        fp1 = _make_analysis_fingerprint('https://github.com/test/repo', 'main', {'branch': 'main'})
        fp2 = _make_analysis_fingerprint('https://github.com/test/repo', 'dev', {'branch': 'dev'})
        assert fp1 != fp2

    def test_different_repo_different_fingerprint(self):
        fp1 = _make_analysis_fingerprint('https://github.com/test/repo1', 'main', {'branch': 'main'})
        fp2 = _make_analysis_fingerprint('https://github.com/test/repo2', 'main', {'branch': 'main'})
        assert fp1 != fp2

    def test_fingerprint_is_64_chars(self):
        fp = _make_analysis_fingerprint('https://github.com/test/repo', 'main', {'branch': 'main'})
        assert len(fp) == 64


@pytest.mark.django_db
class TestAnalyzeCacheHit:
    def test_first_request_returns_202(self, api_client, mocker):
        mocker.patch('tasks.analyzer_tasks.run_analysis.delay')
        response = api_client.post('/api/v1/analyze/', {
            'repo_url': 'https://github.com/test/cache-test',
            'branch': 'main'
        }, format='json')
        assert response.status_code == 202
        assert response.data['cached'] is False
        assert 'job_id' in response.data

    def test_cache_hit_returns_200(self, api_client, mocker):
        mocker.patch('tasks.analyzer_tasks.run_analysis.delay')

        response1 = api_client.post('/api/v1/analyze/', {
            'repo_url': 'https://github.com/test/cache-hit',
            'branch': 'main'
        }, format='json')
        job_id = str(response1.data['job_id'])

        run = AnalysisRun.objects.get(id=job_id)
        run.status = AnalysisRun.Status.SUCCESS
        run.save()

        response2 = api_client.post('/api/v1/analyze/', {
            'repo_url': 'https://github.com/test/cache-hit',
            'branch': 'main'
        }, format='json')

        assert response2.status_code == 200
        assert response2.data['cached'] is True
        assert str(response2.data['job_id']) == job_id

    def test_force_ignores_cache(self, api_client, mocker):
        mocker.patch('tasks.analyzer_tasks.run_analysis.delay')

        response1 = api_client.post('/api/v1/analyze/', {
            'repo_url': 'https://github.com/test/force-test',
            'branch': 'main'
        }, format='json')
        job_id1 = str(response1.data['job_id'])

        run = AnalysisRun.objects.get(id=job_id1)
        run.status = AnalysisRun.Status.SUCCESS
        run.save()

        response2 = api_client.post('/api/v1/analyze/?force=1', {
            'repo_url': 'https://github.com/test/force-test',
            'branch': 'main'
        }, format='json')

        assert response2.status_code == 202
        assert response2.data['cached'] is False
        assert str(response2.data['job_id']) != job_id1


@pytest.mark.django_db
class TestArtifactsCreated:
    def test_success_creates_artifacts(self, api_client, mocker):
        from tasks.analyzer_tasks import run_analysis

        mocker.patch('services.analyzer.RepoAnalyzer.analyze', return_value={
            'repo': {'commit': 'abc123'},
            'tree': {'modules': [{'path': 'main.py'}]},
            'stack': {'languages': {'Python': 100}}
        })
        mocker.patch('services.analyzer.RepoAnalyzer.__init__', return_value=None)

        project = Project.objects.create(repo_url='https://github.com/test/artifacts')
        run = AnalysisRun.objects.create(
            project=project,
            fingerprint='test-fp',
            params={'branch': 'main'}
        )

        result = run_analysis(str(run.id), 'https://github.com/test/artifacts')

        assert result['status'] == 'success'

        run.refresh_from_db()
        assert run.status == AnalysisRun.Status.SUCCESS

        artifacts = Artifact.objects.filter(analysis_run=run)
        kinds = set(a.kind for a in artifacts)

        assert Artifact.Kind.FACTS in kinds
        assert Artifact.Kind.META in kinds
        assert Artifact.Kind.TRACE in kinds

    def test_meta_artifact_has_info(self, db, mocker):
        from tasks.analyzer_tasks import run_analysis

        mocker.patch('services.analyzer.RepoAnalyzer.analyze', return_value={
            'repo': {'commit': 'abc123'},
            'tree': {'modules': []},
            'stack': {'languages': {'Python': 100}}
        })
        mocker.patch('services.analyzer.RepoAnalyzer.__init__', return_value=None)

        project = Project.objects.create(repo_url='https://github.com/test/meta-check')
        run = AnalysisRun.objects.create(
            project=project,
            fingerprint='test-meta',
            params={'branch': 'main'}
        )

        run_analysis.apply(args=(str(run.id), 'https://github.com/test/meta-check'))

        meta = Artifact.objects.filter(analysis_run=run, kind=Artifact.Kind.META).first()
        assert meta is not None
        assert 'repo_url' in meta.data
        assert 'fingerprint' in meta.data
        assert 'analyzer_version' in meta.data


@pytest.mark.django_db
class TestRunStepEndpoint:
    def test_run_step_requires_debug(self, api_client, settings, mocker):
        mocker.patch('tasks.analyzer_tasks.run_analysis.delay')
        settings.DEBUG = False

        project = Project.objects.create(repo_url='https://github.com/test/step')
        run = AnalysisRun.objects.create(project=project, fingerprint='test')

        response = api_client.post(f'/api/v1/jobs/{run.id}/run/?step=extract')
        assert response.status_code == 403

    def test_run_step_extract(self, api_client, settings, mocker):
        mocker.patch('tasks.analyzer_tasks.run_analysis.delay')
        settings.DEBUG = True

        project = Project.objects.create(repo_url='https://github.com/test/step-extract')
        run = AnalysisRun.objects.create(project=project, fingerprint='test')

        response = api_client.post(f'/api/v1/jobs/{run.id}/run/?step=extract')
        assert response.status_code == 202
        assert response.data['step'] == 'extract'
