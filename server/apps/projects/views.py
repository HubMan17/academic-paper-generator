from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Project, AnalysisRun, Artifact, Document, Section
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
)
from services.documents import DocumentService, SectionBusy
from tasks.analyzer_tasks import run_analysis


@extend_schema(
    request=AnalyzeRequestSerializer,
    responses={202: JobCreateResponseSerializer},
    description="Создаёт задачу анализа репозитория и возвращает job_id. "
                "Если уже есть успешный анализ для того же repo — возвращает существующий job.",
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

    project, _ = Project.objects.get_or_create(
        repo_url=repo_url,
        defaults={'default_branch': branch}
    )

    existing_run = AnalysisRun.objects.filter(
        project=project,
        status=AnalysisRun.Status.SUCCESS
    ).order_by('-created_at').first()

    if existing_run:
        return Response(
            {
                "job_id": existing_run.id,
                "project_id": project.id,
                "status": existing_run.status,
                "message": "Returning cached analysis result"
            },
            status=status.HTTP_200_OK
        )

    analysis_run = AnalysisRun.objects.create(
        project=project,
        status=AnalysisRun.Status.QUEUED
    )

    run_analysis.delay(str(analysis_run.id), repo_url)

    return Response(
        {
            "job_id": analysis_run.id,
            "project_id": project.id,
            "status": analysis_run.status,
            "message": "Analysis job created"
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
