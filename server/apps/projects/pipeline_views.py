import uuid as uuid_module

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Document, DocumentArtifact, Project, AnalysisRun, Artifact, Section

from services.pipeline import (
    DocumentRunner,
    get_profile,
    list_profiles,
    get_success_artifact,
    ArtifactKind,
    get_all_section_keys,
    get_section_spec,
)
from services.pipeline.tasks import run_document_task, run_section_task, resume_document_task


@extend_schema(
    parameters=[
        OpenApiParameter(name='step', description='document | section | resume', required=True, type=str),
        OpenApiParameter(name='key', description='Section key (for step=section)', required=False, type=str),
        OpenApiParameter(name='profile', description='fast | default | heavy', required=False, type=str),
        OpenApiParameter(name='force', description='Force regeneration', required=False, type=bool),
    ],
    description="Run document pipeline. "
                "step=document: full document generation. "
                "step=section: single section (key required). "
                "step=resume: continue from last failed section.",
    tags=["Pipeline"]
)
@api_view(['POST'])
def run_pipeline(request, document_id):
    doc = get_object_or_404(Document, id=document_id)

    step = request.query_params.get('step', 'document')
    profile = request.query_params.get('profile', 'default')
    force = request.query_params.get('force', '').lower() in ('1', 'true', 'yes')

    try:
        get_profile(profile)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    job_id = str(uuid_module.uuid4())

    if step == 'document':
        run_document_task.delay(str(document_id), job_id, profile)
        return Response({
            'job_id': job_id,
            'step': step,
            'profile': profile,
            'status': 'queued',
        }, status=status.HTTP_202_ACCEPTED)

    elif step == 'section':
        key = request.query_params.get('key')
        if not key:
            return Response(
                {'error': 'key parameter is required for step=section'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if key not in get_all_section_keys():
            return Response(
                {'error': f'Unknown section key: {key}. Valid: {get_all_section_keys()}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        run_section_task.delay(str(document_id), key, job_id, profile, force)
        return Response({
            'job_id': job_id,
            'step': step,
            'key': key,
            'profile': profile,
            'force': force,
            'status': 'queued',
        }, status=status.HTTP_202_ACCEPTED)

    elif step == 'resume':
        resume_document_task.delay(str(document_id), job_id, profile)
        return Response({
            'job_id': job_id,
            'step': step,
            'profile': profile,
            'status': 'queued',
        }, status=status.HTTP_202_ACCEPTED)

    else:
        return Response(
            {'error': f'Unknown step: {step}. Valid: document, section, resume'},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    description="Get pipeline artifacts status for a document",
    tags=["Pipeline"]
)
@api_view(['GET'])
def pipeline_status(request, document_id):
    doc = get_object_or_404(Document, id=document_id)

    outline = get_success_artifact(document_id, ArtifactKind.OUTLINE.value)
    draft = get_success_artifact(document_id, ArtifactKind.DOCUMENT_DRAFT.value)
    toc = get_success_artifact(document_id, ArtifactKind.TOC.value)
    quality = get_success_artifact(document_id, ArtifactKind.QUALITY_REPORT.value)

    sections_status = []
    for key in get_all_section_keys():
        spec = get_section_spec(key)
        context_pack = get_success_artifact(document_id, ArtifactKind.context_pack(key))
        section = get_success_artifact(document_id, ArtifactKind.section(key))
        summary = get_success_artifact(document_id, ArtifactKind.section_summary(key))

        sections_status.append({
            'key': key,
            'title': spec.title if spec else key,
            'order': spec.order if spec else 0,
            'has_context_pack': context_pack is not None,
            'has_section': section is not None,
            'has_summary': summary is not None,
            'context_pack_id': str(context_pack.id) if context_pack else None,
            'section_id': str(section.id) if section else None,
            'summary_id': str(summary.id) if summary else None,
        })

    return Response({
        'document_id': str(document_id),
        'document_status': doc.status,
        'has_outline': outline is not None,
        'has_draft': draft is not None,
        'has_toc': toc is not None,
        'has_quality_report': quality is not None,
        'outline_id': str(outline.id) if outline else None,
        'draft_id': str(draft.id) if draft else None,
        'toc_id': str(toc.id) if toc else None,
        'quality_report_id': str(quality.id) if quality else None,
        'sections': sections_status,
    })


@extend_schema(
    description="Get document draft artifact",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_document_draft(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    draft = get_success_artifact(document_id, ArtifactKind.DOCUMENT_DRAFT.value)

    if not draft:
        return Response({'error': 'Document draft not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'artifact_id': str(draft.id),
        'created_at': draft.created_at.isoformat(),
        'data': draft.data_json,
    })


@extend_schema(
    description="Get TOC artifact",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_toc(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    toc = get_success_artifact(document_id, ArtifactKind.TOC.value)

    if not toc:
        return Response({'error': 'TOC not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'artifact_id': str(toc.id),
        'created_at': toc.created_at.isoformat(),
        'data': toc.data_json,
    })


@extend_schema(
    description="Get quality report artifact",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_quality_report(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    quality = get_success_artifact(document_id, ArtifactKind.QUALITY_REPORT.value)

    if not quality:
        return Response({'error': 'Quality report not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'artifact_id': str(quality.id),
        'created_at': quality.created_at.isoformat(),
        'passed': quality.meta.get('passed', False),
        'error_count': quality.meta.get('error_count', 0),
        'warning_count': quality.meta.get('warning_count', 0),
        'data': quality.data_json,
    })


@extend_schema(
    description="List available profiles",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_profiles(request):
    profiles = []
    for name in list_profiles():
        profile = get_profile(name)
        profiles.append({
            'name': profile.name,
            'description': profile.description,
            'target_words_multiplier': profile.target_words_multiplier,
            'max_facts': profile.max_facts,
            'summary_bullets': profile.summary_bullets,
        })
    return Response({'profiles': profiles})


@extend_schema(
    description="List pipeline section specs",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_pipeline_sections(request):
    sections = []
    for key in get_all_section_keys():
        spec = get_section_spec(key)
        if spec:
            sections.append({
                'key': spec.key,
                'title': spec.title,
                'order': spec.order,
                'required': spec.required,
                'depends_on': spec.depends_on,
                'target_words': spec.target_words,
                'fact_tags': spec.fact_tags,
                'outline_mode': spec.outline_mode.value,
                'needs_summaries': spec.needs_summaries,
            })
    return Response({'sections': sections})


@extend_schema(
    description="Run pipeline synchronously (for testing without Celery)",
    parameters=[
        OpenApiParameter(name='step', description='document | section', required=False, type=str),
        OpenApiParameter(name='key', description='Section key (for step=section)', required=False, type=str),
        OpenApiParameter(name='profile', description='fast | default | heavy', required=False, type=str),
    ],
    tags=["Pipeline"]
)
@api_view(['POST'])
def run_pipeline_sync(request, document_id):
    doc = get_object_or_404(Document, id=document_id)

    step = request.query_params.get('step', 'document')
    profile = request.query_params.get('profile', 'fast')
    key = request.query_params.get('key')

    try:
        get_profile(profile)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    runner = DocumentRunner(
        document_id=document_id,
        profile=profile,
        mock_mode=True,
    )

    job_id = uuid_module.uuid4()

    try:
        if step == 'document':
            result = runner.run_full(job_id=job_id, force=False)
        elif step == 'section':
            if not key:
                return Response({'error': 'key required for step=section'}, status=status.HTTP_400_BAD_REQUEST)
            result = runner.run_section(section_key=key, job_id=job_id, force=True)
        else:
            return Response({'error': f'Unknown step: {step}'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': result.success,
            'artifacts_created': result.artifacts_created,
            'artifacts_cached': result.artifacts_cached,
            'errors': result.errors,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    description="Create test document with sample facts for pipeline testing",
    tags=["Pipeline"]
)
@api_view(['POST'])
def create_test_document(request):
    project = Project.objects.create(
        repo_url="https://github.com/test/sample-repo",
    )

    analysis_run = AnalysisRun.objects.create(
        project=project,
        status=AnalysisRun.Status.SUCCESS,
    )

    Artifact.objects.create(
        analysis_run=analysis_run,
        kind=Artifact.Kind.FACTS,
        data={
            "repo": {
                "url": "https://github.com/test/sample-repo",
                "commit": "abc123def456",
                "detected_at": "2024-01-01T00:00:00Z",
            },
            "languages": [
                {"name": "Python", "ratio": 0.7, "lines_of_code": 5000},
                {"name": "JavaScript", "ratio": 0.2, "lines_of_code": 1500},
                {"name": "HTML", "ratio": 0.1, "lines_of_code": 500},
            ],
            "frameworks": [
                {"name": "Django", "type": "backend", "version": "5.0"},
                {"name": "Django REST Framework", "type": "backend", "version": "3.14"},
                {"name": "React", "type": "frontend", "version": "18.2"},
            ],
            "architecture": {
                "type": "layered",
                "layers": ["api", "services", "models"],
                "evidence": [
                    {"path": "server/apps/", "description": "Django apps"},
                    {"path": "server/services/", "description": "Business logic"},
                    {"path": "client/src/", "description": "React frontend"},
                ],
            },
            "modules": [
                {"path": "server/apps/core/", "type": "app", "name": "core"},
                {"path": "server/apps/projects/", "type": "app", "name": "projects"},
                {"path": "server/services/llm/", "type": "service", "name": "llm"},
                {"path": "server/services/analyzer/", "type": "service", "name": "analyzer"},
            ],
            "dependencies": {
                "backend": [
                    {"name": "django", "version": "5.0"},
                    {"name": "djangorestframework", "version": "3.14"},
                    {"name": "celery", "version": "5.3"},
                    {"name": "openai", "version": "1.0"},
                ],
                "frontend": [
                    {"name": "react", "version": "18.2"},
                    {"name": "tailwindcss", "version": "3.4"},
                ],
            },
            "api": {
                "endpoints": [
                    {"method": "POST", "path": "/api/v1/analyze/", "description": "Start analysis"},
                    {"method": "GET", "path": "/api/v1/jobs/{id}/", "description": "Get job status"},
                    {"method": "POST", "path": "/api/v1/documents/", "description": "Create document"},
                    {"method": "GET", "path": "/api/v1/documents/{id}/", "description": "Get document"},
                ],
            },
            "models": [
                {"name": "Project", "app": "projects", "fields": ["name", "repo_url"]},
                {"name": "Document", "app": "projects", "fields": ["type", "language", "status"]},
                {"name": "Section", "app": "projects", "fields": ["key", "title", "content"]},
            ],
            "testing": {
                "framework": "pytest",
                "coverage": 75,
                "test_count": 120,
            },
        }
    )

    document = Document.objects.create(
        analysis_run=analysis_run,
        type=Document.Type.COURSE,
        language="ru-RU",
        target_pages=40,
        params={
            "title": "Пояснительная записка к курсовой работе",
            "topic": "Разработка веб-приложения для генерации документов",
        },
    )

    for spec in get_all_section_keys():
        section_spec = get_section_spec(spec)
        if section_spec:
            Section.objects.create(
                document=document,
                key=spec,
                title=section_spec.title,
                order=section_spec.order,
                status=Section.Status.IDLE,
            )

    return Response({
        'document_id': str(document.id),
        'project_id': str(project.id),
        'analysis_run_id': str(analysis_run.id),
        'message': 'Test document created successfully',
    }, status=status.HTTP_201_CREATED)
