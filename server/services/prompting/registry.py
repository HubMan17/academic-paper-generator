from .schema import SectionSpec, OutlineMode


_REGISTRY: dict[str, SectionSpec] = {}


def register_section_spec(spec: SectionSpec) -> None:
    _REGISTRY[spec.key] = spec


def get_section_spec(key: str) -> SectionSpec:
    """
    FALLBACK: Returns SectionSpec from registry or generates default.
    Pipeline should pass explicit spec to slice_for_section() instead of relying on this.
    """
    if key in _REGISTRY:
        return _REGISTRY[key]

    chapter_key = 'practice'
    fact_tags = ['modules', 'models', 'tech_stack']
    target_chars = (3000, 6000)
    outline_mode = OutlineMode.STRUCTURE

    if key in ('intro', 'introduction'):
        chapter_key = 'intro'
        fact_tags = ["project_name", "description", "tech_stack", "purpose"]
        target_chars = (2500, 5000)
        outline_mode = OutlineMode.FULL
    elif key in ('conclusion', 'conclusions', 'summary'):
        chapter_key = 'conclusion'
        fact_tags = ["project_name", "purpose"]
        target_chars = (1500, 3000)
        outline_mode = OutlineMode.FULL
    elif key.startswith('theory_') or key in ('concepts', 'technologies', 'comparison', 'methods'):
        chapter_key = 'theory'
        fact_tags = ['tech_stack', 'frameworks', 'architecture']
        target_chars = (3500, 7000)
    elif key.startswith('practice_') or key in ('analysis', 'architecture', 'implementation', 'testing', 'design', 'development'):
        chapter_key = 'practice'
        fact_tags = ['modules', 'models', 'api', 'endpoints']
        target_chars = (3000, 6000)

    return SectionSpec(
        key=key,
        fact_tags=fact_tags,
        fact_keys=[],
        outline_mode=outline_mode,
        needs_summaries=True,
        style_profile="academic",
        target_chars=target_chars,
        constraints=["Академический тон", "Без воды и повторов"],
    )


def list_section_keys() -> list[str]:
    return list(_REGISTRY.keys())


register_section_spec(
    SectionSpec(
        key="intro",
        fact_tags=["project_name", "description", "tech_stack", "purpose"],
        fact_keys=[],
        outline_mode=OutlineMode.FULL,
        needs_summaries=False,
        style_profile="academic",
        target_chars=(2500, 5000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Чётко описать цель, объект и предмет исследования",
            "Перечислить основной технологический стек",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="architecture",
        fact_tags=["architecture", "modules", "layers", "storage", "queue", "infra"],
        fact_keys=[],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        style_profile="academic",
        target_chars=(4000, 8000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Подробно описать модули, слои и компоненты",
            "Указать хранилища данных и очереди сообщений",
            "Описать инфраструктуру и развёртывание",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="api",
        fact_tags=["api", "endpoints", "auth", "models", "errors"],
        fact_keys=[],
        outline_mode=OutlineMode.LOCAL,
        needs_summaries=True,
        style_profile="academic",
        target_chars=(3500, 7000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Описать все основные API endpoints",
            "Указать методы аутентификации и авторизации",
            "Перечислить модели данных и форматы ошибок",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="theory",
        fact_tags=["tech_stack", "frameworks", "architecture"],
        fact_keys=[],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        style_profile="academic",
        target_chars=(4000, 7500),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Описать теоретические основы используемых технологий",
            "Привести сравнительный анализ альтернативных решений",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="analysis",
        fact_tags=["modules", "models", "dependencies"],
        fact_keys=[],
        outline_mode=OutlineMode.STRUCTURE,
        needs_summaries=True,
        style_profile="academic",
        target_chars=(3000, 6000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Провести анализ требований",
            "Описать бизнес-логику системы",
            "Определить функциональные и нефункциональные требования",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="implementation",
        fact_tags=["api", "endpoints", "models", "modules"],
        fact_keys=[],
        outline_mode=OutlineMode.LOCAL,
        needs_summaries=True,
        style_profile="academic",
        target_chars=(5000, 10000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Описать ключевые алгоритмы",
            "Привести примеры кода с пояснениями",
            "Объяснить архитектурные решения",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="testing",
        fact_tags=["testing", "quality"],
        fact_keys=[],
        outline_mode=OutlineMode.LOCAL,
        needs_summaries=True,
        style_profile="academic",
        target_chars=(2000, 4000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Описать стратегию тестирования",
            "Представить результаты тестирования",
            "Описать используемые инструменты тестирования",
        ],
    )
)

register_section_spec(
    SectionSpec(
        key="conclusion",
        fact_tags=["project_name", "purpose"],
        fact_keys=[],
        outline_mode=OutlineMode.FULL,
        needs_summaries=False,
        style_profile="academic",
        target_chars=(1500, 3000),
        constraints=[
            "Академический тон",
            "Без воды и повторов",
            "Подвести итоги работы",
            "Описать достигнутые результаты",
            "Описать перспективы развития проекта",
        ],
    )
)
