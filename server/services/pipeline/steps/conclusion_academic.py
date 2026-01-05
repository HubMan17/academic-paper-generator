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

CONCLUSION_SYSTEM_PROMPT_TEMPLATE = """Ты пишешь ЗАКЛЮЧЕНИЕ академической работы на русском языке.

## ОБЯЗАТЕЛЬНАЯ СТРУКТУРА ЗАКЛЮЧЕНИЯ (по ГОСТ 7.32-2001)

Заключение должно быть написано СПЛОШНЫМ ТЕКСТОМ без нумерованных подзаголовков.
В тексте должны быть ПОСЛЕДОВАТЕЛЬНО раскрыты следующие элементы:

1. **Краткое резюме работы** (1 абзац)
   - Напомнить тему и цель работы
   - Обобщить проделанную работу в 2-3 предложениях

2. **Основные результаты теоретической части** (1-2 абзаца)
   - Какие теоретические вопросы были изучены?
   - Какие методы, подходы, принципы были рассмотрены?
   - Какие выводы были сделаны в теоретических разделах?

3. **Основные результаты практической части** (2-3 абзаца)
   - Что было разработано/реализовано?
   - Какие технические решения были приняты?
   - Какая функциональность была реализована?
   - Какие результаты были достигнуты?

4. **Соответствие поставленным задачам** (1 абзац)
   - Подтверждение выполнения всех задач из введения
   - Соответствие результатов поставленной цели
   - Формулировка: "В ходе работы были решены все поставленные задачи..."

5. **Практическая значимость результатов** (1 абзац)
   - Где и как можно применить полученные результаты?
   - Какую пользу приносит разработанное решение?
   - Для каких задач это будет полезно?

6. **Перспективы развития** (1 абзац)
   - Какие направления для дальнейшего развития существуют?
   - Какие улучшения можно внести?
   - Какие задачи можно решить в будущем?

## СТРОГИЕ ПРАВИЛА

– НЕ использовать маркированные или нумерованные списки в тексте
– Писать только сплошными абзацами (каждый абзац 3-6 предложений)
– Использовать академический стиль
– Опираться на предоставленные summaries разделов
– Избегать повторения одних и тех же формулировок
– Каждый абзац должен логически переходить к следующему

## СТИЛЬ НАПИСАНИЯ

– Использовать прошедшее время для описания проделанной работы
– Конкретные результаты: "было изучено", "была разработана", "было реализовано"
– Избегать водянистых фраз: "особое значение приобретает", "в современных условиях"
– Фокус на РЕЗУЛЬТАТАХ работы, а не на процессе

Целевой объём: {target_words} слов на русском языке."""

CONCLUSION_USER_TEMPLATE = """## ДАННЫЕ О РАБОТЕ

**Тема работы:** {topic_title}

**Описание работы:**
{topic_description}

**Тип работы:** {work_type_name}

**Цель работы:**
{work_goal}

**Задачи работы:**
{work_tasks}

## РЕЗУЛЬТАТЫ РАЗДЕЛОВ

**Теоретическая часть:**
{theory_summaries}

**Практическая часть:**
{practice_summaries}

## ЗАДАНИЕ

Напишите заключение к данной работе, следуя структуре и академическому стилю.
Используйте предоставленные summaries разделов для описания результатов.
Убедитесь, что все задачи отмечены как выполненные, и подтвердите достижение цели работы."""

