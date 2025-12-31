from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from services.analyzer import RepoAnalyzer
from .serializers import AnalyzeRequestSerializer, AnalyzeResponseSerializer


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
