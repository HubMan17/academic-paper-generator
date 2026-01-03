from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnrichmentNeed:
    section_key: str
    current_words: int
    target_words_min: int
    target_words_max: int
    deficit_words: int
    priority: int
    reason: str


@dataclass
class EnrichmentPlan:
    version: str = "v1"
    sections_to_enrich: list[EnrichmentNeed] = field(default_factory=list)
    total_deficit: int = 0
    facts_available: int = 0

    def needs_enrichment(self) -> bool:
        return len(self.sections_to_enrich) > 0


@dataclass
class FactReference:
    fact_id: str
    text: str
    relevance: float = 1.0


@dataclass
class EnrichmentResult:
    section_key: str
    original_text: str
    enriched_text: str
    facts_used: list[str] = field(default_factory=list)
    words_added: int = 0
    success: bool = True
    error: str | None = None


@dataclass
class EnrichmentReport:
    version: str = "v1"
    sections_enriched: list[EnrichmentResult] = field(default_factory=list)
    total_words_added: int = 0
    total_facts_used: int = 0


def enrichment_need_to_dict(need: EnrichmentNeed) -> dict[str, Any]:
    return {
        "section_key": need.section_key,
        "current_words": need.current_words,
        "target_words_min": need.target_words_min,
        "target_words_max": need.target_words_max,
        "deficit_words": need.deficit_words,
        "priority": need.priority,
        "reason": need.reason,
    }


def enrichment_plan_to_dict(plan: EnrichmentPlan) -> dict[str, Any]:
    return {
        "version": plan.version,
        "sections_to_enrich": [enrichment_need_to_dict(n) for n in plan.sections_to_enrich],
        "total_deficit": plan.total_deficit,
        "facts_available": plan.facts_available,
    }


def enrichment_result_to_dict(result: EnrichmentResult) -> dict[str, Any]:
    return {
        "section_key": result.section_key,
        "original_text": result.original_text,
        "enriched_text": result.enriched_text,
        "facts_used": result.facts_used,
        "words_added": result.words_added,
        "success": result.success,
        "error": result.error,
    }


def enrichment_report_to_dict(report: EnrichmentReport) -> dict[str, Any]:
    return {
        "version": report.version,
        "sections_enriched": [enrichment_result_to_dict(r) for r in report.sections_enriched],
        "total_words_added": report.total_words_added,
        "total_facts_used": report.total_facts_used,
    }
