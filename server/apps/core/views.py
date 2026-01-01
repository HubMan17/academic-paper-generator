from dataclasses import asdict

from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from services.analyzer import RepoAnalyzer
from services.llm import LLMClient
from services.llm.errors import LLMError
from apps.llm.models import LLMCall
from .serializers import (
    AnalyzeRequestSerializer,
    AnalyzeResponseSerializer,
    LLMTextRequestSerializer,
    LLMJsonRequestSerializer,
    LLMResponseSerializer,
)


def test_page(request):
    return render(request, 'core/test_page.html')


def test_analyzer_page(request):
    return render(request, 'core/test_analyzer.html')


@extend_schema(
    request=AnalyzeRequestSerializer,
    responses={200: AnalyzeResponseSerializer},
    description="Анализирует репозиторий и возвращает facts.json",
    tags=["Analyzer"]
)
@api_view(['POST'])
def analyze_repository_api(request):
    serializer = AnalyzeRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "error": serializer.errors, "facts": None},
            status=status.HTTP_400_BAD_REQUEST
        )

    repo_url = serializer.validated_data['repo_url']

    try:
        analyzer = RepoAnalyzer(repo_url)
        facts = analyzer.analyze()
        return Response({
            "status": "success",
            "facts": facts,
            "error": None
        })
    except Exception as e:
        return Response(
            {"status": "error", "error": str(e), "facts": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    request=LLMTextRequestSerializer,
    responses={200: LLMResponseSerializer},
    description="Генерирует текст через LLM",
    tags=["LLM"]
)
@api_view(['POST'])
def llm_generate_text_api(request):
    serializer = LLMTextRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "error": serializer.errors, "result": None},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data

    try:
        client = LLMClient()
        result = client.generate_text(
            system=data['system'],
            user=data['user'],
            model=data.get('model'),
            temperature=data.get('temperature', 0.7),
            use_cache=data.get('use_cache', True),
        )
        return Response({
            "status": "success",
            "result": {
                "text": result.text,
                "meta": asdict(result.meta),
            },
            "error": None
        })
    except LLMError as e:
        return Response(
            {"status": "error", "error": str(e), "result": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    request=LLMJsonRequestSerializer,
    responses={200: LLMResponseSerializer},
    description="Генерирует JSON через LLM",
    tags=["LLM"]
)
@api_view(['POST'])
def llm_generate_json_api(request):
    serializer = LLMJsonRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "error": serializer.errors, "result": None},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data

    try:
        client = LLMClient()
        result = client.generate_json(
            system=data['system'],
            user=data['user'],
            model=data.get('model'),
            temperature=data.get('temperature', 0.3),
            use_cache=data.get('use_cache', True),
            schema=data.get('schema'),
        )
        return Response({
            "status": "success",
            "result": {
                "data": result.data,
                "meta": asdict(result.meta),
            },
            "error": None
        })
    except LLMError as e:
        return Response(
            {"status": "error", "error": str(e), "result": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    responses={200: dict},
    description="Получает статистику LLM вызовов",
    tags=["LLM"]
)
@api_view(['GET'])
def llm_stats_api(request):
    total = LLMCall.objects.count()
    success = LLMCall.objects.filter(status=LLMCall.Status.SUCCESS).count()
    failed = LLMCall.objects.filter(status=LLMCall.Status.FAILED).count()
    in_progress = LLMCall.objects.filter(status=LLMCall.Status.IN_PROGRESS).count()

    recent = LLMCall.objects.order_by('-created_at')[:10]
    recent_list = [
        {
            "fingerprint": call.fingerprint[:16] + "...",
            "model": call.model,
            "status": call.status,
            "created_at": call.created_at.isoformat(),
            "cost": call.meta.get("cost_estimate", 0) if call.meta else 0,
        }
        for call in recent
    ]

    return Response({
        "total": total,
        "success": success,
        "failed": failed,
        "in_progress": in_progress,
        "recent": recent_list,
    })


@extend_schema(
    responses={200: dict},
    description="Очищает кэш LLM вызовов",
    tags=["LLM"]
)
@api_view(['POST'])
def llm_clear_cache_api(request):
    deleted, _ = LLMCall.objects.all().delete()
    return Response({
        "status": "success",
        "deleted": deleted,
    })
