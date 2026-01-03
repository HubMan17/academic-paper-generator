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
from services.editor import (
    EditorService,
    EditLevel,
)


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

    edited = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=DocumentArtifact.Kind.DOCUMENT_EDITED
    ).first()
    glossary = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=DocumentArtifact.Kind.GLOSSARY
    ).first()
    edit_plan = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=DocumentArtifact.Kind.EDIT_PLAN
    ).first()

    sections_status = []
    for key in get_all_section_keys():
        spec = get_section_spec(key)
        context_pack = get_success_artifact(document_id, ArtifactKind.context_pack(key))
        section = get_success_artifact(document_id, ArtifactKind.section(key))
        summary = get_success_artifact(document_id, ArtifactKind.section_summary(key))
        section_edited = DocumentArtifact.objects.filter(
            document_id=document_id,
            section__key=key,
            kind=DocumentArtifact.Kind.SECTION_EDITED
        ).first()

        sections_status.append({
            'key': key,
            'title': spec.title if spec else key,
            'order': spec.order if spec else 0,
            'has_context_pack': context_pack is not None,
            'has_section': section is not None,
            'has_summary': summary is not None,
            'has_edited': section_edited is not None,
            'context_pack_id': str(context_pack.id) if context_pack else None,
            'section_id': str(section.id) if section else None,
            'summary_id': str(summary.id) if summary else None,
            'edited_id': str(section_edited.id) if section_edited else None,
        })

    return Response({
        'document_id': str(document_id),
        'document_status': doc.status,
        'has_outline': outline is not None,
        'has_draft': draft is not None,
        'has_toc': toc is not None,
        'has_quality_report': quality is not None,
        'has_edited': edited is not None,
        'has_glossary': glossary is not None,
        'has_edit_plan': edit_plan is not None,
        'outline_id': str(outline.id) if outline else None,
        'draft_id': str(draft.id) if draft else None,
        'toc_id': str(toc.id) if toc else None,
        'quality_report_id': str(quality.id) if quality else None,
        'edited_id': str(edited.id) if edited else None,
        'glossary_id': str(glossary.id) if glossary else None,
        'edit_plan_id': str(edit_plan.id) if edit_plan else None,
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
        OpenApiParameter(name='step', description='document | section | analyze | edit', required=False, type=str),
        OpenApiParameter(name='key', description='Section key (for step=section)', required=False, type=str),
        OpenApiParameter(name='profile', description='fast | default | heavy', required=False, type=str),
        OpenApiParameter(name='level', description='Edit level 1-3 (for step=edit)', required=False, type=int),
    ],
    tags=["Pipeline"]
)
@api_view(['POST'])
def run_pipeline_sync(request, document_id):
    from asgiref.sync import async_to_sync

    doc = get_object_or_404(Document, id=document_id)

    step = request.query_params.get('step', 'document')
    profile = request.query_params.get('profile', 'fast')
    key = request.query_params.get('key')
    level = int(request.query_params.get('level', 1))

    if step == 'analyze':
        service = EditorService()
        quality_report, artifact = service.run_analyze_only(doc)

        return Response({
            'success': True,
            'artifact_id': str(artifact.id),
            'total_chars': quality_report.total_chars,
            'total_words': quality_report.total_words,
            'style_markers': sum(quality_report.style_marker_counts.values()),
            'global_repeats': len(quality_report.global_repeats),
        })

    if step == 'edit':
        if level not in [1, 2, 3]:
            return Response({'error': 'level must be 1, 2, or 3'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            service = EditorService()
            edit_level = EditLevel(level)

            result = async_to_sync(service.run_full_pipeline)(
                document_id=document_id,
                level=edit_level,
                force=False,
            )

            return Response({
                'success': True,
                'sections_edited': len(result.sections),
                'transitions_count': len(result.transitions),
                'chapter_conclusions': len(result.chapter_conclusions),
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    description="Get edited document artifact",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_document_edited(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    edited = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=DocumentArtifact.Kind.DOCUMENT_EDITED
    ).order_by('-created_at').first()

    if not edited:
        return Response({'error': 'Edited document not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'artifact_id': str(edited.id),
        'created_at': edited.created_at.isoformat(),
        'data': edited.data_json,
    })


@extend_schema(
    description="Get glossary artifact",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_glossary(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    glossary = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=DocumentArtifact.Kind.GLOSSARY
    ).order_by('-created_at').first()

    if not glossary:
        return Response({'error': 'Glossary not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'artifact_id': str(glossary.id),
        'created_at': glossary.created_at.isoformat(),
        'data': glossary.data_json,
    })


@extend_schema(
    description="Get edit plan artifact",
    tags=["Pipeline"]
)
@api_view(['GET'])
def get_edit_plan(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    edit_plan = DocumentArtifact.objects.filter(
        document_id=document_id,
        kind=DocumentArtifact.Kind.EDIT_PLAN
    ).order_by('-created_at').first()

    if not edit_plan:
        return Response({'error': 'Edit plan not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'artifact_id': str(edit_plan.id),
        'created_at': edit_plan.created_at.isoformat(),
        'data': edit_plan.data_json,
    })


@extend_schema(
    description="Create test document with sample facts for pipeline testing",
    tags=["Pipeline"]
)
@api_view(['POST'])
def create_test_document(request):
    project = Project.objects.create(
        repo_url="https://github.com/HubMan17/academic-paper-generator",
    )

    analysis_run = AnalysisRun.objects.create(
        project=project,
        status=AnalysisRun.Status.SUCCESS,
    )

    Artifact.objects.create(
        analysis_run=analysis_run,
        kind=Artifact.Kind.FACTS,
        data={
            "schema": "facts.v1",
            "repo": {
                "url": "https://github.com/HubMan17/academic-paper-generator",
                "commit": "8802cc6a07a73677ae3c2ed490a2fa383ff1bd69",
                "detected_at": "2026-01-03T20:37:18.786192Z",
            },
            "languages": [
                {"name": "Python", "ratio": 0.97, "lines_of_code": 5704, "evidence": [{"path": "*.py"}]},
                {"name": "TypeScript", "ratio": 0.03, "lines_of_code": 158, "evidence": [{"path": "*.ts"}, {"path": "*.tsx"}]},
                {"name": "JavaScript", "ratio": 0, "lines_of_code": 16, "evidence": [{"path": "*.js"}, {"path": "*.jsx"}]},
            ],
            "frameworks": [
                {"name": "Django", "type": "web", "evidence": [{"path": "server/requirements.txt"}]},
                {"name": "Celery", "type": "task-queue", "evidence": [{"path": "server/requirements.txt"}]},
                {"name": "pytest", "type": "testing", "evidence": [{"path": "server/requirements.txt"}]},
                {"name": "React", "type": "frontend", "evidence": [{"path": "client/package.json"}]},
                {"name": "TailwindCSS", "type": "styling", "evidence": [{"path": "client/package.json"}]},
            ],
            "architecture": {
                "type": "client-server",
                "layers": ["frontend", "backend"],
                "details": {"separation": "monorepo", "api_type": "REST"},
                "evidence": [{"path": "client", "lines": []}, {"path": "server", "lines": []}],
            },
            "modules": [
                {"name": "apps", "role": "module", "path": "server/apps", "submodules": ["accounts:submodule", "core:submodule", "llm:submodule", "projects:submodule"]},
                {"name": "config", "role": "configuration", "path": "server/config", "submodules": []},
                {"name": "services", "role": "business-logic", "path": "server/services", "submodules": ["analyzer:submodule", "documents:submodule", "llm:submodule", "prompting:submodule"]},
                {"name": "tasks", "role": "module", "path": "server/tasks", "submodules": []},
                {"name": "templates", "role": "templates", "path": "server/templates", "submodules": ["core:submodule", "dev:submodule"]},
                {"name": "tests", "role": "testing", "path": "server/tests", "submodules": ["test_analyzer:submodule", "test_documents:submodule", "test_llm:submodule", "test_prompting:submodule"]},
                {"name": "public", "role": "static-files", "path": "client/public", "submodules": []},
                {"name": "src", "role": "module", "path": "client/src", "submodules": ["components:ui-components", "hooks:react-hooks", "pages:pages", "services:business-logic", "types:type-definitions"]},
                {"name": "docs", "role": "top-level", "path": "docs", "submodules": []},
            ],
            "api": {"endpoints": [], "total_count": 0},
            "frontend_routes": [{"path": "/", "name": "", "component": "", "file": "client/src/App.tsx", "auth_required": False}],
            "models": [],
            "runtime": {
                "dependencies": [
                    {"name": "django", "version": ">=5.0"},
                    {"name": "djangorestframework", "version": ">=3.14"},
                    {"name": "drf-spectacular", "version": ">=0.27"},
                    {"name": "celery", "version": ">=5.3"},
                    {"name": "redis", "version": ">=5.0"},
                    {"name": "python-dotenv", "version": ">=1.0"},
                    {"name": "django-cors-headers", "version": ">=4.3"},
                    {"name": "pytest", "version": ">=8.0"},
                    {"name": "pytest-django", "version": ">=4.7"},
                    {"name": "pytest-mock", "version": ">=3.0"},
                    {"name": "openai", "version": ">=1.0"},
                    {"name": "jsonschema", "version": ">=4.0"},
                    {"name": "react", "version": "^18.2.0"},
                    {"name": "react-dom", "version": "^18.2.0"},
                    {"name": "react-router-dom", "version": "^6.20.0"},
                    {"name": "tailwindcss", "version": "^3.4.0"},
                    {"name": "typescript", "version": "^5.3.3"},
                    {"name": "vite", "version": "^5.0.10"},
                ],
                "build_files": ["client/package.json", "client/tsconfig.json", "client/vite.config.ts"],
                "entrypoints": ["server/manage.py", "server/config/wsgi.py", "client/src/types/index.ts"],
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
