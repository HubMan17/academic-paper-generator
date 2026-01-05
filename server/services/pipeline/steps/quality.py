import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.projects.models import Document, DocumentArtifact
from services.pipeline.ensure import ensure_artifact, get_success_artifact, get_outline_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.schemas import (
    QualityReport, QualityStats, SectionCoverage,
    PracticeBlockCheck, TerminologyIssue, SuggestedFix,
    quality_report_to_dict,
)
from services.pipeline.specs import get_section_spec

logger = logging.getLogger(__name__)

PRACTICE_REQUIRED_BLOCKS = [
    ("requirements", ["требовани", "задач", "постановка", "цел"]),
    ("architecture", ["архитектур", "структур", "компонент", "модул"]),
    ("data", ["данн", "модел", "сущност", "таблиц", "схем"]),
    ("api", ["api", "endpoint", "интерфейс", "метод", "запрос"]),
    ("testing", ["тест", "проверк", "валидац", "результат"]),
]

TERMINOLOGY_GROUPS = [
    ("api", ["API", "АПИ", "интерфейс программирования"]),
    ("endpoint", ["endpoint", "эндпоинт", "точка доступа", "маршрут"]),
    ("database", ["база данных", "БД", "СУБД", "хранилище"]),
    ("frontend", ["frontend", "фронтенд", "клиентская часть", "интерфейс пользователя"]),
    ("backend", ["backend", "бэкенд", "серверная часть"]),
]