CONCLUSION_WORD_LIMITS = {
    "referat": {"min": 250, "max": 450, "target": "300–400"},
    "course": {"min": 400, "max": 700, "target": "500–650"},
    "diploma": {"min": 600, "max": 1100, "target": "700–1000"},
}


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def validate_conclusion_quality(
    text: str,
    work_type: str = "course",
    custom_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    word_count = count_words(text)
    issues = []

    if custom_limits:
        limits = custom_limits
    else:
        limits = CONCLUSION_WORD_LIMITS.get(work_type, CONCLUSION_WORD_LIMITS["course"])

    min_words = limits["min"]
    max_words = limits["max"]

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words} for {work_type})")

    if word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words} for {work_type})")

    has_bullet_list = bool(re.search(r'^\s*[-•●]\s+', text, re.MULTILINE))
    has_numbered_list = bool(re.search(r'^\s*\d+[.)]\s+', text, re.MULTILINE))

    if has_bullet_list:
        issues.append("Contains bullet lists (not allowed in conclusion)")
    if has_numbered_list:
        issues.append("Contains numbered lists (not allowed in conclusion)")

    return {
        "valid": len(issues) == 0,
        "word_count": word_count,
        "issues": issues,
    }


def get_section_summaries(document: Document, chapter_key: str) -> str:
    sections = document.sections.filter(chapter_key=chapter_key).order_by('order')

    summaries = []
    for section in sections:
        summary_artifact = DocumentArtifact.objects.filter(
            document=document,
            section=section,
            kind=ArtifactKind.section_summary(section.key),
            meta__status='success',
        ).order_by('-created_at').first()

        if summary_artifact and summary_artifact.content_text:
            summaries.append(f"**{section.title}:**\n{summary_artifact.content_text}")

    return "\n\n".join(summaries) if summaries else "Результаты не доступны"


def get_work_goal_and_tasks(document: Document) -> tuple[str, str]:
    intro_section = document.sections.filter(key='intro').first()
    if not intro_section or not intro_section.text_current:
        return (
            "Разработать программное решение согласно описанию темы",
            "Задачи работы были сформулированы во введении"
        )

    intro_text = intro_section.text_current

    goal_match = re.search(r'Целью.*?является\s+(.+?)\.', intro_text, re.IGNORECASE | re.DOTALL)
    goal = goal_match.group(1).strip() if goal_match else "достижение поставленных целей согласно теме работы"

    tasks_section = re.search(
        r'(?:задач[иа]|задачами|решить следующие задачи)[:\s]+(.+?)(?:\n\n|\. Объект|\. Метод|\. Практическ)',
        intro_text,
        re.IGNORECASE | re.DOTALL
    )

    if tasks_section:
        tasks_text = tasks_section.group(1).strip()
        tasks = re.sub(r'\s+', ' ', tasks_text)
    else:
        tasks = "выполнение всех поставленных задач согласно плану работы"

    return goal, tasks


