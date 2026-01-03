import hashlib
import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Project, AnalysisRun, Artifact, Document, Section, DocumentArtifact
from .serializers import (
    AnalyzeRequestSerializer,
    JobCreateResponseSerializer,
    JobStatusSerializer,
    ArtifactDetailSerializer,
    DocumentCreateSerializer,
    DocumentResponseSerializer,
    OutlineResponseSerializer,
    SectionListSerializer,
    SectionDetailSerializer,
    JobIdResponseSerializer,
    ContextPackResponseSerializer,
    SectionLatestSerializer,
    SectionSpecSerializer,
)
from services.analyzer.constants import ANALYZER_VERSION
from services.documents import DocumentService, SectionBusy
from services.prompting import get_section_spec, list_section_keys
from tasks.analyzer_tasks import run_analysis
from tasks.editor_tasks import run_editor_pipeline_task, run_editor_analyze_task


def _make_analysis_fingerprint(repo_url: str, branch: str, params: dict) -> str:
    data = {
        'repo_url': repo_url,
        'branch': branch,
        'analyzer_version': ANALYZER_VERSION,
        'params': params,
    }
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


@extend_schema(
    request=AnalyzeRequestSerializer,
    responses={202: JobCreateResponseSerializer},
    parameters=[
        OpenApiParameter(
            name='force',
            description='Force new analysis, ignore cache',
            required=False,
            type=bool
        )
    ],
    description="Создаёт задачу анализа репозитория и возвращает job_id. "
                "Если уже есть успешный анализ с тем же fingerprint — возвращает существующий job. "
                "?force=1 игнорирует кеш.",
    tags=["Analysis"]
)
@api_view(['POST'])
def create_analysis(request):
    serializer = AnalyzeRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    repo_url = serializer.validated_data['repo_url']
    branch = serializer.validated_data.get('branch', 'main')
    force = request.query_params.get('force', '').lower() in ('1', 'true', 'yes')

    params = {'branch': branch}
    fingerprint = _make_analysis_fingerprint(repo_url, branch, params)

    project, _ = Project.objects.get_or_create(
        repo_url=repo_url,
        defaults={'default_branch': branch}
    )

    if not force:
        existing_run = AnalysisRun.objects.filter(
            fingerprint=fingerprint,
            status=AnalysisRun.Status.SUCCESS
        ).order_by('-created_at').first()

        if existing_run:
            return Response(
                {
                    "job_id": existing_run.id,
                    "project_id": project.id,
                    "status": existing_run.status,
                    "message": "Returning cached analysis result",
                    "cached": True
                },
                status=status.HTTP_200_OK
            )

    analysis_run = AnalysisRun.objects.create(
        project=project,
        fingerprint=fingerprint,
        params=params,
        analyzer_version=ANALYZER_VERSION,
        status=AnalysisRun.Status.QUEUED
    )

    run_analysis.delay(str(analysis_run.id), repo_url)

    return Response(
        {
            "job_id": analysis_run.id,
            "project_id": project.id,
            "status": analysis_run.status,
            "message": "Analysis job created",
            "cached": False
        },
        status=status.HTTP_202_ACCEPTED
    )


