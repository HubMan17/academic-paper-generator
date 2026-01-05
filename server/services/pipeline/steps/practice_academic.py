import json
import logging
import re
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.projects.models import Artifact, Document, DocumentArtifact, Section
from services.llm import LLMClient
from services.pipeline.ensure import ensure_artifact, get_success_artifact, invalidate_assembly_artifacts
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import get_profile
from services.pipeline.work_types import get_work_type_preset

logger = logging.getLogger(__name__)

PRACTICE_SYSTEM_PROMPT_TEMPLATE = """You are writing a PRACTICAL section of an academic paper in Russian.

This section should describe the practical implementation based on the provided project analysis.

RULES:
– Write in academic style but with concrete details about the project
– Use information from the provided facts about the project
– Describe architecture, implementation details, or testing approaches as appropriate
– DO NOT use bullet lists or numbered lists in the main text
– Write continuous prose paragraphs only
– Focus on technical decisions and their justification

For ANALYSIS sections: describe requirements, domain analysis, problem statement
For ARCHITECTURE sections: describe system structure, components, design decisions
For IMPLEMENTATION sections: describe key algorithms, data flows, core functionality
For TESTING sections: describe testing strategy, test coverage, quality assurance

Target length: {target_words} words in Russian.
Write continuous prose paragraphs only."""

PRACTICE_USER_TEMPLATE = """Тема работы: {topic_title}

Раздел: {section_title}

Ключевые аспекты для раскрытия:
{section_points}

Информация о проекте (facts):
{facts_summary}

Тип работы: {work_type_name}

Напишите текст данного практического раздела в академическом стиле.
Используйте конкретную информацию о проекте из предоставленных данных."""

PRACTICE_WORD_LIMITS = {
    "referat": {"min": 400, "max": 700, "target": "500–600"},
    "course": {"min": 800, "max": 1400, "target": "1000–1200"},
    "diploma": {"min": 1000, "max": 1800, "target": "1200–1600"},
}

PRACTICE_SUBSECTION_WORD_LIMITS = {
    "referat": {"min": 150, "max": 300, "target": "200–280"},
    "course": {"min": 300, "max": 500, "target": "350–450"},
    "diploma": {"min": 400, "max": 600, "target": "450–550"},
}


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def validate_practice_quality(
    text: str,
    work_type: str = "course",
    is_subsection: bool = False,
    custom_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    word_count = count_words(text)
    issues = []

    if custom_limits:
        limits = custom_limits
    elif is_subsection:
        limits = PRACTICE_SUBSECTION_WORD_LIMITS.get(work_type, PRACTICE_SUBSECTION_WORD_LIMITS["course"])
    else:
        limits = PRACTICE_WORD_LIMITS.get(work_type, PRACTICE_WORD_LIMITS["course"])

    min_words = limits["min"]
    max_words = limits["max"]

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words} for {work_type})")

    if word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words} for {work_type})")

    has_bullet_list = bool(re.search(r'^\s*[-•●]\s+', text, re.MULTILINE))
    has_numbered_list = bool(re.search(r'^\s*\d+[.)]\s+', text, re.MULTILINE))

    if has_bullet_list:
        issues.append("Contains bullet lists (not allowed in academic text)")
    if has_numbered_list:
        issues.append("Contains numbered lists (not allowed in academic text)")

    return {
        "valid": len(issues) == 0,
        "word_count": word_count,
        "issues": issues,
    }


def get_section_points_from_outline(document: Document, section_key: str) -> tuple[list[str], bool]:
    from services.pipeline.ensure import get_outline_artifact

    outline_artifact = get_outline_artifact(document.id)
    if not outline_artifact:
        return [], False

    outline_data = outline_artifact.data_json
    chapters = outline_data.get("chapters", [])

    for chapter in chapters:
        if chapter.get("key") == "practice":
            for section in chapter.get("sections", []):
                if section.get("key") == section_key:
                    return section.get("points", []), False

                for subsec in section.get("subsections", []):
                    if subsec.get("key") == section_key:
                        return subsec.get("points", []), True

    return [], False


