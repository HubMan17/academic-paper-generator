from dataclasses import dataclass, field
from typing import Any

from services.prompting.schema import SectionSpec as PromptingSectionSpec, OutlineMode
from services.pipeline.work_types import get_work_type_preset, WorkTypePreset


@dataclass
class SectionBudget:
    max_input_tokens: int = 4000
    max_output_tokens: int = 2000
    temperature: float = 0.7


@dataclass
class PipelineSectionSpec:
    key: str
    title: str
    order: int
    chapter_key: str = ''
    depth: int = 1
    required: bool = True
    depends_on: list[str] = field(default_factory=list)
    target_words: tuple[int, int] = (500, 1500)
    budget: SectionBudget = field(default_factory=SectionBudget)

    fact_tags: list[str] = field(default_factory=list)
    fact_keys: list[str] = field(default_factory=list)
    outline_mode: OutlineMode = OutlineMode.FULL
    needs_summaries: bool = True
    style_profile: str = "academic"
    constraints: list[str] = field(default_factory=list)

    def to_prompting_spec(self) -> PromptingSectionSpec:
        min_chars = self.target_words[0] * 5
        max_chars = self.target_words[1] * 5
        return PromptingSectionSpec(
            key=self.key,
            fact_tags=self.fact_tags,
            fact_keys=self.fact_keys,
            outline_mode=self.outline_mode,
            needs_summaries=self.needs_summaries,
            style_profile=self.style_profile,
            target_chars=(min_chars, max_chars),
            constraints=self.constraints,
            chapter_key=self.chapter_key,
        )


DEFAULT_SECTIONS: list[PipelineSectionSpec] = [
    PipelineSectionSpec(
        key="intro",
        title="Введение",
        order=1,
        chapter_key="intro",
        depth=0,
        required=True,
        depends_on=[],
        target_words=(400, 800),
        fact_tags=["project_name", "description", "tech_stack", "purpose"],
        outline_mode=OutlineMode.FULL,
        needs_summaries=False,
        constraints=["Не использовать технические детали", "Обосновать актуальность темы"],
    ),
    PipelineSectionSpec(
        key="theory",
        title="Теоретическая часть",
        order=2,
        chapter_key="theory",
        depth=0,
        required=True,
        depends_on=["intro"],
        target_words=(800, 1500),
        fact_tags=["tech_stack", "frameworks", "architecture"],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        constraints=["Описать теоретические основы используемых технологий"],
    ),
    PipelineSectionSpec(
        key="analysis",
        title="Анализ предметной области",
        order=3,
        chapter_key="practice",
        depth=1,
        required=True,
        depends_on=["theory"],
        target_words=(600, 1200),
        fact_tags=["modules", "models", "dependencies"],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        constraints=["Провести анализ требований", "Описать бизнес-логику"],
    ),
    PipelineSectionSpec(
        key="architecture",
        title="Архитектура системы",
        order=4,
        chapter_key="practice",
        depth=1,
        required=True,
        depends_on=["analysis"],
        target_words=(800, 1500),
        fact_tags=["architecture", "modules", "layers", "storage", "queue", "infra"],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        constraints=["Описать компоненты системы", "Показать связи между модулями"],
    ),
    PipelineSectionSpec(
        key="implementation",
        title="Реализация",
        order=5,
        chapter_key="practice",
        depth=1,
        required=True,
        depends_on=["architecture"],
        target_words=(1000, 2000),
        fact_tags=["api", "endpoints", "models", "modules"],
        outline_mode=OutlineMode.LOCAL,
        needs_summaries=True,
        constraints=["Описать ключевые алгоритмы", "Привести примеры кода"],
    ),
    PipelineSectionSpec(
        key="testing",
        title="Тестирование",
        order=6,
        chapter_key="practice",
        depth=1,
        required=True,
        depends_on=["implementation"],
        target_words=(400, 800),
        fact_tags=["testing", "quality"],
        outline_mode=OutlineMode.LOCAL,
        needs_summaries=True,
        constraints=["Описать стратегию тестирования", "Представить результаты"],
    ),
    PipelineSectionSpec(
        key="conclusion",
        title="Заключение",
        order=7,
        chapter_key="conclusion",
        depth=0,
        required=True,
        depends_on=["testing"],
        target_words=(300, 600),
        fact_tags=["project_name", "purpose"],
        outline_mode=OutlineMode.FULL,
        needs_summaries=False,
        constraints=["Подвести итоги работы", "Описать перспективы развития"],
    ),
]


