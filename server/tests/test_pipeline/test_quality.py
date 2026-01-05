import pytest
from services.pipeline.steps.quality import (
    check_ngram_repetition,
    check_practice_blocks,
    check_terminology_consistency,
    generate_suggested_fixes,
    count_words,
    extract_ngrams,
)
from services.pipeline.schemas import (
    QualityReport, QualityStats, QualityIssue,
    PracticeBlockCheck, TerminologyIssue, SuggestedFix,
)


class TestCountWords:
    def test_empty_string(self):
        assert count_words("") == 0

    def test_simple_sentence(self):
        assert count_words("Hello world") == 2

    def test_with_punctuation(self):
        assert count_words("Hello, world! How are you?") == 5

    def test_russian_text(self):
        assert count_words("Привет мир") == 2


class TestExtractNgrams:
    def test_empty_text(self):
        assert extract_ngrams("") == []

    def test_short_text(self):
        assert extract_ngrams("one two") == []

    def test_three_words(self):
        ngrams = extract_ngrams("one two three")
        assert len(ngrams) == 1
        assert ngrams[0] == ("one", "two", "three")

    def test_four_words(self):
        ngrams = extract_ngrams("one two three four")
        assert len(ngrams) == 2


class TestCheckNgramRepetition:
    def test_no_repetition(self):
        text = " ".join([f"word{i}" for i in range(20)])
        is_rep, ratio = check_ngram_repetition(text)
        assert not is_rep
        assert ratio == 0.0

    def test_high_repetition(self):
        text = "repeat this phrase " * 20
        is_rep, ratio = check_ngram_repetition(text)
        assert is_rep
        assert ratio > 0.1

    def test_short_text_no_check(self):
        text = "short text"
        is_rep, ratio = check_ngram_repetition(text)
        assert not is_rep
        assert ratio == 0.0


class TestCheckPracticeBlocks:
    def test_empty_text(self):
        blocks = check_practice_blocks("")
        assert len(blocks) == 5
        assert all(not b.present for b in blocks)

    def test_requirements_present(self):
        text = "Требования к системе включают..."
        blocks = check_practice_blocks(text)
        req_block = next(b for b in blocks if b.block_name == "requirements")
        assert req_block.present
        assert "требовани" in req_block.markers_found

    def test_architecture_present(self):
        text = "Архитектура системы состоит из нескольких компонентов"
        blocks = check_practice_blocks(text)
        arch_block = next(b for b in blocks if b.block_name == "architecture")
        assert arch_block.present

    def test_api_present(self):
        text = "API endpoints: GET /users, POST /users"
        blocks = check_practice_blocks(text)
        api_block = next(b for b in blocks if b.block_name == "api")
        assert api_block.present

    def test_testing_present(self):
        text = "Тестирование проводилось с использованием pytest"
        blocks = check_practice_blocks(text)
        test_block = next(b for b in blocks if b.block_name == "testing")
        assert test_block.present

    def test_data_present(self):
        text = "Модель данных включает сущности User и Project"
        blocks = check_practice_blocks(text)
        data_block = next(b for b in blocks if b.block_name == "data")
        assert data_block.present

    def test_all_blocks_missing(self):
        text = "Простой текст без технических деталей"
        blocks = check_practice_blocks(text)
        missing = [b for b in blocks if not b.present]
        assert len(missing) == 5


class TestCheckTerminologyConsistency:
    def test_no_issues_single_variant(self):
        text = "API используется для связи. API обеспечивает доступ."
        issues = check_terminology_consistency(text)
        api_issues = [i for i in issues if i.term == "api"]
        assert len(api_issues) == 0

    def test_issue_with_multiple_variants(self):
        text = "API обеспечивает доступ. Также АПИ используется для..."
        issues = check_terminology_consistency(text)
        api_issues = [i for i in issues if i.term == "api"]
        assert len(api_issues) == 1
        assert len(api_issues[0].variants) == 2

    def test_frontend_variants(self):
        text = "Frontend разработан на React. Фронтенд включает компоненты."
        issues = check_terminology_consistency(text)
        fe_issues = [i for i in issues if i.term == "frontend"]
        assert len(fe_issues) == 1

    def test_no_issues_clean_text(self):
        text = "Текст без терминологии"
        issues = check_terminology_consistency(text)
        assert len(issues) == 0


class TestGenerateSuggestedFixes:
    def test_fix_for_missing_section(self):
        report = QualityReport()
        report.add_error("MISSING_SECTION", "Section missing", section_key="intro")
        report.stats = QualityStats()

        fixes = generate_suggested_fixes(report)
        add_fixes = [f for f in fixes if f.code == "ADD_SECTION"]
        assert len(add_fixes) == 1
        assert add_fixes[0].priority == "high"

    def test_fix_for_short_section(self):
        report = QualityReport()
        report.add_warning("SECTION_TOO_SHORT", "Too short", section_key="api")
        report.stats = QualityStats()

        fixes = generate_suggested_fixes(report)
        expand_fixes = [f for f in fixes if f.code == "EXPAND_SECTION"]
        assert len(expand_fixes) == 1
        assert expand_fixes[0].priority == "medium"

    def test_fix_for_missing_practice_block(self):
        report = QualityReport()
        report.stats = QualityStats(
            missing_required_blocks=[
                PracticeBlockCheck(block_name="api", present=False),
                PracticeBlockCheck(block_name="testing", present=True),
            ]
        )

        fixes = generate_suggested_fixes(report)
        block_fixes = [f for f in fixes if f.code == "ADD_PRACTICE_BLOCK"]
        assert len(block_fixes) == 1
        assert "api" in block_fixes[0].message

    def test_fix_for_terminology(self):
        report = QualityReport()
        report.stats = QualityStats(
            terminology_inconsistencies=[
                TerminologyIssue(term="api", variants=["API", "АПИ"])
            ]
        )

        fixes = generate_suggested_fixes(report)
        term_fixes = [f for f in fixes if f.code == "UNIFY_TERMINOLOGY"]
        assert len(term_fixes) == 1
        assert term_fixes[0].priority == "low"


class TestQualitySchemas:
    def test_practice_block_check(self):
        block = PracticeBlockCheck(
            block_name="api",
            present=True,
            markers_found=["api", "endpoint"]
        )
        assert block.block_name == "api"
        assert block.present
        assert len(block.markers_found) == 2

    def test_terminology_issue(self):
        issue = TerminologyIssue(
            term="api",
            variants=["API", "АПИ"],
            occurrences={"API": 5, "АПИ": 2}
        )
        assert issue.term == "api"
        assert len(issue.variants) == 2
        assert issue.occurrences["API"] == 5

    def test_suggested_fix(self):
        fix = SuggestedFix(
            priority="high",
            code="ADD_SECTION",
            message="Add intro section",
            section_key="intro"
        )
        assert fix.priority == "high"
        assert fix.section_key == "intro"

    def test_quality_stats_defaults(self):
        stats = QualityStats()
        assert stats.repetition_score == 0.0
        assert stats.section_repetition_scores == {}
        assert stats.section_length_warnings == []
        assert stats.missing_required_blocks == []
        assert stats.terminology_inconsistencies == []
        assert stats.suggested_fixes == []