def ensure_conclusion_section(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
    mock_mode: bool = False,
    max_retries: int = 2,
) -> DocumentArtifact:
    section_kind = ArtifactKind.section('conclusion')
    trace_kind = ArtifactKind.llm_trace('conclusion')
    prof = get_profile(profile)

    document = Document.objects.get(id=document_id)
    section = document.sections.filter(key='conclusion').first()

    if not section:
        raise ValueError(f"No conclusion section found for document {document_id}")

    section.status = Section.Status.RUNNING
    section.save(update_fields=['status', 'updated_at'])

    def builder() -> dict[str, Any]:
        doc_profile = document.profile
        if doc_profile:
            topic_title = doc_profile.topic_title
            topic_description = doc_profile.topic_description or "Описание не предоставлено"
            work_type_key = doc_profile.work_type
            work_type_name = doc_profile.get_work_type_display()
        else:
            topic_title = document.params.get('title', 'Разработка программного обеспечения')
            topic_description = document.params.get('description', 'Описание не предоставлено')
            work_type_key = document.type
            work_type_name = document.get_type_display()

        limits = CONCLUSION_WORD_LIMITS.get(work_type_key, CONCLUSION_WORD_LIMITS["course"])
        target_words = limits["target"]

        theory_summaries = get_section_summaries(document, 'theory')
        practice_summaries = get_section_summaries(document, 'practice')
        work_goal, work_tasks = get_work_goal_and_tasks(document)

        if mock_mode:
            content_text = generate_mock_conclusion(topic_title, work_type_key)
            meta = {
                "mock": True,
                "profile": profile,
                "mode": "conclusion_academic",
                "work_type": work_type_key,
            }
            llm_trace_data = None
            validation = {"valid": True, "word_count": count_words(content_text), "issues": []}
        else:
            system_prompt = CONCLUSION_SYSTEM_PROMPT_TEMPLATE.format(target_words=target_words)
            user_prompt = CONCLUSION_USER_TEMPLATE.format(
                topic_title=topic_title,
                topic_description=topic_description,
                work_type_name=work_type_name,
                work_goal=work_goal,
                work_tasks=work_tasks,
                theory_summaries=theory_summaries,
                practice_summaries=practice_summaries,
            )

            budget = prof.get_budget_for_section('conclusion')
            llm_client = LLMClient()

            content_text = None
            validation = None
            attempts = 0

            for attempt in range(1, max_retries + 1):
                attempts = attempt
                logger.info(f"Generating conclusion section, attempt {attempt}/{max_retries}")

                result = llm_client.generate_text(
                    system=system_prompt,
                    user=user_prompt,
                    temperature=0.7,
                    max_tokens=max(3000, budget.max_output_tokens),
                    use_cache=attempt == 1,
                )

                content_text = result.text
                validation = validate_conclusion_quality(content_text, work_type_key, limits)

                if validation["valid"]:
                    logger.info(f"Conclusion section passed validation on attempt {attempt}")
                    break
                else:
                    logger.warning(f"Conclusion validation failed on attempt {attempt}: {validation['issues']}")
                    if attempt < max_retries:
                        user_prompt = user_prompt + f"\n\nВАЖНО: Пишите сплошными абзацами БЕЗ списков. Целевой объём: {target_words} слов."

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
                "mode": "conclusion_academic",
                "work_type": work_type_key,
                "target_words": target_words,
                "generation_attempts": attempts,
                "validation": validation,
            }

            llm_trace_data = {
                "operation": "conclusion_academic_generate",
                "section_key": "conclusion",
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
            section_key='conclusion',
        )

        is_new_artifact = artifact.id != (existing_artifact.id if existing_artifact else None)

        if is_new_artifact:
            invalidated = invalidate_assembly_artifacts(document_id)
            if invalidated:
                logger.info(f"Conclusion section regenerated, invalidated: {invalidated}")

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


def generate_mock_conclusion(topic_title: str, work_type: str) -> str:
    return f"""В ходе выполнения данной работы была проведена комплексная разработка программного решения по теме "{topic_title}". Работа включала как теоретическое исследование вопроса, так и практическую реализацию функционального приложения.

В теоретической части работы были изучены фундаментальные принципы разработки программного обеспечения, рассмотрены современные подходы к проектированию информационных систем, проанализированы различные архитектурные паттерны и методологии разработки. Особое внимание было уделено вопросам обеспечения качества программных продуктов и применению передовых практик программной инженерии.

В практической части работы была спроектирована и реализована информационная система, отвечающая поставленным требованиям. Разработанное решение обеспечивает необходимую функциональность для решения задач предметной области. В процессе разработки были приняты обоснованные технические решения, направленные на достижение требуемого качества программного продукта. Реализованная система прошла необходимое тестирование, подтвердившее корректность работы основных компонентов.

В ходе работы были решены все поставленные задачи: проведён анализ предметной области, изучены теоретические основы разработки, спроектирована архитектура системы, реализована требуемая функциональность, проведено тестирование разработанного решения. Достигнутые результаты полностью соответствуют цели работы.

Практическая значимость разработанного решения заключается в возможности его применения для автоматизации соответствующих процессов и повышения эффективности работы пользователей системы. Реализованная функциональность может быть использована в реальных условиях для решения практических задач.

Перспективы дальнейшего развития системы включают расширение функциональности, оптимизацию производительности, улучшение пользовательского интерфейса и интеграцию с дополнительными внешними сервисами. Разработанное решение создаёт прочную основу для последующей эволюции системы в соответствии с изменяющимися требованиями.

Это тестовый текст заключения, сгенерированный в режиме MOCK."""