@dataclass
class DocumentSpec:
    sections: list[PipelineSectionSpec] = field(default_factory=lambda: DEFAULT_SECTIONS.copy())
    title_template: str = "Пояснительная записка"
    language: str = "ru-RU"
    style_profile: str = "academic"
    meta: dict[str, Any] = field(default_factory=dict)

    def get_section(self, key: str) -> PipelineSectionSpec | None:
        for spec in self.sections:
            if spec.key == key:
                return spec
        return None

    def get_sections_ordered(self) -> list[PipelineSectionSpec]:
        return sorted(self.sections, key=lambda s: s.order)

    def get_required_sections(self) -> list[PipelineSectionSpec]:
        return [s for s in self.get_sections_ordered() if s.required]

    def get_dependencies(self, key: str) -> list[str]:
        spec = self.get_section(key)
        if not spec:
            return []
        return spec.depends_on


SECTION_REGISTRY: dict[str, PipelineSectionSpec] = {
    spec.key: spec for spec in DEFAULT_SECTIONS
}


def get_section_spec(key: str) -> PipelineSectionSpec | None:
    if key in SECTION_REGISTRY:
        return SECTION_REGISTRY[key]

    chapter_key = 'practice'
    depth = 1
    fact_tags = ['modules', 'models', 'tech_stack']

    if key in ('intro', 'introduction'):
        chapter_key = 'intro'
        depth = 0
        fact_tags = ["project_name", "description", "tech_stack", "purpose"]
    elif key in ('conclusion', 'conclusions', 'summary'):
        chapter_key = 'conclusion'
        depth = 0
        fact_tags = ["project_name", "purpose"]
    elif key.startswith('theory_') or key in ('concepts', 'technologies', 'comparison', 'methods', 'theory'):
        chapter_key = 'theory'
        depth = 1
        fact_tags = THEORY_SECTION_TAGS.get(key, THEORY_SECTION_TAGS.get(key.replace('theory_', ''), ['tech_stack', 'frameworks']))
    elif key.startswith('practice_') or key in PRACTICE_SECTION_TAGS:
        chapter_key = 'practice'
        depth = 1
        fact_tags = PRACTICE_SECTION_TAGS.get(key, PRACTICE_SECTION_TAGS.get(key.replace('practice_', ''), ['modules', 'models']))

    return PipelineSectionSpec(
        key=key,
        title=key.replace('_', ' ').title(),
        order=0,
        chapter_key=chapter_key,
        depth=depth,
        required=True,
        depends_on=[],
        target_words=(600, 1200),
        fact_tags=fact_tags,
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        constraints=[],
    )


def get_all_section_keys() -> list[str]:
    return [spec.key for spec in sorted(DEFAULT_SECTIONS, key=lambda s: s.order)]


THEORY_SECTION_TAGS = {
    'concepts': ['tech_stack', 'frameworks', 'description'],
    'technologies': ['tech_stack', 'frameworks', 'languages'],
    'comparison': ['tech_stack', 'frameworks', 'architecture'],
    'methods': ['architecture', 'modules', 'tech_stack'],
}

PRACTICE_SECTION_TAGS = {
    'analysis': ['modules', 'models', 'dependencies'],
    'architecture': ['architecture', 'modules', 'layers', 'storage', 'queue', 'infra'],
    'implementation': ['api', 'endpoints', 'models', 'modules'],
    'testing': ['testing', 'quality'],
}