def get_facts_summary(document: Document, section_key: str) -> str:
    from services.pipeline.facts_sanitizer import sanitize_facts_for_llm, get_sanitized_facts_summary

    try:
        artifact = Artifact.objects.filter(
            analysis_run=document.analysis_run,
            kind=Artifact.Kind.FACTS
        ).order_by('-created_at').first()

        if not artifact or not artifact.data:
            return "Информация о проекте не доступна"

        facts = artifact.data
        clean_facts = sanitize_facts_for_llm(facts)
        return get_sanitized_facts_summary(clean_facts, section_key)

    except Exception as e:
        logger.warning(f"Failed to get facts summary: {e}")
        return "Информация о проекте не доступна"


def ensure_practice_section(
    document_id: UUID,
    section_key: str,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
    max_retries: int = 2,
) -> DocumentArtifact:
    section_kind = ArtifactKind.section(section_key)
    trace_kind = ArtifactKind.llm_trace(section_key)
    prof = get_profile(profile)

    document = Document.objects.get(id=document_id)
    section = document.sections.filter(key=section_key).first()

    if not section:
        raise ValueError(f"No section with key '{section_key}' found for document {document_id}")

    if section.chapter_key != 'practice':
        raise ValueError(f"Section '{section_key}' is not a practice section (chapter_key={section.chapter_key})")

    section.status = Section.Status.RUNNING
    section.save(update_fields=['status', 'updated_at'])

    def builder() -> dict[str, Any]:
        doc_profile = document.profile
        if doc_profile:
            topic_title = doc_profile.topic_title
            work_type_key = doc_profile.work_type
            work_type_name = doc_profile.get_work_type_display()
        else:
            topic_title = document.params.get('title', 'Разработка программного обеспечения')
            work_type_key = document.type
            work_type_name = document.get_type_display()

        is_subsection = section.depth >= 3 or bool(section.parent_key)
        preset = get_work_type_preset(work_type_key)

        section_points, _ = get_section_points_from_outline(document, section_key)
        points_text = "\n".join(f"– {p}" for p in section_points) if section_points else "Раскрыть практические аспекты реализации"

        facts_summary = get_facts_summary(document, section_key)

        if section_key.startswith('practice_') and '_' in section_key:
            section_index = int(section_key.split('_')[1]) - 1
        else:
            section_index = 0
        preset_target = preset.get_section_target_words('practice', section_index)

        if is_subsection:
            limits = PRACTICE_SUBSECTION_WORD_LIMITS.get(work_type_key, PRACTICE_SUBSECTION_WORD_LIMITS["course"])
            target_words = limits["target"]
        elif preset_target != 800:
            min_w = int(preset_target * 0.85)
            max_w = int(preset_target * 1.15)
            limits = {"min": min_w, "max": max_w, "target": f"{min_w}–{max_w}"}
            target_words = str(preset_target)
        else:
            limits = PRACTICE_WORD_LIMITS.get(work_type_key, PRACTICE_WORD_LIMITS["course"])
            target_words = limits["target"]

        if mock_mode:
            content_text = generate_mock_practice(section.title, section_key, is_subsection)
            meta = {
                "mock": True,
                "profile": profile,
                "mode": "practice_academic",
                "work_type": work_type_key,
                "is_subsection": is_subsection,
            }
            llm_trace_data = None
            validation = {"valid": True, "word_count": count_words(content_text), "issues": []}
        else:
            system_prompt = PRACTICE_SYSTEM_PROMPT_TEMPLATE.format(target_words=target_words)
            user_prompt = PRACTICE_USER_TEMPLATE.format(
                topic_title=topic_title,
                section_title=section.title,
                section_points=points_text,
                facts_summary=facts_summary,
                work_type_name=work_type_name,
            )

            budget = prof.get_budget_for_section(section_key)
            llm_client = LLMClient()

            content_text = None
            validation = None
            attempts = 0

            for attempt in range(1, max_retries + 1):
                attempts = attempt
                logger.info(f"Generating practice {'subsection' if is_subsection else 'section'} '{section_key}', attempt {attempt}/{max_retries}")

                result = llm_client.generate_text(
                    system=system_prompt,
                    user=user_prompt,
                    temperature=0.7,
                    max_tokens=max(2000 if is_subsection else 4000, budget.max_output_tokens),
                    use_cache=attempt == 1,
                )

                content_text = result.text
                validation = validate_practice_quality(content_text, work_type_key, is_subsection, limits)

                if validation["valid"]:
                    logger.info(f"Practice section '{section_key}' passed validation on attempt {attempt}")
                    break
                else:
                    logger.warning(f"Practice section validation failed on attempt {attempt}: {validation['issues']}")
                    if attempt < max_retries:
                        user_prompt = user_prompt + f"\n\nВАЖНО: Целевой объём: {target_words} слов. Пишите сплошным текстом без списков."

            meta = {
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": {
                    "prompt": result.meta.prompt_tokens,
                    "completion": result.meta.completion_tokens,
                    "total": result.meta.total_tokens
                },
                "cost_estimate": result.meta.cost_estimate,
                "profile": profile,
                "mode": "practice_academic",
                "work_type": work_type_key,
                "is_subsection": is_subsection,
                "target_words": target_words,
                "generation_attempts": attempts,
                "validation": validation,
            }

            llm_trace_data = {
                "operation": "practice_academic_generate",
                "section_key": section_key,
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": meta["tokens"],
                "cost_estimate": result.meta.cost_estimate,
                "generation_attempts": attempts,
                "validation_passed": validation["valid"],
                "validation_issues": validation["issues"],
            }

        word_count = count_words(content_text)
        char_count = len(content_text)

        if llm_trace_data:
            DocumentArtifact.objects.create(
                document=document,
                section=section,
                job_id=job_id,
                kind=trace_kind,
                format=DocumentArtifact.Format.JSON,
                data_json=llm_trace_data,
                source="llm",
                version="v1",
                meta={"status": "success"},
            )

        return {
            "content_text": content_text,
            "format": DocumentArtifact.Format.MARKDOWN,
            "meta": {
                **meta,
                "word_count": word_count,
                "char_count": char_count,
                "sources_used": [],
            },
        }

    try:
        existing_artifact = get_success_artifact(document_id, section_kind)

        artifact = ensure_artifact(
            document_id=document_id,
            kind=section_kind,
            builder_fn=builder,
            force=force,
            job_id=job_id,
            section_key=section_key,
        )

        is_new_artifact = artifact.id != (existing_artifact.id if existing_artifact else None)

        if is_new_artifact:
            invalidated = invalidate_assembly_artifacts(document_id)
            if invalidated:
                logger.info(f"Practice section '{section_key}' regenerated, invalidated: {invalidated}")

        with transaction.atomic():
            section.text_current = artifact.content_text or ""
            section.version += 1
            section.last_artifact = artifact
            section.status = Section.Status.SUCCESS
            section.last_error = ""
            section.save(update_fields=[
                'text_current', 'version', 'last_artifact',
                'status', 'last_error', 'updated_at'
            ])

        return artifact

    except Exception as e:
        section.status = Section.Status.FAILED
        section.last_error = str(e)[:1000]
        section.save(update_fields=['status', 'last_error', 'updated_at'])
        raise


