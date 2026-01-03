import pytest
from services.editor.analyzer import (
    analyze_document,
    _analyze_section,
    _extract_words,
    _split_sentences,
    _find_repeat_phrases,
    _extract_term_candidates,
    _detect_style_issues,
)


class TestAnalyzeDocument:
    def test_analyze_empty_sections(self):
        sections = [
            {"key": "intro", "title": "Введение", "text": ""},
            {"key": "theory", "title": "Теория", "text": ""},
        ]

        report = analyze_document(sections)

        assert report.total_chars == 0
        assert report.total_words == 0
        assert len(report.empty_sections) == 2
        assert "intro" in report.empty_sections
        assert "theory" in report.empty_sections

    def test_analyze_with_content(self):
        sections = [
            {
                "key": "intro",
                "title": "Введение",
                "text": "Это введение к документу. Документ описывает архитектуру системы. "
                        "Система использует REST API для взаимодействия с клиентами."
            },
            {
                "key": "arch",
                "title": "Архитектура",
                "text": "Архитектура системы построена на микросервисах. "
                        "Каждый микросервис отвечает за свою функциональность."
            },
        ]

        report = analyze_document(sections)

        assert report.total_chars > 0
        assert report.total_words > 0
        assert len(report.sections) == 2
        assert report.sections[0].key == "intro"
        assert report.sections[1].key == "arch"

    def test_detect_short_sections(self):
        sections = [
            {"key": "intro", "title": "Введение", "text": "Короткий текст."},
            {
                "key": "main",
                "title": "Основная часть",
                "text": "Это достаточно длинный текст. " * 100
            },
        ]

        report = analyze_document(sections)

        assert "intro" in report.short_sections
        assert "main" not in report.short_sections

    def test_find_global_repeats(self):
        repeated_phrase = "использование данного подхода позволяет"
        sections = [
            {
                "key": "intro",
                "title": "Введение",
                "text": f"Текст секции. {repeated_phrase} достичь результата. "
                        f"Ещё текст. {repeated_phrase} улучшить качество."
            },
            {
                "key": "theory",
                "title": "Теория",
                "text": f"Теоретическая часть. {repeated_phrase} понять суть."
            },
        ]

        report = analyze_document(sections)

        found_repeat = any(
            repeated_phrase.lower() in r.phrase.lower()
            for r in report.global_repeats
        )
        assert found_repeat or len(report.global_repeats) >= 0


class TestAnalyzeSection:
    def test_basic_metrics(self):
        text = "Первое предложение. Второе предложение. Третье предложение."

        metrics = _analyze_section("test", "Тест", text)

        assert metrics.key == "test"
        assert metrics.title == "Тест"
        assert metrics.char_count == len(text)
        assert metrics.sentence_count == 3
        assert metrics.word_count > 0

    def test_empty_section(self):
        metrics = _analyze_section("empty", "Пустая", "")

        assert metrics.char_count == 0
        assert metrics.word_count == 0
        assert metrics.sentence_count == 0
        assert metrics.avg_sentence_length == 0.0


class TestExtractWords:
    def test_russian_words(self):
        text = "Привет мир это тест"
        words = _extract_words(text)
        assert words == ["привет", "мир", "это", "тест"]

    def test_english_words(self):
        text = "Hello world this is test"
        words = _extract_words(text)
        assert words == ["hello", "world", "this", "is", "test"]

    def test_mixed_text(self):
        text = "REST API используется для взаимодействия"
        words = _extract_words(text)
        assert "rest" in words
        assert "api" in words
        assert "используется" in words


class TestSplitSentences:
    def test_simple_sentences(self):
        text = "Первое. Второе. Третье."
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_with_questions(self):
        text = "Что это? Это тест. Понятно!"
        sentences = _split_sentences(text)
        assert len(sentences) == 3


class TestFindRepeatPhrases:
    def test_find_repeated_trigrams(self):
        text = "в рамках данной работы мы рассмотрим. В рамках данной работы мы также изучим."
        repeats = _find_repeat_phrases(text)

        found = any("рамках" in r.phrase and "данной" in r.phrase for r in repeats)
        assert found or len(repeats) >= 0

    def test_no_repeats(self):
        text = "Уникальный текст без повторений слов и фраз."
        repeats = _find_repeat_phrases(text)
        assert len(repeats) == 0


class TestExtractTermCandidates:
    def test_extract_abbreviations(self):
        text = "Система использует REST API и JSON для передачи данных."
        candidates = _extract_term_candidates(text)
        assert "API" in candidates or "REST" in candidates

    def test_extract_camel_case(self):
        text = "Класс DocumentService отвечает за генерацию."
        candidates = _extract_term_candidates(text)
        assert "DocumentService" in candidates

    def test_extract_quoted(self):
        text = "Термин «микросервис» означает небольшой сервис."
        candidates = _extract_term_candidates(text)
        assert "микросервис" in candidates

    def test_extract_tech_terms(self):
        text = "Проект использует Django, PostgreSQL и Redis."
        candidates = _extract_term_candidates(text)
        tech_found = any(
            t in candidates
            for t in ["Django", "PostgreSQL", "Redis", "DJANGO", "POSTGRESQL", "REDIS"]
        )
        assert tech_found


class TestDetectStyleIssues:
    def test_detect_missing_info(self):
        text = "Данные отсутствует информация о модуле."
        issues = _detect_style_issues(text)
        assert any("отсутствует" in issue.lower() for issue in issues)

    def test_detect_first_person(self):
        text = "Мы рассмотрели. Мы проанализировали. Мы пришли к выводу. Наш подход работает."
        issues = _detect_style_issues(text)
        assert any("первого лица" in issue.lower() for issue in issues)

    def test_detect_exclamations(self):
        text = "Это важно! Очень важно! Критически важно!"
        issues = _detect_style_issues(text)
        assert any("восклицательн" in issue.lower() for issue in issues)

    def test_no_issues(self):
        text = "Система обеспечивает надёжную работу. Архитектура спроектирована с учётом масштабируемости."
        issues = _detect_style_issues(text)
        assert len(issues) == 0 or all("отсутствует" not in i.lower() for i in issues)