@extend_schema(
    responses={200: JobStatusSerializer},
    description="Получить статус задачи анализа. "
                "Статусы: queued → running → success | failed. "
                "Поле error заполняется только при status=failed.",
    tags=["Analysis"]
)
@api_view(['GET'])
def get_job_status(request, job_id):
    try:
        analysis_run = AnalysisRun.objects.select_related('project').prefetch_related('artifacts').get(id=job_id)
    except AnalysisRun.DoesNotExist:
        return Response(
            {"error": "Job not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = JobStatusSerializer(analysis_run)
    return Response(serializer.data)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='kind',
            description='Тип артефакта: facts, screenshot, docx',
            required=False,
            type=str,
            enum=['facts', 'screenshot', 'docx']
        )
    ],
    responses={200: ArtifactDetailSerializer(many=True)},
    description="Получить артефакты задачи. Фильтр ?kind=facts для конкретного типа.",
    tags=["Analysis"]
)
@api_view(['GET'])
def get_job_artifacts(request, job_id):
    try:
        analysis_run = AnalysisRun.objects.get(id=job_id)
    except AnalysisRun.DoesNotExist:
        return Response(
            {"error": "Job not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    if analysis_run.status in [AnalysisRun.Status.QUEUED, AnalysisRun.Status.RUNNING]:
        return Response({
            "job_id": str(job_id),
            "status": analysis_run.status,
            "progress": analysis_run.progress,
            "artifacts": [],
            "error": None
        })

    if analysis_run.status == AnalysisRun.Status.FAILED:
        return Response({
            "job_id": str(job_id),
            "status": analysis_run.status,
            "progress": analysis_run.progress,
            "artifacts": [],
            "error": analysis_run.error
        })

    artifacts = analysis_run.artifacts.all()

    kind = request.query_params.get('kind')
    if kind:
        artifacts = artifacts.filter(kind=kind)

    serializer = ArtifactDetailSerializer(artifacts, many=True)
    return Response({
        "job_id": str(job_id),
        "status": analysis_run.status,
        "progress": analysis_run.progress,
        "artifacts": serializer.data,
        "error": None
    })


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='step',
            description='Step to run: extract, outline, section, analyze, edit',
            required=True,
            type=str,
            enum=['extract', 'outline', 'section', 'analyze', 'edit']
        ),
        OpenApiParameter(
            name='key',
            description='Section key (required for step=section)',
            required=False,
            type=str
        ),
        OpenApiParameter(
            name='level',
            description='Edit level 1-3 (for step=edit)',
            required=False,
            type=int
        ),
        OpenApiParameter(
            name='force',
            description='Force re-run even if already completed',
            required=False,
            type=bool
        )
    ],
    responses={202: JobIdResponseSerializer},
    description="[DEV] Запустить отдельный шаг пайплайна. "
                "step=extract: перезапуск анализа. "
                "step=outline: генерация outline (нужен Document). "
                "step=section: генерация секции (key обязателен). "
                "step=analyze: анализ качества текста. "
                "step=edit: запуск редактуры документа (level=1,2,3).",
    tags=["Analysis"]
)
@api_view(['POST'])
def run_step(request, job_id):
    if not settings.DEBUG:
        return Response(
            {"error": "This endpoint is only available in DEBUG mode"},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        analysis_run = AnalysisRun.objects.get(id=job_id)
    except AnalysisRun.DoesNotExist:
        return Response(
            {"error": "Job not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    step = request.query_params.get('step')
    if not step:
        return Response(
            {"error": "step parameter is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if step == 'extract':
        run_analysis.delay(str(job_id), analysis_run.project.repo_url)
        return Response(
            {"queued": True, "step": step, "job_id": str(job_id)},
            status=status.HTTP_202_ACCEPTED
        )

    if step == 'outline':
        service = DocumentService()
        doc = analysis_run.documents.first()
        if not doc:
            doc = service.create_document(str(job_id))

        outline_job_id = service.request_outline(str(doc.id))
        return Response(
            {"queued": True, "step": step, "job_id": outline_job_id, "document_id": str(doc.id)},
            status=status.HTTP_202_ACCEPTED
        )

    if step == 'section':
        key = request.query_params.get('key')
        if not key:
            return Response(
                {"error": "key parameter is required for step=section"},
                status=status.HTTP_400_BAD_REQUEST
            )

        doc = analysis_run.documents.first()
        if not doc:
            return Response(
                {"error": "No document found. Run step=outline first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not doc.sections.filter(key=key).exists():
            valid_keys = list(doc.sections.values_list('key', flat=True))
            return Response(
                {"error": f"Section '{key}' not found. Valid keys: {valid_keys}"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            service = DocumentService()
            section_job_id = service.request_section_generate(str(doc.id), key)
            return Response(
                {"queued": True, "step": step, "key": key, "job_id": section_job_id},
                status=status.HTTP_202_ACCEPTED
            )
        except SectionBusy as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)

    if step == 'analyze':
        doc = analysis_run.documents.first()
        if not doc:
            return Response(
                {"error": "No document found. Run step=outline first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        import uuid as uuid_mod
        editor_job_id = str(uuid_mod.uuid4())
        run_editor_analyze_task.delay(str(doc.id), job_id=editor_job_id)
        return Response(
            {"queued": True, "step": step, "job_id": editor_job_id, "document_id": str(doc.id)},
            status=status.HTTP_202_ACCEPTED
        )

    if step == 'edit':
        doc = analysis_run.documents.first()
        if not doc:
            return Response(
                {"error": "No document found. Run step=outline first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        level = int(request.query_params.get('level', 1))
        if level not in [1, 2, 3]:
            return Response(
                {"error": "level must be 1, 2, or 3"},
                status=status.HTTP_400_BAD_REQUEST
            )

        force = request.query_params.get('force', '').lower() in ('1', 'true', 'yes')

        import uuid as uuid_mod
        editor_job_id = str(uuid_mod.uuid4())
        run_editor_pipeline_task.delay(
            str(doc.id),
            level=level,
            force=force,
            job_id=editor_job_id
        )
        return Response(
            {
                "queued": True,
                "step": step,
                "job_id": editor_job_id,
                "document_id": str(doc.id),
                "level": level,
            },
            status=status.HTTP_202_ACCEPTED
        )

    return Response(
        {"error": f"Unknown step: {step}"},
        status=status.HTTP_400_BAD_REQUEST
    )


@extend_schema(
    request=DocumentCreateSerializer,
    responses={201: DocumentResponseSerializer},
    description="Создаёт Document + 5 секций по умолчанию",
    tags=["Documents"]
)
@api_view(['POST'])
def create_document_view(request):
    serializer = DocumentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        service = DocumentService()
        doc = service.create_document(
            analysis_run_id=serializer.validated_data['analysis_run_id'],
            params=serializer.validated_data.get('params') or {},
            doc_type=serializer.validated_data.get('doc_type', 'course'),
            language=serializer.validated_data.get('language', 'ru-RU'),
            target_pages=serializer.validated_data.get('target_pages', 40),
        )
    except AnalysisRun.DoesNotExist:
        return Response(
            {"error": "AnalysisRun not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(DocumentResponseSerializer(doc).data, status=status.HTTP_201_CREATED)


@extend_schema(
    responses={200: DocumentResponseSerializer},
    description="Получить документ по ID",
    tags=["Documents"]
)
@api_view(['GET'])
def get_document(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    return Response(DocumentResponseSerializer(doc).data)


@extend_schema(
    methods=['GET'],
    responses={200: OutlineResponseSerializer},
    description="Получить текущий outline документа",
    tags=["Documents"]
)
@extend_schema(
    methods=['POST'],
    responses={202: JobIdResponseSerializer},
    description="Запустить генерацию outline (async)",
    tags=["Documents"]
)
@api_view(['GET', 'POST'])
def document_outline(request, document_id):
    doc = get_object_or_404(Document, id=document_id)

    if request.method == 'POST':
        service = DocumentService()
        job_id = service.request_outline(str(document_id))
        return Response({'job_id': job_id}, status=status.HTTP_202_ACCEPTED)

    data = {'outline': None, 'artifact_id': None}
    if doc.outline_current:
        data = {
            'outline': doc.outline_current.data_json,
            'artifact_id': doc.outline_current.id
        }
    return Response(OutlineResponseSerializer(data).data)


@extend_schema(
    responses={200: SectionListSerializer(many=True)},
    description="Получить список секций документа",
    tags=["Documents"]
)
@api_view(['GET'])
def list_sections(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    sections = doc.sections.order_by('order')
    return Response(SectionListSerializer(sections, many=True).data)


@extend_schema(
    responses={200: SectionDetailSerializer},
    description="Получить детали секции по ключу",
    tags=["Documents"]
)
@api_view(['GET'])
def get_section(request, document_id, section_key):
    doc = get_object_or_404(Document, id=document_id)
    section = get_object_or_404(Section, document=doc, key=section_key)
    return Response(SectionDetailSerializer(section).data)


@extend_schema(
    responses={
        202: JobIdResponseSerializer,
        409: OpenApiParameter(name='error', description='Section is busy')
    },
    description="Запустить генерацию текста секции (async). 409 если секция уже генерируется.",
    tags=["Documents"]
)
@api_view(['POST'])
def generate_section(request, document_id, section_key):
    doc = get_object_or_404(Document, id=document_id)
    get_object_or_404(Section, document=doc, key=section_key)

    try:
        service = DocumentService()
        job_id = service.request_section_generate(str(document_id), section_key)
        return Response({'job_id': job_id}, status=status.HTTP_202_ACCEPTED)
    except SectionBusy as e:
        return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)


@extend_schema(
    responses={201: ContextPackResponseSerializer},
    description="Собрать context pack для секции (без вызова LLM). "
                "Возвращает artifact_id и данные context pack.",
    tags=["Documents"]
)
@api_view(['POST'])
def build_context_pack(request, document_id, section_key):
    doc = get_object_or_404(Document, id=document_id)
    get_object_or_404(Section, document=doc, key=section_key)

    service = DocumentService()
    artifact = service.build_context_pack(doc, section_key)

    return Response({
        'artifact_id': artifact.id,
        'section_key': section_key,
        'job_id': artifact.job_id,
        'data': artifact.data_json
    }, status=status.HTTP_201_CREATED)


@extend_schema(
    responses={200: SectionLatestSerializer},
    description="Получить последнее состояние секции: текст, summary, context_pack, llm_traces.",
    tags=["Documents"]
)
@api_view(['GET'])
def section_latest(request, document_id, section_key):
    doc = get_object_or_404(Document, id=document_id)
    section = get_object_or_404(Section, document=doc, key=section_key)

    context_pack = DocumentArtifact.objects.filter(
        document=doc,
        section=section,
        kind=DocumentArtifact.Kind.CONTEXT_PACK
    ).order_by('-created_at').first()

    llm_traces = list(DocumentArtifact.objects.filter(
        document=doc,
        section=section,
        kind=DocumentArtifact.Kind.LLM_TRACE
    ).order_by('-created_at')[:10])

    data = {
        'section': section,
        'context_pack': context_pack,
        'llm_traces': llm_traces
    }

    return Response(SectionLatestSerializer(data).data)


@extend_schema(
    responses={200: SectionSpecSerializer(many=True)},
    description="Получить список всех доступных секций из registry с их spec.",
    tags=["Sections"]
)
@api_view(['GET'])
def sections_registry(request):
    section_keys = list_section_keys()
    specs = []

    for key in section_keys:
        spec = get_section_spec(key)
        specs.append({
            'key': spec.key,
            'fact_tags': spec.fact_tags,
            'fact_keys': spec.fact_keys,
            'outline_mode': spec.outline_mode,
            'needs_summaries': spec.needs_summaries,
            'style_profile': spec.style_profile,
            'target_chars': spec.target_chars,
            'constraints': spec.constraints
        })

    return Response(SectionSpecSerializer(specs, many=True).data)
