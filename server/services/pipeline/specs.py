from dataclasses import dataclass, field
from typing import Any

from services.prompting.schema import SectionSpec as PromptingSectionSpec, OutlineMode


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
        )


DEFAULT_SECTIONS: list[PipelineSectionSpec] = [
    PipelineSectionSpec(
        key="intro",
        title="Введение",
        order=1,
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
    return SECTION_REGISTRY.get(key)


def get_all_section_keys() -> list[str]:
    return [spec.key for spec in sorted(DEFAULT_SECTIONS, key=lambda s: s.order)]