def get_sections_for_work_type(work_type: str) -> list[PipelineSectionSpec]:
    preset = get_work_type_preset(work_type)
    sections: list[PipelineSectionSpec] = []
    order = 1

    sections.append(PipelineSectionSpec(
        key="intro",
        title="Введение",
        order=order,
        chapter_key="intro",
        depth=0,
        required=True,
        depends_on=[],
        target_words=preset.intro_words,
        fact_tags=["project_name", "description", "tech_stack", "purpose"],
        outline_mode=OutlineMode.FULL,
        needs_summaries=False,
        constraints=["Не использовать технические детали", "Обосновать актуальность темы"],
    ))
    order += 1

    prev_key = "intro"
    theory_base_order = order
    theory_tag_keys = list(THEORY_SECTION_TAGS.keys())
    for i in range(preset.theory_sections_count):
        full_key = f"theory_{i+1}"
        tag_key = theory_tag_keys[i % len(theory_tag_keys)] if theory_tag_keys else 'concepts'
        fact_tags = THEORY_SECTION_TAGS.get(tag_key, ['tech_stack', 'frameworks'])
        target_words = preset.get_section_target_words('theory', i)
        word_range = (max(400, target_words - 200), target_words + 200)
        sections.append(PipelineSectionSpec(
            key=full_key,
            title=f"1.{i+1} Раздел теории",
            order=order,
            chapter_key="theory",
            depth=1,
            required=True,
            depends_on=[prev_key],
            target_words=word_range,
            fact_tags=fact_tags,
            outline_mode=OutlineMode.STRUCTURE,
            needs_summaries=True,
            constraints=["Описать теоретические основы"],
        ))
        prev_key = full_key
        order += 1

    practice_base_order = order
    practice_tag_keys = list(PRACTICE_SECTION_TAGS.keys())
    for i in range(preset.practice_sections_count):
        full_key = f"practice_{i+1}"
        tag_key = practice_tag_keys[i % len(practice_tag_keys)] if practice_tag_keys else 'analysis'
        fact_tags = PRACTICE_SECTION_TAGS.get(tag_key, ['modules', 'models'])
        target_words = preset.get_section_target_words('practice', i)
        word_range = (max(400, target_words - 200), target_words + 200)
        is_impl_or_test = i >= (preset.practice_sections_count - 2)
        sections.append(PipelineSectionSpec(
            key=full_key,
            title=f"2.{i+1} Раздел практики",
            order=order,
            chapter_key="practice",
            depth=1,
            required=True,
            depends_on=[prev_key],
            target_words=word_range,
            fact_tags=fact_tags,
            outline_mode=OutlineMode.LOCAL if is_impl_or_test else OutlineMode.STRUCTURE,
            needs_summaries=True,
            constraints=["Описать практическую реализацию"],
        ))
        prev_key = full_key
        order += 1

    sections.append(PipelineSectionSpec(
        key="conclusion",
        title="Заключение",
        order=order,
        chapter_key="conclusion",
        depth=0,
        required=True,
        depends_on=[prev_key],
        target_words=preset.conclusion_words,
        fact_tags=["project_name", "purpose"],
        outline_mode=OutlineMode.FULL,
        needs_summaries=False,
        constraints=["Подвести итоги работы", "Описать перспективы развития"],
    ))

    return sections


def get_sections_by_chapter(sections: list[PipelineSectionSpec]) -> dict[str, list[PipelineSectionSpec]]:
    result: dict[str, list[PipelineSectionSpec]] = {}
    for spec in sections:
        chapter = spec.chapter_key or 'other'
        if chapter not in result:
            result[chapter] = []
        result[chapter].append(spec)
    return result


def get_allowed_section_keys(work_type: str) -> set[str]:
    sections = get_sections_for_work_type(work_type)
    allowed = {spec.key for spec in sections}
    allowed.add('toc')
    allowed.add('literature')
    allowed.add('appendix')
    return allowed


def get_allowed_chapter_keys() -> set[str]:
    return {'toc', 'intro', 'theory', 'practice', 'conclusion', 'literature', 'appendix'}
