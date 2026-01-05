import pytest
from services.prompting.validators import (
    validate_practice_content,
    is_practice_section,
    get_validation_summary,
    PracticeValidationResult,
)


class TestIsPracticeSection:
    def test_practice_key(self):
        assert is_practice_section("practice_1")
        assert is_practice_section("practice")

    def test_implementation_key(self):
        assert is_practice_section("implementation")
        assert is_practice_section("core_implementation")

    def test_testing_key(self):
        assert is_practice_section("testing")
        assert is_practice_section("unit_testing")

    def test_architecture_key(self):
        assert is_practice_section("architecture")
        assert is_practice_section("system_architecture")

    def test_api_key(self):
        assert is_practice_section("api")
        assert is_practice_section("rest_api")

    def test_non_practice_keys(self):
        assert not is_practice_section("intro")
        assert not is_practice_section("conclusion")
        assert not is_practice_section("theory")
        assert not is_practice_section("concepts")


class TestValidatePracticeContent:
    def test_empty_text(self):
        result = validate_practice_content("")
        assert not result.is_valid
        assert result.entities_count == 0
        assert not result.has_algorithm
        assert not result.has_table
        assert len(result.warnings) > 0

    def test_text_with_entities(self):
        text = """
        Модуль DocumentService отвечает за генерацию документов.
        LLMClient используется для работы с языковыми моделями.
        Artifact сохраняет результаты генерации.
        """
        result = validate_practice_content(text)
        assert result.entities_count >= 2
        assert "DocumentService" in result.entities_found or "LLMClient" in result.entities_found

    def test_text_with_algorithm(self):
        text = """
        **Алгоритм генерации секции:**
        1. Input: context_pack, section_key
        2. Шаг: Формирование промпта
        3. Шаг: Вызов LLM
        4. Output: generated_text
        """
        result = validate_practice_content(text)
        assert result.has_algorithm
        assert len(result.algorithm_markers) > 0

    def test_text_with_table(self):
        text = """
        | Endpoint | Method | Description |
        |----------|--------|-------------|
        | /users   | GET    | List users  |
        | /users   | POST   | Create user |
        """
        result = validate_practice_content(text)
        assert result.has_table
        assert result.table_count >= 1

    def test_fully_compliant_text(self):
        text = """
        ## Реализация DocumentService

        DocumentService является основным сервисом для генерации документов.
        LLMClient используется для взаимодействия с языковыми моделями.
        ContextPack содержит контекст для генерации.

        **Алгоритм генерации:**
        1. Input: document_id, section_key
        2. Шаг: Загрузка context_pack
        3. Шаг: Формирование промпта
        4. Output: section_text

        | Артефакт | Описание | Формат |
        |----------|----------|--------|
        | outline  | Оглавление | JSON   |
        | section  | Секция    | Markdown |
        """
        result = validate_practice_content(text)
        assert result.is_valid
        assert result.entities_count >= 2
        assert result.has_algorithm
        assert result.has_table
        assert len(result.warnings) == 0
        assert result.score >= 0.9

    def test_score_calculation(self):
        text_entities_only = "DocumentService и LLMClient используются"
        result1 = validate_practice_content(text_entities_only)
        assert result1.score > 0
        assert result1.score < 1.0

        text_algorithm_only = "**Алгоритм:**\n1. Input: x\n2. Output: y"
        result2 = validate_practice_content(text_algorithm_only)
        assert result2.score > 0

    def test_camel_case_detection(self):
        text = "Используются ContextPack, SectionSpec и RenderedPrompt"
        result = validate_practice_content(text)
        assert result.entities_count >= 3

    def test_custom_thresholds(self):
        text = "DocumentService только один"
        result_strict = validate_practice_content(text, min_entities=3)
        assert not result_strict.is_valid

        result_relaxed = validate_practice_content(text, min_entities=1)
        assert result_relaxed.entities_count >= 1


class TestPracticeValidationResult:
    def test_to_dict(self):
        result = PracticeValidationResult(
            is_valid=True,
            entities_found=["User", "Document"],
            entities_count=2,
            has_algorithm=True,
            algorithm_markers=["**Алгоритм"],
            has_table=True,
            table_count=1,
            warnings=[],
            score=1.0
        )
        d = result.to_dict()
        assert d["is_valid"] == True
        assert d["entities_count"] == 2
        assert d["has_algorithm"] == True
        assert d["has_table"] == True
        assert d["score"] == 1.0


class TestGetValidationSummary:
    def test_valid_result(self):
        result = PracticeValidationResult(
            is_valid=True,
            entities_count=3,
            has_algorithm=True,
            has_table=True,
            score=1.0
        )
        summary = get_validation_summary(result)
        assert "соответствует требованиям" in summary
        assert "Сущности: 3" in summary

    def test_invalid_result(self):
        result = PracticeValidationResult(
            is_valid=False,
            entities_count=1,
            has_algorithm=False,
            has_table=False,
            warnings=["Отсутствует таблица"],
            score=0.3
        )
        summary = get_validation_summary(result)
        assert "требует доработки" in summary
        assert "Отсутствует таблица" in summary


class TestAssemblerPracticeGuardrails:
    def test_practice_section_has_guardrails(self):
        from services.prompting.assembler import _build_system_prompt, PRACTICE_GUARDRAILS
        from services.prompting.schema import SectionSpec

        spec = SectionSpec(key="implementation")
        prompt = _build_system_prompt(spec)
        assert "ОБЯЗАТЕЛЬНЫЙ МИНИМУМ" in prompt
        assert "СУЩНОСТИ ИЗ FACTS" in prompt
        assert "АЛГОРИТМ" in prompt
        assert "ТАБЛИЦА" in prompt

    def test_theory_section_no_guardrails(self):
        from services.prompting.assembler import _build_system_prompt
        from services.prompting.schema import SectionSpec

        spec = SectionSpec(key="intro")
        prompt = _build_system_prompt(spec)
        assert "СТРОГИЕ ТРЕБОВАНИЯ ДЛЯ ПРАКТИЧЕСКОЙ ЧАСТИ" not in prompt

    def test_is_practice_section_function(self):
        from services.prompting.assembler import _is_practice_section

        assert _is_practice_section("practice_1")
        assert _is_practice_section("implementation")
        assert _is_practice_section("api_design")
        assert not _is_practice_section("intro")
        assert not _is_practice_section("conclusion")
