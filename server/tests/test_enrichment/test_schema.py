import pytest
from services.enrichment.schema import (
    EnrichmentPlan,
    EnrichmentNeed,
    EnrichmentResult,
    EnrichmentReport,
    enrichment_plan_to_dict,
    enrichment_report_to_dict,
    enrichment_result_to_dict,
)


class TestEnrichmentNeed:
    def test_create_need(self):
        need = EnrichmentNeed(
            section_key="intro",
            current_words=100,
            target_words_min=500,
            target_words_max=1000,
            deficit_words=400,
            priority=8,
            reason="Section is too short",
        )

        assert need.section_key == "intro"
        assert need.current_words == 100
        assert need.deficit_words == 400
        assert need.priority == 8


class TestEnrichmentPlan:
    def test_create_empty_plan(self):
        plan = EnrichmentPlan(
            sections_to_enrich=[],
            total_deficit=0,
            facts_available=0,
        )

        assert not plan.needs_enrichment()
        assert plan.total_deficit == 0

    def test_create_plan_with_needs(self):
        need = EnrichmentNeed(
            section_key="intro",
            current_words=100,
            target_words_min=500,
            target_words_max=1000,
            deficit_words=400,
            priority=8,
            reason="Too short",
        )
        plan = EnrichmentPlan(
            sections_to_enrich=[need],
            total_deficit=400,
            facts_available=10,
        )

        assert plan.needs_enrichment()
        assert len(plan.sections_to_enrich) == 1

    def test_plan_to_dict(self):
        need = EnrichmentNeed(
            section_key="intro",
            current_words=100,
            target_words_min=500,
            target_words_max=1000,
            deficit_words=400,
            priority=8,
            reason="Too short",
        )
        plan = EnrichmentPlan(
            sections_to_enrich=[need],
            total_deficit=400,
            facts_available=10,
        )

        data = enrichment_plan_to_dict(plan)

        assert data["total_deficit"] == 400
        assert data["facts_available"] == 10
        assert len(data["sections_to_enrich"]) == 1
        assert data["sections_to_enrich"][0]["section_key"] == "intro"


class TestEnrichmentResult:
    def test_create_successful_result(self):
        result = EnrichmentResult(
            section_key="intro",
            original_text="Short text.",
            enriched_text="Short text. With additional content from facts.",
            facts_used=["fact_1", "fact_2"],
            words_added=6,
            success=True,
        )

        assert result.success
        assert result.words_added == 6
        assert len(result.facts_used) == 2

    def test_create_failed_result(self):
        result = EnrichmentResult(
            section_key="intro",
            original_text="Short text.",
            enriched_text="Short text.",
            success=False,
            error="No facts available",
        )

        assert not result.success
        assert result.error == "No facts available"
        assert result.words_added == 0

    def test_result_to_dict(self):
        result = EnrichmentResult(
            section_key="intro",
            original_text="Short text.",
            enriched_text="Short text. Enriched.",
            facts_used=["fact_1"],
            words_added=1,
            success=True,
        )

        data = enrichment_result_to_dict(result)

        assert data["section_key"] == "intro"
        assert data["success"] is True
        assert data["words_added"] == 1


class TestEnrichmentReport:
    def test_create_empty_report(self):
        report = EnrichmentReport(
            version="v1",
            sections_enriched=[],
            total_words_added=0,
            total_facts_used=0,
        )

        assert report.total_words_added == 0
        assert len(report.sections_enriched) == 0

    def test_create_report_with_results(self):
        result = EnrichmentResult(
            section_key="intro",
            original_text="Short.",
            enriched_text="Short. Extended.",
            facts_used=["f1"],
            words_added=1,
            success=True,
        )
        report = EnrichmentReport(
            version="v1",
            sections_enriched=[result],
            total_words_added=1,
            total_facts_used=1,
        )

        assert report.total_words_added == 1
        assert len(report.sections_enriched) == 1

    def test_report_to_dict(self):
        result = EnrichmentResult(
            section_key="intro",
            original_text="Short.",
            enriched_text="Short. Extended.",
            facts_used=["f1"],
            words_added=1,
            success=True,
        )
        report = EnrichmentReport(
            version="v1",
            sections_enriched=[result],
            total_words_added=1,
            total_facts_used=1,
        )

        data = enrichment_report_to_dict(report)

        assert data["version"] == "v1"
        assert data["total_words_added"] == 1
        assert data["total_facts_used"] == 1
        assert len(data["sections_enriched"]) == 1
