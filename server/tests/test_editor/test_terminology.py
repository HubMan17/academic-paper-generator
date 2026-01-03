import pytest
from services.editor.terminology import (
    apply_glossary,
    _preserve_case,
    glossary_to_dict,
    consistency_report_to_dict,
)
from services.editor.schema import Glossary, GlossaryTerm


class TestApplyGlossary:
    def test_apply_simple_replacement(self):
        glossary = Glossary(
            version="v1",
            terms=[
                GlossaryTerm(
                    canonical="REST API",
                    variants=["REST-API", "rest api", "РЕСТ АПИ"],
                    context="интерфейс",
                ),
            ],
        )

        sections = [
            {
                "key": "intro",
                "text": "Система использует REST-API для взаимодействия.",
            },
        ]

        updated, report = apply_glossary(sections, glossary)

        assert "REST API" in updated[0]["text"]
        assert "REST-API" not in updated[0]["text"]
        assert len(report.replacements_made) > 0

    def test_apply_multiple_variants(self):
        glossary = Glossary(
            version="v1",
            terms=[
                GlossaryTerm(
                    canonical="PostgreSQL",
                    variants=["Postgres", "postgres", "POSTGRES"],
                    context="база данных",
                ),
            ],
        )

        sections = [
            {
                "key": "db",
                "text": "Используется Postgres. База данных postgres надёжна.",
            },
        ]

        updated, report = apply_glossary(sections, glossary)

        assert updated[0]["text"].count("PostgreSQL") == 2
        assert "Postgres" not in updated[0]["text"]
        assert "postgres" not in updated[0]["text"]

    def test_no_replacement_for_canonical(self):
        glossary = Glossary(
            version="v1",
            terms=[
                GlossaryTerm(
                    canonical="Docker",
                    variants=["docker", "DOCKER"],
                    context="контейнеризация",
                ),
            ],
        )

        sections = [
            {
                "key": "deploy",
                "text": "Docker используется для контейнеризации.",
            },
        ]

        updated, report = apply_glossary(sections, glossary)

        assert updated[0]["text"] == sections[0]["text"]
        assert len(report.replacements_made) == 0

    def test_multiple_sections(self):
        glossary = Glossary(
            version="v1",
            terms=[
                GlossaryTerm(
                    canonical="API",
                    variants=["апи", "АПИ"],
                    context="интерфейс",
                ),
            ],
        )

        sections = [
            {"key": "intro", "text": "Используется апи для связи."},
            {"key": "arch", "text": "АПИ обеспечивает взаимодействие."},
        ]

        updated, report = apply_glossary(sections, glossary)

        assert "API" in updated[0]["text"]
        assert "API" in updated[1]["text"]
        assert len(report.issues_fixed) == 2

    def test_empty_glossary(self):
        glossary = Glossary(version="v1", terms=[])

        sections = [{"key": "test", "text": "Текст без изменений."}]

        updated, report = apply_glossary(sections, glossary)

        assert updated[0]["text"] == sections[0]["text"]
        assert len(report.replacements_made) == 0


class TestPreserveCase:
    def test_preserve_uppercase(self):
        assert _preserve_case("API", "rest api") == "REST API"

    def test_preserve_lowercase(self):
        assert _preserve_case("api", "REST API") == "rest api"

    def test_preserve_title_case(self):
        assert _preserve_case("Api", "rest api") == "Rest api"

    def test_mixed_case(self):
        result = _preserve_case("ApI", "rest api")
        assert result == "Rest api"


class TestGlossaryToDict:
    def test_serialize(self):
        glossary = Glossary(
            version="v1",
            terms=[
                GlossaryTerm(
                    canonical="Docker",
                    variants=["docker"],
                    context="контейнеры",
                ),
            ],
        )

        result = glossary_to_dict(glossary)

        assert result["version"] == "v1"
        assert len(result["terms"]) == 1
        assert result["terms"][0]["canonical"] == "Docker"


class TestConsistencyReportToDict:
    def test_serialize(self):
        _, report = apply_glossary(
            [{"key": "test", "text": "test docker here"}],
            Glossary(
                version="v1",
                terms=[
                    GlossaryTerm(
                        canonical="Docker",
                        variants=["docker"],
                        context="",
                    ),
                ],
            ),
        )

        result = consistency_report_to_dict(report)

        assert "version" in result
        assert "replacements_made" in result
        assert "total_replacements" in result
