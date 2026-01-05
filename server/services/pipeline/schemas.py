from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SectionDraft:
    key: str
    title: str
    order: int
    content_md: str
    summary_bullets: list[str] = field(default_factory=list)
    word_count: int = 0
    char_count: int = 0
    sources_used: list[str] = field(default_factory=list)


@dataclass
class DocumentDraft:
    document_id: str
    title: str
    outline: dict[str, Any]
    sections: list[SectionDraft] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def get_section(self, key: str) -> SectionDraft | None:
        for section in self.sections:
            if section.key == key:
                return section
        return None

    def total_words(self) -> int:
        return sum(s.word_count for s in self.sections)

    def total_chars(self) -> int:
        return sum(s.char_count for s in self.sections)


@dataclass
class TocItem:
    level: int
    title: str
    section_key: str | None = None
    anchor: str | None = None
    page: int | None = None


@dataclass
class Toc:
    items: list[TocItem] = field(default_factory=list)
    generated_at: datetime | None = None


@dataclass
class QualityIssue:
    severity: str  # 'error' | 'warning'
    code: str
    message: str
    section_key: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionCoverage:
    key: str
    title: str
    required: bool
    present: bool
    word_count: int = 0
    target_min: int = 0
    target_max: int = 0
    status: str = "missing"  # missing, short, ok, long


@dataclass
class PracticeBlockCheck:
    block_name: str
    present: bool
    markers_found: list[str] = field(default_factory=list)


@dataclass
class TerminologyIssue:
    term: str
    variants: list[str] = field(default_factory=list)
    occurrences: dict[str, int] = field(default_factory=dict)


@dataclass
class SuggestedFix:
    priority: str  # high, medium, low
    code: str
    message: str
    section_key: str | None = None


@dataclass
class QualityStats:
    total_words: int = 0
    total_chars: int = 0
    section_count: int = 0
    section_words: dict[str, int] = field(default_factory=dict)
    avg_words_per_section: float = 0.0
    duration_ms: int | None = None
    required_sections_total: int = 0
    required_sections_present: int = 0
    coverage_percent: float = 0.0
    target_words_min: int = 0
    target_words_max: int = 0
    sections_coverage: list[SectionCoverage] = field(default_factory=list)
    repetition_score: float = 0.0
    section_repetition_scores: dict[str, float] = field(default_factory=dict)
    section_length_warnings: list[str] = field(default_factory=list)
    missing_required_blocks: list[PracticeBlockCheck] = field(default_factory=list)
    terminology_inconsistencies: list[TerminologyIssue] = field(default_factory=list)
    suggested_fixes: list[SuggestedFix] = field(default_factory=list)


@dataclass
class QualityReport:
    errors: list[QualityIssue] = field(default_factory=list)
    warnings: list[QualityIssue] = field(default_factory=list)
    stats: QualityStats = field(default_factory=QualityStats)
    passed: bool = True
    generated_at: datetime | None = None

    def add_error(self, code: str, message: str, section_key: str | None = None, **details):
        self.errors.append(QualityIssue(
            severity="error",
            code=code,
            message=message,
            section_key=section_key,
            details=details
        ))
        self.passed = False

    def add_warning(self, code: str, message: str, section_key: str | None = None, **details):
        self.warnings.append(QualityIssue(
            severity="warning",
            code=code,
            message=message,
            section_key=section_key,
            details=details
        ))


def section_draft_to_dict(draft: SectionDraft) -> dict:
    return {
        "key": draft.key,
        "title": draft.title,
        "order": draft.order,
        "content_md": draft.content_md,
        "summary_bullets": draft.summary_bullets,
        "word_count": draft.word_count,
        "char_count": draft.char_count,
        "sources_used": draft.sources_used,
    }


def document_draft_to_dict(draft: DocumentDraft) -> dict:
    return {
        "document_id": draft.document_id,
        "title": draft.title,
        "outline": draft.outline,
        "sections": [section_draft_to_dict(s) for s in draft.sections],
        "meta": draft.meta,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "total_words": draft.total_words(),
        "total_chars": draft.total_chars(),
    }


def toc_to_dict(toc: Toc) -> dict:
    return {
        "items": [
            {
                "level": item.level,
                "title": item.title,
                "section_key": item.section_key,
                "anchor": item.anchor,
                "page": item.page,
            }
            for item in toc.items
        ],
        "generated_at": toc.generated_at.isoformat() if toc.generated_at else None,
    }


def quality_report_to_dict(report: QualityReport) -> dict:
    return {
        "passed": report.passed,
        "errors": [
            {
                "severity": e.severity,
                "code": e.code,
                "message": e.message,
                "section_key": e.section_key,
                "details": e.details,
            }
            for e in report.errors
        ],
        "warnings": [
            {
                "severity": w.severity,
                "code": w.code,
                "message": w.message,
                "section_key": w.section_key,
                "details": w.details,
            }
            for w in report.warnings
        ],
        "stats": {
            "total_words": report.stats.total_words,
            "total_chars": report.stats.total_chars,
            "section_count": report.stats.section_count,
            "section_words": report.stats.section_words,
            "avg_words_per_section": report.stats.avg_words_per_section,
            "duration_ms": report.stats.duration_ms,
            "required_sections_total": report.stats.required_sections_total,
            "required_sections_present": report.stats.required_sections_present,
            "coverage_percent": report.stats.coverage_percent,
            "target_words_min": report.stats.target_words_min,
            "target_words_max": report.stats.target_words_max,
            "sections_coverage": [
                {
                    "key": sc.key,
                    "title": sc.title,
                    "required": sc.required,
                    "present": sc.present,
                    "word_count": sc.word_count,
                    "target_min": sc.target_min,
                    "target_max": sc.target_max,
                    "status": sc.status,
                }
                for sc in report.stats.sections_coverage
            ],
            "repetition_score": report.stats.repetition_score,
            "section_repetition_scores": report.stats.section_repetition_scores,
            "section_length_warnings": report.stats.section_length_warnings,
            "missing_required_blocks": [
                {
                    "block_name": b.block_name,
                    "present": b.present,
                    "markers_found": b.markers_found,
                }
                for b in report.stats.missing_required_blocks
            ],
            "terminology_inconsistencies": [
                {
                    "term": t.term,
                    "variants": t.variants,
                    "occurrences": t.occurrences,
                }
                for t in report.stats.terminology_inconsistencies
            ],
            "suggested_fixes": [
                {
                    "priority": f.priority,
                    "code": f.code,
                    "message": f.message,
                    "section_key": f.section_key,
                }
                for f in report.stats.suggested_fixes
            ],
        },
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
    }
