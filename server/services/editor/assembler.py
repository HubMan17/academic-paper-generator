from .schema import (
    DocumentEdited,
    SectionEdited,
    Transition,
    ChapterConclusion,
    QualityReport,
)
from .analyzer import analyze_document
from services.pipeline.text_sanitizer import sanitize_section_text


def assemble_document(
    original_sections: list[dict],
    edited_sections: dict[str, SectionEdited],
    transitions: list[Transition],
    chapter_conclusions: list[ChapterConclusion],
    final_conclusion: str | None = None,
) -> DocumentEdited:
    sections_dict: dict[str, str] = {}
    transitions_by_from = {t.from_section: t for t in transitions}

    for section in original_sections:
        key = section.get("key", "")
        title = section.get("title", "")

        if key in edited_sections:
            text = edited_sections[key].edited_text
        else:
            text = section.get("text", "")

        text = sanitize_section_text(text, key)

        if key in transitions_by_from:
            transition = transitions_by_from[key]
            text = text.rstrip() + "\n\n" + transition.text

        if key == "conclusion" and final_conclusion:
            text = sanitize_section_text(final_conclusion, key)

        sections_dict[key] = text

    return DocumentEdited(
        version="v1",
        sections=sections_dict,
        transitions=transitions,
        chapter_conclusions=chapter_conclusions,
        quality_report_v2=None,
    )


def render_document_markdown(
    document: DocumentEdited,
    outline: dict,
) -> str:
    lines: list[str] = []

    document_title = outline.get("title", "Документ")
    lines.append(f"# {document_title}")
    lines.append("")

    for chapter in outline.get("chapters", []):
        chapter_title = chapter.get("title", "")
        lines.append(f"## {chapter_title}")
        lines.append("")

        for section in chapter.get("sections", []):
            section_key = section.get("key", "")
            section_title = section.get("title", "")

            if section_key in document.sections:
                lines.append(f"### {section_title}")
                lines.append("")
                lines.append(document.sections[section_key])
                lines.append("")

        chapter_key = chapter.get("key", "")
        chapter_conclusion = _find_chapter_conclusion(
            document.chapter_conclusions,
            chapter_key
        )
        if chapter_conclusion:
            lines.append("#### Выводы по главе")
            lines.append("")
            for bullet in chapter_conclusion.bullets:
                lines.append(f"- {bullet}")
            lines.append("")

    return "\n".join(lines)


def _find_chapter_conclusion(
    conclusions: list[ChapterConclusion],
    chapter_key: str
) -> ChapterConclusion | None:
    for c in conclusions:
        if c.chapter_key == chapter_key:
            return c
    return None


def validate_assembled_document(document: DocumentEdited) -> QualityReport:
    sections_list = [
        {"key": key, "title": key, "text": text}
        for key, text in document.sections.items()
    ]
    return analyze_document(sections_list)


def document_edited_to_dict(document: DocumentEdited) -> dict:
    return {
        "version": document.version,
        "sections": document.sections,
        "transitions": [
            {
                "from_section": t.from_section,
                "to_section": t.to_section,
                "text": t.text,
                "position": t.position,
            }
            for t in document.transitions
        ],
        "chapter_conclusions": [
            {
                "chapter_key": c.chapter_key,
                "chapter_title": c.chapter_title,
                "bullets": c.bullets,
            }
            for c in document.chapter_conclusions
        ],
        "stats": {
            "total_sections": len(document.sections),
            "total_chars": sum(len(t) for t in document.sections.values()),
            "transitions_count": len(document.transitions),
            "conclusions_count": len(document.chapter_conclusions),
        },
    }


def merge_sections_with_edits(
    original_sections: list[dict],
    edited_sections: dict[str, SectionEdited],
) -> list[dict]:
    merged = []

    for section in original_sections:
        key = section.get("key", "")

        if key in edited_sections:
            merged.append({
                **section,
                "text": edited_sections[key].edited_text,
                "edited": True,
            })
        else:
            merged.append({
                **section,
                "edited": False,
            })

    return merged
