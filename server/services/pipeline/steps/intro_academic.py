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

logger = logging.getLogger(__name__)

ACADEMIC_INTRO_SYSTEM_PROMPT_TEMPLATE = """You are writing the INTRODUCTION of an academic paper in Russian.

Your task:
– Introduce the relevance of the topic
– Describe the general context of modern software development
– Explain the problem area and why it matters
– Gradually lead the reader to the topic of the work
– Formulate the goal and objectives of the work

STRICT RULES:
– Do NOT mention specific technologies, frameworks, libraries, or tools
– Do NOT describe implementation details
– Do NOT analyze source code or repositories
– Do NOT use bullet lists or numbered lists
– Write in a formal academic style
– The text must be logically coherent and suitable for a university paper
– Write continuous prose paragraphs only

Target length: {target_words} words in Russian."""

INTRO_WORD_LIMITS = {
    "referat": {"min": 300, "max": 500, "target": "350–450"},
    "course": {"min": 350, "max": 600, "target": "400–550"},
    "diploma": {"min": 600, "max": 1100, "target": "700–950"},
}

ACADEMIC_INTRO_USER_TEMPLATE = """Тема работы: {topic_title}

Краткое описание работы:
{topic_description}

Тип работы: {work_type_name}

Язык: русский

Напишите введение к данной работе, следуя академическому стилю изложения."""

FORBIDDEN_TECH_PATTERNS = [
    r'\bDjango\b', r'\bFlask\b', r'\bFastAPI\b', r'\bReact\b', r'\bVue\b', r'\bAngular\b',
    r'\bNode\.?js\b', r'\bExpress\b', r'\bPostgreSQL\b', r'\bMySQL\b', r'\bMongoDB\b',
    r'\bRedis\b', r'\bDocker\b', r'\bKubernetes\b', r'\bAWS\b', r'\bAPI\b', r'\bREST\b',
    r'\bGraphQL\b', r'\bWebSocket\b', r'\bCelery\b', r'\bNginx\b', r'\bGunicorn\b',
    r'\bPython\b', r'\bJavaScript\b', r'\bTypeScript\b', r'\bHTML\b', r'\bCSS\b',
    r'\bJSON\b', r'\bXML\b', r'\bSQL\b', r'\bОРМ\b', r'\bORM\b', r'\bфреймворк\b',
    r'\bбиблиотек[аиу]\b', r'\bсервер\b', r'\bбэкенд\b', r'\bфронтенд\b',
    r'\bбаз[аыу] данных\b', r'\bHTTP\b', r'\bендпоинт\b', r'\bэндпоинт\b',
]


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def validate_intro_quality(text: str, work_type: str = "course") -> dict[str, Any]:
    word_count = count_words(text)
    issues = []

    limits = INTRO_WORD_LIMITS.get(work_type, INTRO_WORD_LIMITS["course"])
    min_words = limits["min"]
    max_words = limits["max"]

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words} for {work_type})")

    if word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words} for {work_type})")

    tech_found = []
    for pattern in FORBIDDEN_TECH_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            tech_found.extend(matches)

    if tech_found:
        unique_tech = list(set(tech_found))
        issues.append(f"Technology terms found: {', '.join(unique_tech[:10])}")

    has_bullet_list = bool(re.search(r'^\s*[-•●]\s+', text, re.MULTILINE))
    has_numbered_list = bool(re.search(r'^\s*\d+[.)]\s+', text, re.MULTILINE))

    if has_bullet_list:
        issues.append("Contains bullet lists (not allowed in intro)")
    if has_numbered_list:
        issues.append("Contains numbered lists (not allowed in intro)")

    return {
        "valid": len(issues) == 0,
        "word_count": word_count,
        "issues": issues,
        "tech_terms_found": tech_found,
    }


