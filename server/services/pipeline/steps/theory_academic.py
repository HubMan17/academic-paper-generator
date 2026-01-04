import logging
import re
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.projects.models import Document, DocumentArtifact, Section
from services.llm import LLMClient
from services.pipeline.ensure import ensure_artifact, get_success_artifact, invalidate_assembly_artifacts
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import get_profile
from services.pipeline.work_types import get_work_type_preset

logger = logging.getLogger(__name__)

THEORY_SYSTEM_PROMPT_TEMPLATE = """You are writing a THEORETICAL section of an academic paper in Russian.

STRICT RULES:
– DO NOT mention any specific project, repository, or codebase
– DO NOT mention Git, URLs, commits, directories, or file structures
– DO NOT mention concrete frameworks or libraries by name (Django, React, etc.)
– DO NOT analyze source code or implementation details
– DO NOT use bullet lists or numbered lists in the main text
– Write in general scientific/academic language
– Use abstract examples when needed
– Focus on paradigms, approaches, methodologies, and principles

ALLOWED:
– Describe programming paradigms (OOP, functional, etc.) in general terms
– Discuss architectural patterns (client-server, MVC, microservices) abstractly
– Explain software engineering principles and best practices
– Reference academic concepts and methodologies
– Use terms like "web application", "information system", "software system" generically

Target length: {target_words} words in Russian.
Write continuous prose paragraphs only."""

THEORY_USER_TEMPLATE = """Тема работы: {topic_title}

Раздел: {section_title}

Ключевые аспекты для раскрытия:
{section_points}

Тип работы: {work_type_name}

Напишите текст данного теоретического раздела в академическом стиле.
Текст должен быть общетеоретическим, без привязки к конкретному проекту или технологиям."""

THEORY_WORD_LIMITS = {
    "referat": {"min": 450, "max": 700, "target": "500–600"},
    "course": {"min": 1000, "max": 1600, "target": "1200–1400"},
    "diploma": {"min": 1200, "max": 1800, "target": "1400–1600"},
}

SUBSECTION_WORD_LIMITS = {
    "referat": {"min": 150, "max": 280, "target": "180–250"},
    "course": {"min": 350, "max": 550, "target": "400–500"},
    "diploma": {"min": 450, "max": 650, "target": "500–600"},
}

FORBIDDEN_PATTERNS = [
    r'\bDjango\b', r'\bFlask\b', r'\bFastAPI\b', r'\bReact\b', r'\bVue\b', r'\bAngular\b',
    r'\bNode\.?js\b', r'\bExpress\b', r'\bPostgreSQL\b', r'\bMySQL\b', r'\bMongoDB\b',
    r'\bRedis\b', r'\bDocker\b', r'\bKubernetes\b', r'\bAWS\b', r'\bGitHub\b', r'\bGitLab\b',
    r'\bGraphQL\b', r'\bWebSocket\b', r'\bCelery\b', r'\bNginx\b', r'\bGunicorn\b',
    r'\bPython\b', r'\bJavaScript\b', r'\bTypeScript\b', r'\bJava\b', r'\bC\+\+\b', r'\bC#\b',
    r'\bJSON\b', r'\bXML\b', r'\bSQL\b', r'\bОРМ\b', r'\bORM\b',
    r'\bserver/', r'\bclient/', r'\bapps/', r'\bservices/', r'\btests/',
    r'репозитори[йяюе]', r'коммит', r'\.py\b', r'\.js\b', r'\.tsx?\b',
    r'requirements\.txt', r'package\.json', r'README',
]


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def validate_theory_quality(
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
        limits = SUBSECTION_WORD_LIMITS.get(work_type, SUBSECTION_WORD_LIMITS["course"])
    else:
        limits = THEORY_WORD_LIMITS.get(work_type, THEORY_WORD_LIMITS["course"])

    min_words = limits["min"]
    max_words = limits["max"]

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words} for {work_type})")

    if word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words} for {work_type})")

    forbidden_found = []
    for pattern in FORBIDDEN_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            forbidden_found.extend(matches)

    if forbidden_found:
        unique_forbidden = list(set(forbidden_found))[:10]
        issues.append(f"Forbidden terms found: {', '.join(unique_forbidden)}")

    has_bullet_list = bool(re.search(r'^\s*[-•●]\s+', text, re.MULTILINE))
    has_numbered_list = bool(re.search(r'^\s*\d+[.)]\s+', text, re.MULTILINE))

    if has_bullet_list:
        issues.append("Contains bullet lists (not allowed in theory)")
    if has_numbered_list:
        issues.append("Contains numbered lists (not allowed in theory)")

    return {
        "valid": len(issues) == 0,
        "word_count": word_count,
        "issues": issues,
        "forbidden_terms_found": forbidden_found,
    }


def get_section_points_from_outline(document: Document, section_key: str) -> tuple[list[str], bool]:
    from services.pipeline.ensure import get_outline_artifact

    outline_artifact = get_outline_artifact(document.id)
    if not outline_artifact:
        return [], False

    outline_data = outline_artifact.data_json
    chapters = outline_data.get("chapters", [])

    for chapter in chapters:
        if chapter.get("key") == "theory":
            for section in chapter.get("sections", []):
                if section.get("key") == section_key:
                    return section.get("points", []), False

                for subsec in section.get("subsections", []):
                    if subsec.get("key") == section_key:
                        return subsec.get("points", []), True

    return [], False


