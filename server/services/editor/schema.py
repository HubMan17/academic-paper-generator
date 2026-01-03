from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class EditLevel(IntEnum):
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3


@dataclass
class RepeatInfo:
    phrase: str
    count: int
    locations: list[tuple[str, int]]


@dataclass
class SectionMetrics:
    key: str
    title: str
    char_count: int
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    repeat_phrases: list[RepeatInfo] = field(default_factory=list)
    term_candidates: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    version: str
    total_chars: int
    total_words: int
    sections: list[SectionMetrics]
    global_repeats: list[RepeatInfo]
    term_candidates: list[str]
    short_sections: list[str]
    empty_sections: list[str]
    style_issues: list[str]


@dataclass
class SectionEditPlan:
    key: str
    action: str
    priority: int
    issues: list[str]
    suggestions: list[str]


@dataclass
class EditPlan:
    version: str
    level: EditLevel
    sections_to_edit: list[SectionEditPlan]
    transitions_needed: list[tuple[str, str]]
    terms_to_unify: list[str]
    global_notes: list[str]


@dataclass
class GlossaryTerm:
    canonical: str
    variants: list[str]
    context: str = ""


@dataclass
class Glossary:
    version: str
    terms: list[GlossaryTerm]


@dataclass
class TermReplacement:
    original: str
    replacement: str
    section_key: str
    position: int


@dataclass
class ConsistencyReport:
    version: str
    replacements_made: list[TermReplacement]
    issues_found: list[str]
    issues_fixed: list[str]


@dataclass
class Transition:
    from_section: str
    to_section: str
    text: str
    position: str


@dataclass
class ChapterConclusion:
    chapter_key: str
    chapter_title: str
    bullets: list[str]


@dataclass
class SectionEdited:
    key: str
    original_text: str
    edited_text: str
    changes_made: list[str]
    llm_trace_id: Optional[str] = None


@dataclass
class DocumentEdited:
    version: str
    sections: dict[str, str]
    transitions: list[Transition]
    chapter_conclusions: list[ChapterConclusion]
    quality_report_v2: Optional[QualityReport] = None


@dataclass
class EditContext:
    section_key: str
    section_text: str
    prev_section_excerpt: str
    next_section_excerpt: str
    glossary_excerpt: list[GlossaryTerm]
    style_requirements: list[str]
    level: EditLevel
