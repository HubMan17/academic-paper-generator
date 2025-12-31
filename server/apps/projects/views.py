from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Project, AnalysisRun, Artifact
from .serializers import (
    AnalyzeRequestSerializer,
    JobCreateResponseSerializer,
    JobStatusSerializer,
    ArtifactDetailSerializer,
)
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