def ensure_theory_section(
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

    if section.chapter_key != 'theory':
        raise ValueError(f"Section '{section_key}' is not a theory section (chapter_key={section.chapter_key})")

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
        points_text = "\n".join(f"– {p}" for p in section_points) if section_points else "Раскрыть основные теоретические аспекты темы"

        preset_target = preset.get_section_target_words(section_key)

        if is_subsection:
            limits = SUBSECTION_WORD_LIMITS.get(work_type_key, SUBSECTION_WORD_LIMITS["course"])
            target_words = limits["target"]
        elif preset_target != 800:
            min_w = int(preset_target * 0.85)
            max_w = int(preset_target * 1.15)
            limits = {"min": min_w, "max": max_w, "target": f"{min_w}–{max_w}"}
            target_words = str(preset_target)
        else:
            limits = THEORY_WORD_LIMITS.get(work_type_key, THEORY_WORD_LIMITS["course"])
            target_words = limits["target"]

        if mock_mode:
            content_text = generate_mock_theory(section.title, section_key, is_subsection)
            meta = {
                "mock": True,
                "profile": profile,
                "mode": "theory_academic",
                "work_type": work_type_key,
                "is_subsection": is_subsection,
            }
            llm_trace_data = None
            validation = {"valid": True, "word_count": count_words(content_text), "issues": []}
        else:
            system_prompt = THEORY_SYSTEM_PROMPT_TEMPLATE.format(target_words=target_words)
            user_prompt = THEORY_USER_TEMPLATE.format(
                topic_title=topic_title,
                section_title=section.title,
                section_points=points_text,
                work_type_name=work_type_name,
            )

            budget = prof.get_budget_for_section(section_key)
            llm_client = LLMClient()

            content_text = None
            validation = None
            attempts = 0

            for attempt in range(1, max_retries + 1):
                attempts = attempt
                logger.info(f"Generating theory {'subsection' if is_subsection else 'section'} '{section_key}', attempt {attempt}/{max_retries}")

                result = llm_client.generate_text(
                    system=system_prompt,
                    user=user_prompt,
                    temperature=0.7,
                    max_tokens=max(2000 if is_subsection else 4000, budget.max_output_tokens),
                    use_cache=attempt == 1,
                )

                content_text = result.text
                validation = validate_theory_quality(content_text, work_type_key, is_subsection, limits)

                if validation["valid"]:
                    logger.info(f"Theory section '{section_key}' passed validation on attempt {attempt}")
                    break
                else:
                    logger.warning(f"Theory section validation failed on attempt {attempt}: {validation['issues']}")
                    if attempt < max_retries:
                        user_prompt = user_prompt + f"\n\nВАЖНО: Пишите общетеоретический текст БЕЗ упоминания конкретных технологий, фреймворков и проектов. Целевой объём: {target_words} слов."

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
                "mode": "theory_academic",
                "work_type": work_type_key,
                "is_subsection": is_subsection,
                "target_words": target_words,
                "generation_attempts": attempts,
                "validation": validation,
            }

            llm_trace_data = {
                "operation": "theory_academic_generate",
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
                logger.info(f"Theory section '{section_key}' regenerated, invalidated: {invalidated}")

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


def generate_mock_theory(title: str, key: str, is_subsection: bool = False) -> str:
    if is_subsection:
        return f"""Данный подраздел посвящён рассмотрению одного из ключевых аспектов теоретической базы работы. В контексте современных подходов к разработке программного обеспечения особое значение приобретает понимание фундаментальных принципов.

Рассматриваемый аспект играет важную роль в формировании целостного представления о предметной области. Его изучение позволяет глубже понять природу исследуемых явлений и процессов.

Таким образом, представленный материал формирует необходимую теоретическую базу для последующего анализа практических решений.

Это тестовый текст подраздела, сгенерированный в режиме MOCK."""

    return f"""В современной практике разработки программного обеспечения особое значение приобретает системный подход к проектированию и реализации информационных систем. Данный раздел посвящён рассмотрению теоретических основ, необходимых для понимания принципов создания качественного программного продукта.

Объектно-ориентированное программирование представляет собой одну из наиболее распространённых парадигм разработки, позволяющую структурировать программный код в виде взаимосвязанных объектов. Каждый объект характеризуется набором свойств и методов, определяющих его состояние и поведение. Ключевыми принципами данной парадигмы являются инкапсуляция, наследование и полиморфизм.

Инкапсуляция обеспечивает сокрытие внутренней реализации объекта от внешнего окружения, предоставляя доступ к функциональности исключительно через определённый интерфейс. Это способствует снижению связанности компонентов системы и упрощает её сопровождение.

Наследование позволяет создавать новые классы на основе существующих, заимствуя их свойства и методы. Данный механизм способствует повторному использованию кода и формированию иерархий типов.

Полиморфизм обеспечивает возможность единообразного обращения к объектам различных типов через общий интерфейс, что повышает гибкость и расширяемость программных систем.

Применение указанных принципов в совокупности позволяет создавать модульные, масштабируемые и легко сопровождаемые программные решения.

Это тестовый текст теоретического раздела, сгенерированный в режиме MOCK."""
