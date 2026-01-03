import pytest
from services.enrichment.analyzer import (
    detect_short_sections,
    count_words,
    select_relevant_facts,
)
from services.enrichment.schema import EnrichmentPlan, EnrichmentNeed


class TestCountWords:
    def test_count_russian_words(self):
        text = "Это простой тест для подсчёта слов"
        count = count_words(text)
        assert count == 6

    def test_count_english_words(self):
        text = "This is a simple test"
        count = count_words(text)
        assert count == 5

    def test_count_mixed_words(self):
        text = "Django REST API для создания backend приложений"
        count = count_words(text)
        assert count == 7

    def test_empty_text(self):
        assert count_words("") == 0
        assert count_words("   ") == 0

    def test_punctuation_ignored(self):
        text = "Привет, мир! Как дела?"
        count = count_words(text)
        assert count == 4


class TestDetectShortSections:
    def test_detect_short_section(self):
        sections = [
            {"key": "intro", "text_current": "Короткий текст."},
        ]
        specs = [
            {"key": "intro", "target_words_min": 500, "target_words_max": 1000},
        ]

        plan = detect_short_sections(sections, specs)

        assert plan.needs_enrichment()
        assert len(plan.sections_to_enrich) == 1
        assert plan.sections_to_enrich[0].section_key == "intro"
        assert plan.sections_to_enrich[0].deficit_words > 0

    def test_no_enrichment_needed(self):
        long_text = "Слово " * 600
        sections = [
            {"key": "intro", "text_current": long_text},
        ]
        specs = [
            {"key": "intro", "target_words_min": 500, "target_words_max": 1000},
        ]

        plan = detect_short_sections(sections, specs)

        assert not plan.needs_enrichment()
        assert len(plan.sections_to_enrich) == 0

    def test_multiple_sections(self):
        sections = [
            {"key": "intro", "text_current": "Короткий текст."},
            {"key": "theory", "text_current": "Слово " * 600},
            {"key": "practice", "text_current": "Ещё короткий."},
        ]
        specs = [
            {"key": "intro", "target_words_min": 500, "target_words_max": 1000},
            {"key": "theory", "target_words_min": 500, "target_words_max": 1000},
            {"key": "practice", "target_words_min": 400, "target_words_max": 800},
        ]

        plan = detect_short_sections(sections, specs)

        assert plan.needs_enrichment()
        assert len(plan.sections_to_enrich) == 2
        keys = [n.section_key for n in plan.sections_to_enrich]
        assert "intro" in keys
        assert "practice" in keys
        assert "theory" not in keys

    def test_priority_ordering(self):
        sections = [
            {"key": "intro", "text_current": "Немного текста здесь."},
            {"key": "theory", "text_current": "Слово."},
        ]
        specs = [
            {"key": "intro", "target_words_min": 500, "target_words_max": 1000},
            {"key": "theory", "target_words_min": 500, "target_words_max": 1000},
        ]

        plan = detect_short_sections(sections, specs)

        assert len(plan.sections_to_enrich) == 2
        assert plan.sections_to_enrich[0].priority >= plan.sections_to_enrich[1].priority

    def test_missing_section_in_specs(self):
        sections = [
            {"key": "intro", "text_current": "Текст."},
            {"key": "unknown", "text_current": "Неизвестная секция."},
        ]
        specs = [
            {"key": "intro", "target_words_min": 500, "target_words_max": 1000},
        ]

        plan = detect_short_sections(sections, specs)

        keys = [n.section_key for n in plan.sections_to_enrich]
        assert "unknown" not in keys


class TestSelectRelevantFacts:
    def test_select_by_tags(self):
        facts = {
            "frameworks": [
                {"name": "Django", "version": "5.0"},
                {"name": "React", "version": "18"},
            ],
            "modules": [
                {"name": "auth", "description": "Authentication module"},
            ],
        }
        tags = ["frameworks", "tech_stack"]

        selected = select_relevant_facts(facts, "intro", tags)

        assert len(selected) >= 1

    def test_empty_tags(self):
        facts = {
            "frameworks": [
                {"name": "Django", "version": "5.0"},
            ],
        }

        selected = select_relevant_facts(facts, "intro", [])

        assert isinstance(selected, list)

    def test_empty_facts(self):
        selected = select_relevant_facts({}, "intro", ["backend"])
        assert len(selected) == 0

    def test_max_facts_limit(self):
        facts = {
            "modules": [
                {"name": f"module_{i}", "description": f"Module {i}"}
                for i in range(50)
            ],
        }

        selected = select_relevant_facts(facts, "intro", [], max_facts=10)

        assert len(selected) <= 10


class TestEnrichmentPlan:
    def test_needs_enrichment_true(self):
        plan = EnrichmentPlan(
            sections_to_enrich=[
                EnrichmentNeed(
                    section_key="intro",
                    current_words=100,
                    target_words_min=500,
                    target_words_max=1000,
                    deficit_words=400,
                    priority=8,
                    reason="Too short",
                )
            ],
            total_deficit=400,
            facts_available=10,
        )

        assert plan.needs_enrichment()

    def test_needs_enrichment_false(self):
        plan = EnrichmentPlan(
            sections_to_enrich=[],
            total_deficit=0,
            facts_available=10,
        )

        assert not plan.needs_enrichment()

    def test_total_deficit_calculation(self):
        plan = EnrichmentPlan(
            sections_to_enrich=[
                EnrichmentNeed(
                    section_key="intro",
                    current_words=100,
                    target_words_min=500,
                    target_words_max=1000,
                    deficit_words=400,
                    priority=8,
                    reason="Too short",
                ),
                EnrichmentNeed(
                    section_key="theory",
                    current_words=200,
                    target_words_min=600,
                    target_words_max=1000,
                    deficit_words=400,
                    priority=7,
                    reason="Too short",
                ),
            ],
            total_deficit=800,
            facts_available=10,
        )

        assert plan.total_deficit == 800
