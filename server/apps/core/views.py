from dataclasses import asdict

from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from services.analyzer import RepoAnalyzer
from services.llm import LLMClient
from services.llm.errors import LLMError
from services.prompting import slice_for_section
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


def dev_pipeline_page(request):
    return render(request, 'dev/pipeline.html')


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


@extend_schema(
    responses={200: dict},
    description="Создаёт ContextPack для секции документа",
    tags=["Prompting"]
)
@api_view(['POST'])
def prompting_slice_api(request):
    section_key = request.data.get('section_key')
    facts = request.data.get('facts', {})
    outline = request.data.get('outline', {})
    summaries = request.data.get('summaries', [])
    global_context = request.data.get('global_context', '')

    if not section_key:
        return Response(
            {"status": "error", "error": "section_key is required", "context_pack": None},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        context_pack = slice_for_section(
            section_key=section_key,
            facts=facts,
            outline=outline,
            summaries=summaries,
            global_context=global_context
        )

        pack_data = {
            "section_key": context_pack.section_key,
            "layers": {
                "global_context": context_pack.layers.global_context,
                "outline_excerpt": context_pack.layers.outline_excerpt,
                "facts_slice": context_pack.layers.facts_slice,
                "summaries": context_pack.layers.summaries,
                "constraints": context_pack.layers.constraints
            },
            "rendered_prompt": {
                "system": context_pack.rendered_prompt.system,
                "user": context_pack.rendered_prompt.user
            },
            "budget": {
                "max_input_tokens_approx": context_pack.budget.max_input_tokens_approx,
                "max_output_tokens": context_pack.budget.max_output_tokens,
                "soft_char_limit": context_pack.budget.soft_char_limit
            },
            "debug": {
                "selected_fact_refs": [
                    {"fact_id": ref.fact_id, "reason": ref.reason, "weight": ref.weight}
                    for ref in context_pack.debug.selected_fact_refs
                ],
                "selection_reason": context_pack.debug.selection_reason,
                "trims_applied": context_pack.debug.trims_applied
            }
        }

        return Response({
            "status": "success",
            "context_pack": pack_data,
            "error": None
        })
    except ValueError as e:
        return Response(
            {"status": "error", "error": str(e), "context_pack": None},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {"status": "error", "error": str(e), "context_pack": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def test_pipeline_page(request):
    return render(request, 'core/test_pipeline.html')


@extend_schema(
    responses={200: dict},
    description="Запускает полный пайплайн генерации документа",
    tags=["Pipeline"]
)
@api_view(['POST'])
def pipeline_run_api(request):
    work_type = request.data.get('work_type', 'referat')
    profile = request.data.get('profile', 'default')
    topic_title = request.data.get('topic_title', 'Разработка программного обеспечения')
    topic_description = request.data.get('topic_description', '')
    facts = request.data.get('facts')
    mock_mode = request.data.get('mock_mode', True)

    try:
        if mock_mode:
            from services.pipeline.work_types import WORK_TYPE_PRESETS

            preset = WORK_TYPE_PRESETS.get(work_type)
            if not preset:
                preset = WORK_TYPE_PRESETS['referat']

            mock_outline = {
                "chapters": [
                    {
                        "key": "intro",
                        "title": "Введение",
                        "sections": [
                            {"key": "intro.main", "title": "Введение", "target_words": 500}
                        ]
                    },
                    {
                        "key": "chapter1",
                        "title": "Теоретическая часть",
                        "sections": [
                            {"key": "chapter1.overview", "title": "Обзор предметной области", "target_words": 800},
                            {"key": "chapter1.tech", "title": "Анализ технологий", "target_words": 600}
                        ]
                    },
                    {
                        "key": "chapter2",
                        "title": "Практическая часть",
                        "sections": [
                            {"key": "chapter2.design", "title": "Проектирование системы", "target_words": 700},
                            {"key": "chapter2.impl", "title": "Реализация", "target_words": 800}
                        ]
                    },
                    {
                        "key": "conclusion",
                        "title": "Заключение",
                        "sections": [
                            {"key": "conclusion.main", "title": "Заключение", "target_words": 400}
                        ]
                    }
                ]
            }

            mock_sections = []
            total_words = 0
            for chapter in mock_outline['chapters']:
                for section in chapter['sections']:
                    words = section['target_words']
                    mock_sections.append({
                        "chapter_key": section['key'],
                        "title": section['title'],
                        "text": f"[Содержимое секции '{section['title']}' - {words} слов]\n\n" + "Lorem ipsum... " * (words // 10),
                        "word_count": words
                    })
                    total_words += words

            mock_literature = {
                "sources": [
                    {
                        "type": "web",
                        "citation": "Django Documentation [Электронный ресурс]. — URL: https://docs.djangoproject.com/",
                        "relevance": "technology"
                    },
                    {
                        "type": "book",
                        "citation": "Мартин Р. Чистая архитектура. — СПб.: Питер, 2018. — 352 с.",
                        "relevance": "architecture"
                    },
                    {
                        "type": "book",
                        "citation": "Гамма Э. и др. Паттерны проектирования. — СПб.: Питер, 2020. — 368 с.",
                        "relevance": "methodology"
                    }
                ]
            }

            mock_quality = {
                "total_words": total_words,
                "sections_count": len(mock_sections),
                "completeness_score": 0.85,
                "issues": []
            }

            result = {
                "outline": mock_outline,
                "sections": mock_sections,
                "sections_count": len(mock_sections),
                "total_words": total_words,
                "literature": mock_literature,
                "sources_count": len(mock_literature['sources']),
                "quality_report": mock_quality,
                "work_type": work_type,
                "profile": profile,
                "mock": True
            }
        else:
            result = {
                "error": "Real pipeline execution not implemented in test API",
                "mock": False
            }

        return Response({
            "status": "success",
            "result": result,
            "error": None
        })

    except Exception as e:
        return Response(
            {"status": "error", "error": str(e), "result": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
