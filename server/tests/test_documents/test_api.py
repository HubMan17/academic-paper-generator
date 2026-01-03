import uuid

import pytest
from rest_framework.test import APIClient

from apps.projects.models import Document, Section, AnalysisRun, Artifact, Project


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def analysis_run_with_facts(db):
    project = Project.objects.create(
        repo_url='https://github.com/test/repo',
        default_branch='main'
    )
    run = AnalysisRun.objects.create(
        project=project,
        status=AnalysisRun.Status.SUCCESS
    )
    Artifact.objects.create(
        analysis_run=run,
        kind=Artifact.Kind.FACTS,
        data={'test': 'facts'}
    )
    return run


@pytest.fixture
def document(analysis_run_with_facts):
    from services.documents import DocumentService
    service = DocumentService(mock_mode=True)
    return service.create_document(str(analysis_run_with_facts.id))


@pytest.mark.django_db
class TestDocumentAPI:
    def test_create_document(self, api_client, analysis_run_with_facts):
        response = api_client.post('/api/v1/documents/', {
            'analysis_run_id': str(analysis_run_with_facts.id),
            'params': {'title': 'Test'}
        }, format='json')
        assert response.status_code == 201
        assert 'id' in response.data

    def test_create_document_with_options(self, api_client, analysis_run_with_facts):
        response = api_client.post('/api/v1/documents/', {
            'analysis_run_id': str(analysis_run_with_facts.id),
            'params': {'title': 'Test'},
            'doc_type': 'diploma',
            'language': 'en-US',
            'target_pages': 60
        }, format='json')
        assert response.status_code == 201
        assert response.data['type'] == 'diploma'
        assert response.data['language'] == 'en-US'
        assert response.data['target_pages'] == 60

    def test_create_document_not_found(self, api_client):
        response = api_client.post('/api/v1/documents/', {
            'analysis_run_id': str(uuid.uuid4()),
        }, format='json')
        assert response.status_code == 404

    def test_get_document(self, api_client, document):
        response = api_client.get(f'/api/v1/documents/{document.id}/')
        assert response.status_code == 200
        assert response.data['id'] == str(document.id)

    def test_get_document_not_found(self, api_client):
        response = api_client.get(f'/api/v1/documents/{uuid.uuid4()}/')
        assert response.status_code == 404

    def test_get_outline_empty(self, api_client, document):
        response = api_client.get(f'/api/v1/documents/{document.id}/outline/')
        assert response.status_code == 200
        assert response.data['outline'] is None
        assert response.data['artifact_id'] is None

    def test_request_outline(self, api_client, document, mocker):
        mocker.patch('tasks.document_tasks.generate_outline_task.delay')
        response = api_client.post(f'/api/v1/documents/{document.id}/outline/')
        assert response.status_code == 202
        assert 'job_id' in response.data

    def test_list_sections(self, api_client, document):
        response = api_client.get(f'/api/v1/documents/{document.id}/sections/')
        assert response.status_code == 200
        assert len(response.data) == 5
        assert response.data[0]['key'] == 'intro'

    def test_get_section(self, api_client, document):
        response = api_client.get(f'/api/v1/documents/{document.id}/sections/intro/')
        assert response.status_code == 200
        assert response.data['key'] == 'intro'
        assert response.data['status'] == 'idle'

    def test_get_section_not_found(self, api_client, document):
        response = api_client.get(f'/api/v1/documents/{document.id}/sections/unknown/')
        assert response.status_code == 404

    def test_generate_section(self, api_client, document, mocker):
        mocker.patch('tasks.document_tasks.generate_section_task.delay')
        response = api_client.post(f'/api/v1/documents/{document.id}/sections/intro/generate/')
        assert response.status_code == 202
        assert 'job_id' in response.data

        document.refresh_from_db()
        section = document.sections.get(key='intro')
        assert section.status == 'queued'

    def test_generate_section_busy(self, api_client, document, mocker):
        mocker.patch('tasks.document_tasks.generate_section_task.delay')
        section = document.sections.get(key='intro')
        section.status = Section.Status.RUNNING
        section.save()

        response = api_client.post(f'/api/v1/documents/{document.id}/sections/intro/generate/')
        assert response.status_code == 409
        assert 'error' in response.data
