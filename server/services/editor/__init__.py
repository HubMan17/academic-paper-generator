from .schema import (
    EditLevel,
    QualityReport,
    SectionMetrics,
    RepeatInfo,
    EditPlan,
    SectionEditPlan,
    Glossary,
    GlossaryTerm,
    ConsistencyReport,
    TermReplacement,
    Transition,
    ChapterConclusion,
    SectionEdited,
    DocumentEdited,
    EditContext,
)

from .analyzer import analyze_document

from .planner import create_edit_plan, edit_plan_to_dict

from .terminology import (
    build_glossary,
    apply_glossary,
    glossary_to_dict,
    consistency_report_to_dict,
)

from .section_editor import (
    edit_section,
    edit_sections_batch,
    section_edited_to_dict,
)

from .transitions import (
    generate_transitions,
    apply_transitions,
    transitions_to_dict,
)

from .conclusions import (
    generate_chapter_conclusions,
    generate_final_conclusion,
    chapter_conclusions_to_dict,
)

from .assembler import (
    assemble_document,
    render_document_markdown,
    document_edited_to_dict,
    merge_sections_with_edits,
)

from .validator import (
    validate_document,
    compare_quality_reports,
    check_edit_success,
    quality_report_to_dict,
)

from .service import EditorService, edit_single_section


__all__ = [
    "EditLevel",
    "QualityReport",
    "SectionMetrics",
    "RepeatInfo",
    "EditPlan",
    "SectionEditPlan",
    "Glossary",
    "GlossaryTerm",
    "ConsistencyReport",
    "TermReplacement",
    "Transition",
    "ChapterConclusion",
    "SectionEdited",
    "DocumentEdited",
    "EditContext",
    "analyze_document",
    "create_edit_plan",
    "edit_plan_to_dict",
    "build_glossary",
    "apply_glossary",
    "glossary_to_dict",
    "consistency_report_to_dict",
    "edit_section",
    "edit_sections_batch",
    "section_edited_to_dict",
    "generate_transitions",
    "apply_transitions",
    "transitions_to_dict",
    "generate_chapter_conclusions",
    "generate_final_conclusion",
    "chapter_conclusions_to_dict",
    "assemble_document",
    "render_document_markdown",
    "document_edited_to_dict",
    "merge_sections_with_edits",
    "validate_document",
    "compare_quality_reports",
    "check_edit_success",
    "quality_report_to_dict",
    "EditorService",
    "edit_single_section",
]
