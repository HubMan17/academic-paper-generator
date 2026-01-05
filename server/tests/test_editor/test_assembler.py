import pytest
from services.editor.assembler import (
    assemble_document,
    render_document_markdown,
    merge_sections_with_edits,
    document_edited_to_dict,
)
from services.editor.schema import (
    SectionEdited,
    Transition,
    ChapterConclusion,
)


class TestAssembleDocument:
    def test_assemble_with_edited_sections(self):
        original_sections = [
            {"key": "intro", "title": "Введение", "text": "Оригинальный текст введения."},
            {"key": "theory", "title": "Теория", "text": "Оригинальный текст теории."},
        ]

        edited_sections = {
            "intro": SectionEdited(
                key="intro",
                original_text="Оригинальный текст введения.",
                edited_text="Отредактированный текст введения.",
                changes_made=["Стилистическая правка"],
            ),
        }

        result = assemble_document(
            original_sections=original_sections,
            edited_sections=edited_sections,
            transitions=[],
            chapter_conclusions=[],
        )

        assert result.sections["intro"].rstrip('\n') == "Отредактированный текст введения."
        assert result.sections["theory"].rstrip('\n') == "Оригинальный текст теории."

    def test_assemble_with_transitions(self):
        original_sections = [
            {"key": "intro", "title": "Введение", "text": "Текст введения."},
            {"key": "theory", "title": "Теория", "text": "Текст теории."},
        ]

        transitions = [
            Transition(
                from_section="intro",
                to_section="theory",
                text="Переходя к теоретической части, рассмотрим основные концепции.",
                position="after_from",
            ),
        ]

        result = assemble_document(
            original_sections=original_sections,
            edited_sections={},
            transitions=transitions,
            chapter_conclusions=[],
        )

        assert "Переходя к теоретической части" in result.sections["intro"]

    def test_assemble_with_final_conclusion(self):
        original_sections = [
            {"key": "intro", "title": "Введение", "text": "Введение."},
            {"key": "conclusion", "title": "Заключение", "text": "Старое заключение."},
        ]

        result = assemble_document(
            original_sections=original_sections,
            edited_sections={},
            transitions=[],
            chapter_conclusions=[],
            final_conclusion="Новое улучшенное заключение.",
        )

        assert result.sections["conclusion"].rstrip('\n') == "Новое улучшенное заключение."


class TestRenderDocumentMarkdown:
    def test_render_simple_document(self):
        from services.editor.schema import DocumentEdited

        document = DocumentEdited(
            version="v1",
            sections={
                "intro": "Текст введения.",
                "theory": "Текст теории.",
            },
            transitions=[],
            chapter_conclusions=[],
        )

        outline = {
            "title": "Тестовый документ",
            "chapters": [
                {
                    "key": "ch1",
                    "title": "Глава 1",
                    "sections": [
                        {"key": "intro", "title": "Введение"},
                        {"key": "theory", "title": "Теория"},
                    ],
                },
            ],
        }

        markdown = render_document_markdown(document, outline)

        assert "# Тестовый документ" in markdown
        assert "## Глава 1" in markdown
        assert "### Введение" in markdown
        assert "### Теория" in markdown
        assert "Текст введения." in markdown
        assert "Текст теории." in markdown

    def test_render_with_chapter_conclusions(self):
        from services.editor.schema import DocumentEdited

        document = DocumentEdited(
            version="v1",
            sections={"intro": "Введение."},
            transitions=[],
            chapter_conclusions=[
                ChapterConclusion(
                    chapter_key="ch1",
                    chapter_title="Глава 1",
                    bullets=["Вывод 1", "Вывод 2"],
                ),
            ],
        )

        outline = {
            "title": "Документ",
            "chapters": [
                {
                    "key": "ch1",
                    "title": "Глава 1",
                    "sections": [{"key": "intro", "title": "Введение"}],
                },
            ],
        }

        markdown = render_document_markdown(document, outline)

        assert "#### Выводы по главе" in markdown
        assert "- Вывод 1" in markdown
        assert "- Вывод 2" in markdown


class TestMergeSectionsWithEdits:
    def test_merge_partial_edits(self):
        original = [
            {"key": "intro", "title": "Введение", "text": "Оригинал 1"},
            {"key": "theory", "title": "Теория", "text": "Оригинал 2"},
            {"key": "practice", "title": "Практика", "text": "Оригинал 3"},
        ]

        edited = {
            "theory": SectionEdited(
                key="theory",
                original_text="Оригинал 2",
                edited_text="Отредактировано 2",
                changes_made=[],
            ),
        }

        merged = merge_sections_with_edits(original, edited)

        assert merged[0]["text"] == "Оригинал 1"
        assert merged[0]["edited"] is False

        assert merged[1]["text"] == "Отредактировано 2"
        assert merged[1]["edited"] is True

        assert merged[2]["text"] == "Оригинал 3"
        assert merged[2]["edited"] is False


class TestDocumentEditedToDict:
    def test_serialize(self):
        from services.editor.schema import DocumentEdited

        document = DocumentEdited(
            version="v1",
            sections={"intro": "Текст", "theory": "Ещё текст"},
            transitions=[
                Transition(
                    from_section="intro",
                    to_section="theory",
                    text="Переход",
                    position="after_from",
                ),
            ],
            chapter_conclusions=[
                ChapterConclusion(
                    chapter_key="ch1",
                    chapter_title="Глава",
                    bullets=["Вывод"],
                ),
            ],
        )

        result = document_edited_to_dict(document)

        assert result["version"] == "v1"
        assert len(result["sections"]) == 2
        assert len(result["transitions"]) == 1
        assert len(result["chapter_conclusions"]) == 1
        assert "stats" in result
        assert result["stats"]["total_sections"] == 2