def generate_mock_practice(title: str, key: str, is_subsection: bool = False) -> str:
    if is_subsection:
        return f"""Данный подраздел посвящён рассмотрению одного из практических аспектов реализации системы. В процессе разработки программного решения были учтены требования к функциональности и производительности.

Реализованный подход позволяет обеспечить выполнение поставленных задач с учётом специфики предметной области. Принятые технические решения основаны на анализе требований и доступных ресурсов.

Таким образом, представленный материал демонстрирует практическое применение выбранных методов и подходов.

Это тестовый текст подраздела практической части, сгенерированный в режиме MOCK."""

    return f"""Практическая реализация программного решения осуществлялась с учётом требований, выявленных на этапе анализа предметной области. Разработанная система представляет собой комплексное решение, обеспечивающее выполнение поставленных задач.

Архитектура системы построена с использованием модульного подхода, что обеспечивает возможность независимого развития отдельных компонентов. Каждый модуль отвечает за определённый аспект функциональности и взаимодействует с другими компонентами через чётко определённые интерфейсы.

Основные компоненты системы включают модуль обработки данных, модуль бизнес-логики и модуль представления. Такое разделение позволяет обеспечить низкую связанность между компонентами и высокую связность внутри каждого из них.

В процессе реализации особое внимание уделялось обеспечению качества кода и его тестируемости. Были разработаны автоматизированные тесты, покрывающие основные сценарии использования системы.

Результаты тестирования подтвердили корректность реализации основных функций системы и её соответствие заявленным требованиям.

Это тестовый текст практического раздела, сгенерированный в режиме MOCK."""