def count_words(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def extract_ngrams(text: str, n: int = 3) -> list[tuple[str, ...]]:
    words = re.findall(r'\b\w+\b', text.lower())
    if len(words) < n:
        return []
    return [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]


def check_ngram_repetition(text: str, threshold: float = 0.1) -> tuple[bool, float]:
    ngrams = extract_ngrams(text, 3)
    if len(ngrams) < 10:
        return False, 0.0

    counter = Counter(ngrams)
    repeated = sum(1 for count in counter.values() if count > 2)
    ratio = repeated / len(counter) if counter else 0.0

    return ratio > threshold, round(ratio, 3)


def check_practice_blocks(text: str) -> list[PracticeBlockCheck]:
    text_lower = text.lower()
    results = []

    for block_name, markers in PRACTICE_REQUIRED_BLOCKS:
        found_markers = []
        for marker in markers:
            if marker.lower() in text_lower:
                found_markers.append(marker)

        results.append(PracticeBlockCheck(
            block_name=block_name,
            present=len(found_markers) > 0,
            markers_found=found_markers
        ))

    return results


def check_terminology_consistency(all_text: str) -> list[TerminologyIssue]:
    issues = []

    for term, variants in TERMINOLOGY_GROUPS:
        occurrences = {}
        for variant in variants:
            count = len(re.findall(re.escape(variant), all_text, re.IGNORECASE))
            if count > 0:
                occurrences[variant] = count

        if len(occurrences) > 1:
            issues.append(TerminologyIssue(
                term=term,
                variants=list(occurrences.keys()),
                occurrences=occurrences
            ))

    return issues


def generate_suggested_fixes(report: QualityReport) -> list[SuggestedFix]:
    fixes = []

    for error in report.errors:
        if error.code == "MISSING_SECTION":
            fixes.append(SuggestedFix(
                priority="high",
                code="ADD_SECTION",
                message=f"Добавить секцию '{error.section_key}'",
                section_key=error.section_key
            ))
        elif error.code == "EMPTY_SECTION":
            fixes.append(SuggestedFix(
                priority="high",
                code="FILL_SECTION",
                message=f"Заполнить пустую секцию '{error.section_key}'",
                section_key=error.section_key
            ))

    for warning in report.warnings:
        if warning.code == "SECTION_TOO_SHORT":
            fixes.append(SuggestedFix(
                priority="medium",
                code="EXPAND_SECTION",
                message=f"Расширить секцию '{warning.section_key}' до минимального объёма",
                section_key=warning.section_key
            ))
        elif warning.code == "HIGH_REPETITION":
            fixes.append(SuggestedFix(
                priority="medium",
                code="REDUCE_REPETITION",
                message=f"Снизить повторяемость в секции '{warning.section_key}'",
                section_key=warning.section_key
            ))

    for block in report.stats.missing_required_blocks:
        if not block.present:
            fixes.append(SuggestedFix(
                priority="medium",
                code="ADD_PRACTICE_BLOCK",
                message=f"Добавить блок '{block.block_name}' в практическую часть",
                section_key=None
            ))

    for term_issue in report.stats.terminology_inconsistencies:
        fixes.append(SuggestedFix(
            priority="low",
            code="UNIFY_TERMINOLOGY",
            message=f"Унифицировать терминологию: {term_issue.term} (варианты: {', '.join(term_issue.variants)})",
            section_key=None
        ))

    return fixes


def ensure_quality_report(
    document_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    start_time_ms: int | None = None,
) -> DocumentArtifact:
    kind = ArtifactKind.QUALITY_REPORT.value

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)
        report = QualityReport(generated_at=datetime.utcnow())

        outline_artifact = get_outline_artifact(document_id)
        outline = outline_artifact.data_json if outline_artifact else None

        if not outline:
            report.add_error("NO_OUTLINE", "Outline not found")

        draft_artifact = get_success_artifact(document_id, ArtifactKind.DOCUMENT_DRAFT.value)
        draft = draft_artifact.data_json if draft_artifact else None

        db_sections = list(document.sections.order_by('order'))
        total_words = 0
        total_chars = 0
        section_words = {}
        section_count = 0
        seen_titles = set()

        required_total = len(db_sections)
        required_present = 0
        target_words_min = 0
        target_words_max = 0
        sections_coverage = []

        section_repetition_scores = {}
        section_length_warnings = []
        all_practice_text = ""

        for db_section in db_sections:
            key = db_section.key
            spec = get_section_spec(key)
            section_artifact = get_success_artifact(document_id, ArtifactKind.section(key))

            is_required = True
            min_words = spec.target_words[0] if spec else 600
            max_words = spec.target_words[1] if spec else 1200
            target_words_min += min_words
            target_words_max += max_words

            if not section_artifact:
                sections_coverage.append(SectionCoverage(
                    key=key,
                    title=db_section.title or key,
                    required=is_required,
                    present=False,
                    word_count=0,
                    target_min=min_words,
                    target_max=max_words,
                    status="missing",
                ))

                report.add_error(
                    "MISSING_SECTION",
                    f"Required section '{key}' not generated",
                    section_key=key
                )
                continue

            content = section_artifact.content_text or ""
            words = count_words(content)
            chars = len(content)

            section_words[key] = words
            total_words += words
            total_chars += chars
            section_count += 1

            if is_required:
                required_present += 1

            section_status = "ok"
            if not content.strip():
                section_status = "empty"
                report.add_error(
                    "EMPTY_SECTION",
                    f"Section '{key}' is empty",
                    section_key=key
                )
            elif spec:
                if words < min_words * 0.5:
                    section_status = "short"
                    report.add_warning(
                        "SECTION_TOO_SHORT",
                        f"Section '{key}' has {words} words, expected at least {min_words}",
                        section_key=key,
                        actual=words,
                        expected_min=min_words
                    )
                elif words > max_words * 1.5:
                    section_status = "long"
                    report.add_warning(
                        "SECTION_TOO_LONG",
                        f"Section '{key}' has {words} words, expected at most {max_words}",
                        section_key=key,
                        actual=words,
                        expected_max=max_words
                    )

            sections_coverage.append(SectionCoverage(
                key=key,
                title=db_section.title or key,
                required=is_required,
                present=True,
                word_count=words,
                target_min=min_words,
                target_max=max_words,
                status=section_status,
            ))

            section_title = db_section.title or key
            if section_title in seen_titles:
                report.add_warning(
                    "DUPLICATE_TITLE",
                    f"Title '{section_title}' appears multiple times",
                    section_key=key
                )
            seen_titles.add(section_title)

            is_repetitive, ratio = check_ngram_repetition(content)
            section_repetition_scores[key] = ratio
            if is_repetitive:
                report.add_warning(
                    "HIGH_REPETITION",
                    f"Section '{key}' has high 3-gram repetition ({ratio:.1%})",
                    section_key=key,
                    repetition_ratio=ratio
                )

            if section_status == "short":
                section_length_warnings.append(f"{key}: слишком короткий ({words} слов, мин. {min_words})")
            elif section_status == "long":
                section_length_warnings.append(f"{key}: слишком длинный ({words} слов, макс. {max_words})")

            is_practice = key.startswith("practice") or "implementation" in key or "testing" in key
            if is_practice:
                all_practice_text += content + "\n"

        coverage_percent = round(required_present / required_total * 100, 1) if required_total > 0 else 100.0

        if total_words < target_words_min * 0.5:
            report.add_warning(
                "DOCUMENT_TOO_SHORT",
                f"Document has {total_words} words, expected at least {target_words_min}",
                actual=total_words,
                expected_min=target_words_min
            )

        avg_repetition = (
            sum(section_repetition_scores.values()) / len(section_repetition_scores)
            if section_repetition_scores else 0.0
        )

        practice_blocks = check_practice_blocks(all_practice_text) if all_practice_text else []
        missing_blocks = [b for b in practice_blocks if not b.present]

        for block in missing_blocks:
            report.add_warning(
                "MISSING_PRACTICE_BLOCK",
                f"Practice section missing '{block.block_name}' block",
                section_key=None,
                block_name=block.block_name
            )

        all_text = ""
        for db_section in db_sections:
            section_artifact = get_success_artifact(document_id, ArtifactKind.section(db_section.key))
            if section_artifact and section_artifact.content_text:
                all_text += section_artifact.content_text + "\n"

        terminology_issues = check_terminology_consistency(all_text)

        report.stats = QualityStats(
            total_words=total_words,
            total_chars=total_chars,
            section_count=section_count,
            section_words=section_words,
            avg_words_per_section=round(total_words / section_count, 1) if section_count else 0.0,
            duration_ms=start_time_ms,
            required_sections_total=required_total,
            required_sections_present=required_present,
            coverage_percent=coverage_percent,
            target_words_min=target_words_min,
            target_words_max=target_words_max,
            sections_coverage=sections_coverage,
            repetition_score=round(avg_repetition, 3),
            section_repetition_scores=section_repetition_scores,
            section_length_warnings=section_length_warnings,
            missing_required_blocks=practice_blocks,
            terminology_inconsistencies=terminology_issues,
        )

        suggested_fixes = generate_suggested_fixes(report)
        report.stats.suggested_fixes = suggested_fixes

        return {
            "data_json": quality_report_to_dict(report),
            "format": DocumentArtifact.Format.JSON,
            "meta": {
                "passed": report.passed,
                "error_count": len(report.errors),
                "warning_count": len(report.warnings),
            },
        }

    return ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
    )
