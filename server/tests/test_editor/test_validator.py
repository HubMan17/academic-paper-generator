import pytest
from services.editor.validator import (
    validate_document,
    compare_quality_reports,
    check_edit_success,
    quality_report_to_dict,
)
from services.editor.schema import (
    DocumentEdited,
    QualityReport,
    SectionMetrics,
    RepeatInfo,
)


class TestValidateDocument:
    def test_validate_simple_document(self):
        document = DocumentEdited(
            version="v1",
            sections={
                "intro": "Введение к документу. " * 50,
                "theory": "Теоретическая часть. " * 50,
            },
            transitions=[],
            chapter_conclusions=[],
        )

        report = validate_document(document)

        assert report.total_chars > 0
        assert report.total_words > 0
        assert len(report.sections) == 2

    def test_validate_empty_document(self):
        document = DocumentEdited(
            version="v1",
            sections={},
            transitions=[],
            chapter_conclusions=[],
        )

        report = validate_document(document)

        assert report.total_chars == 0
        assert report.total_words == 0


class TestCompareQualityReports:
    def test_compare_improvements(self):
        before = QualityReport(
            version="v1",
            total_chars=5000,
            total_words=800,
            sections=[],
            global_repeats=[
                RepeatInfo(phrase="повтор один", count=3, locations=[]),
                RepeatInfo(phrase="повтор два", count=2, locations=[]),
            ],
            term_candidates=[],
            short_sections=["intro", "theory"],
            empty_sections=[],
            style_issues=["проблема 1", "проблема 2"],
        )

        after = QualityReport(
            version="v2",
            total_chars=5500,
            total_words=900,
            sections=[],
            global_repeats=[
                RepeatInfo(phrase="повтор один", count=2, locations=[]),
            ],
            term_candidates=[],
            short_sections=["intro"],
            empty_sections=[],
            style_issues=["проблема 1"],
        )

        comparison = compare_quality_reports(before, after)

        assert comparison["is_improved"] is True
        assert len(comparison["improvements"]) > 0
        assert "before" in comparison["summary"]
        assert "after" in comparison["summary"]

    def test_compare_regressions(self):
        before = QualityReport(
            version="v1",
            total_chars=5000,
            total_words=800,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        after = QualityReport(
            version="v2",
            total_chars=4000,
            total_words=600,
            sections=[],
            global_repeats=[
                RepeatInfo(phrase="новый повтор", count=3, locations=[]),
            ],
            term_candidates=[],
            short_sections=["intro"],
            empty_sections=["theory"],
            style_issues=["новая проблема"],
        )

        comparison = compare_quality_reports(before, after)

        assert len(comparison["regressions"]) > 0

    def test_compare_no_changes(self):
        report = QualityReport(
            version="v1",
            total_chars=5000,
            total_words=800,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        comparison = compare_quality_reports(report, report)

        assert len(comparison["regressions"]) == 0


class TestCheckEditSuccess:
    def test_success_when_improved(self):
        before = QualityReport(
            version="v1",
            total_chars=5000,
            total_words=800,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        after = QualityReport(
            version="v2",
            total_chars=5500,
            total_words=900,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        success, issues = check_edit_success(before, after)

        assert success is True
        assert len(issues) == 0

    def test_failure_when_text_shrunk_too_much(self):
        before = QualityReport(
            version="v1",
            total_chars=10000,
            total_words=1500,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        after = QualityReport(
            version="v2",
            total_chars=5000,
            total_words=800,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        success, issues = check_edit_success(before, after)

        assert success is False
        assert any("сократился" in issue.lower() for issue in issues)

    def test_failure_when_empty_sections_appeared(self):
        before = QualityReport(
            version="v1",
            total_chars=5000,
            total_words=800,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=[],
            style_issues=[],
        )

        after = QualityReport(
            version="v2",
            total_chars=4500,
            total_words=700,
            sections=[],
            global_repeats=[],
            term_candidates=[],
            short_sections=[],
            empty_sections=["theory"],
            style_issues=[],
        )

        success, issues = check_edit_success(before, after)

        assert success is False
        assert any("пустые" in issue.lower() for issue in issues)


class TestQualityReportToDict:
    def test_serialize(self):
        report = QualityReport(
            version="v1",
            total_chars=5000,
            total_words=800,
            sections=[
                SectionMetrics(
                    key="intro",
                    title="Введение",
                    char_count=2000,
                    word_count=300,
                    sentence_count=15,
                    avg_sentence_length=20.0,
                    repeat_phrases=[
                        RepeatInfo(phrase="в рамках", count=3, locations=[]),
                    ],
                    term_candidates=["API", "REST"],
                    issues=["Слишком длинные предложения"],
                ),
            ],
            global_repeats=[
                RepeatInfo(
                    phrase="использование данного",
                    count=4,
                    locations=[("intro", 100), ("theory", 200)],
                ),
            ],
            term_candidates=["API", "REST", "JSON"],
            short_sections=["conclusion"],
            empty_sections=[],
            style_issues=["Много первого лица"],
        )

        result = quality_report_to_dict(report)

        assert result["version"] == "v1"
        assert result["total_chars"] == 5000
        assert result["total_words"] == 800
        assert len(result["sections"]) == 1
        assert result["sections"][0]["key"] == "intro"
        assert len(result["global_repeats"]) == 1
        assert result["short_sections"] == ["conclusion"]
        assert len(result["style_issues"]) == 1