def ensure_intro_academic(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
    max_retries: int = 2,
) -> DocumentArtifact:
    section_key = "intro"
    section_kind = ArtifactKind.section(section_key)
    trace_kind = ArtifactKind.llm_trace(section_key)
    prof = get_profile(profile)

    document = Document.objects.get(id=document_id)
    section = document.sections.filter(key=section_key).first()

    if not section:
        raise ValueError(f"No intro section found for document {document_id}")

    section.status = Section.Status.RUNNING
    section.save(update_fields=['status', 'updated_at'])

    def builder() -> dict[str, Any]:
        doc_profile = document.profile
        if doc_profile:
            topic_title = doc_profile.topic_title
            topic_description = doc_profile.topic_description or "Не указано"
            work_type_name = doc_profile.get_work_type_display()
            work_type_key = doc_profile.work_type
        else:
            topic_title = document.params.get('title', 'Анализ программного обеспечения')
            topic_description = document.params.get('description', 'Не указано')
            work_type_name = document.get_type_display()
            work_type_key = document.type

        limits = INTRO_WORD_LIMITS.get(work_type_key, INTRO_WORD_LIMITS["course"])
        target_words = limits["target"]

        if mock_mode:
            content_text = generate_mock_intro(topic_title)
            meta = {
                "mock": True,
                "profile": profile,
                "mode": "academic_intro",
                "work_type": work_type_key,
            }
            llm_trace_data = None
            validation = {"valid": True, "word_count": count_words(content_text), "issues": []}
        else:
            system_prompt = ACADEMIC_INTRO_SYSTEM_PROMPT_TEMPLATE.format(target_words=target_words)
            user_prompt = ACADEMIC_INTRO_USER_TEMPLATE.format(
                topic_title=topic_title,
                topic_description=topic_description,
                work_type_name=work_type_name,
            )

            budget = prof.get_budget_for_section(section_key)
            llm_client = LLMClient()

            content_text = None
            validation = None
            attempts = 0

            for attempt in range(1, max_retries + 1):
                attempts = attempt
                logger.info(f"Generating academic intro, attempt {attempt}/{max_retries}")

                result = llm_client.generate_text(
                    system=system_prompt,
                    user=user_prompt,
                    temperature=0.7,
                    max_tokens=max(3000, budget.max_output_tokens),
                    use_cache=attempt == 1,
                )

                content_text = result.text
                validation = validate_intro_quality(content_text, work_type_key)

                if validation["valid"]:
                    logger.info(f"Academic intro passed validation on attempt {attempt}")
                    break
                else:
                    logger.warning(f"Academic intro validation failed on attempt {attempt}: {validation['issues']}")
                    if attempt < max_retries:
                        user_prompt = user_prompt + f"\n\nВАЖНО: Избегайте упоминания конкретных технологий. Целевой объём: {target_words} слов."

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
                "mode": "academic_intro",
                "work_type": work_type_key,
                "target_words": target_words,
                "generation_attempts": attempts,
                "validation": validation,
            }

            llm_trace_data = {
                "operation": "intro_academic_generate",
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
                logger.info(f"Intro regenerated, invalidated: {invalidated}")

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


def generate_mock_intro(topic_title: str) -> str:
    return f"""Введение

В условиях стремительного развития информационных технологий программное обеспечение становится неотъемлемой частью практически всех сфер человеческой деятельности. Современные организации, вне зависимости от масштаба и профиля, активно используют программные системы для автоматизации процессов, управления информационными потоками, взаимодействия с пользователями и повышения общей эффективности работы.

Разработка программных решений в современных условиях требует не только получения корректного результата с точки зрения выполнения поставленных задач, но и обеспечения качества программного продукта в долгосрочной перспективе. К числу ключевых требований относятся масштабируемость, возможность дальнейшего расширения функциональности, удобство сопровождения и адаптации к изменяющимся условиям эксплуатации.

В связи с этим особую значимость приобретает применение структурированных методологий разработки программного обеспечения, а также использование концептуальных подходов, направленных на снижение сложности программных систем.

В рамках данной работы рассматривается тема: {topic_title}. Основное внимание уделяется вопросам проектирования и реализации программного решения с применением современных принципов разработки.

Целью данной работы является разработка и описание программного приложения, реализующего поставленную прикладную задачу. Для достижения поставленной цели необходимо рассмотреть теоретические основы разработки программных систем, проанализировать возможные подходы к реализации и обосновать выбор оптимального варианта.

Это тестовый текст введения, сгенерированный в режиме MOCK."""
