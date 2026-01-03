import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.projects.models import Document, DocumentArtifact
from services.pipeline.ensure import ensure_artifact, get_success_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.schemas import (
    QualityReport, QualityStats, SectionCoverage,
    quality_report_to_dict,
)
from services.pipeline.specs import get_section_spec, get_all_section_keys

logger = logging.getLogger(__name__)


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

        outline_artifact = get_success_artifact(document_id, ArtifactKind.OUTLINE.value)
        outline = outline_artifact.data_json if outline_artifact else None

        if not outline:
            report.add_error("NO_OUTLINE", "Outline not found")

        draft_artifact = get_success_artifact(document_id, ArtifactKind.DOCUMENT_DRAFT.value)
        draft = draft_artifact.data_json if draft_artifact else None

        section_keys = get_all_section_keys()
        total_words = 0
        total_chars = 0
        section_words = {}
        section_count = 0
        seen_titles = set()

        required_total = 0
        required_present = 0
        target_words_min = 0
        target_words_max = 0
        sections_coverage = []

        for key in section_keys:
            spec = get_section_spec(key)
            section_artifact = get_success_artifact(document_id, ArtifactKind.section(key))

            if outline:
                outline_has_section = any(s.get("key") == key for s in outline.get("sections", []))
            else:
                outline_has_section = False

            is_required = spec.required if spec else False
            if is_required:
                required_total += 1

            min_words = spec.target_words[0] if spec else 0
            max_words = spec.target_words[1] if spec else 0
            target_words_min += min_words
            target_words_max += max_words

            if not section_artifact:
                sections_coverage.append(SectionCoverage(
                    key=key,
                    title=spec.title if spec else key,
                    required=is_required,
                    present=False,
                    word_count=0,
                    target_min=min_words,
                    target_max=max_words,
                    status="missing",
                ))

                if is_required:
                    report.add_error(
                        "MISSING_SECTION",
                        f"Required section '{key}' not generated",
                        section_key=key
                    )
                elif outline_has_section:
                    report.add_warning(
                        "OUTLINE_SECTION_MISSING",
                        f"Section '{key}' in outline but not generated",
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
                title=spec.title if spec else key,
                required=is_required,
                present=True,
                word_count=words,
                target_min=min_words,
                target_max=max_words,
                status=section_status,
            ))

            title = None
            if draft:
                for s in draft.get("sections", []):
                    if s.get("key") == key:
                        title = s.get("title")
                        break

            if title:
                if title in seen_titles:
                    report.add_warning(
                        "DUPLICATE_TITLE",
                        f"Title '{title}' appears multiple times",
                        section_key=key
                    )
                seen_titles.add(title)

            is_repetitive, ratio = check_ngram_repetition(content)
            if is_repetitive:
                report.add_warning(
                    "HIGH_REPETITION",
                    f"Section '{key}' has high 3-gram repetition ({ratio:.1%})",
                    section_key=key,
                    repetition_ratio=ratio
                )

            if not outline_has_section and outline:
                report.add_warning(
                    "SECTION_NOT_IN_OUTLINE",
                    f"Section '{key}' generated but not in outline",
                    section_key=key
                )

        coverage_percent = round(required_present / required_total * 100, 1) if required_total > 0 else 100.0

        if total_words < target_words_min * 0.5:
            report.add_warning(
                "DOCUMENT_TOO_SHORT",
                f"Document has {total_words} words, expected at least {target_words_min}",
                actual=total_words,
                expected_min=target_words_min
            )

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
        )

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
