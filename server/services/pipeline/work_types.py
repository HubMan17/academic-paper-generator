from dataclasses import dataclass, field


@dataclass
class ChapterSpec:
    key: str
    title: str
    order: int
    is_auto: bool = False
    has_sections: bool = True


@dataclass
class WorkTypePreset:
    key: str
    name: str
    target_pages_min: int
    target_pages_max: int
    theory_sections: list[tuple[str, str]] = field(default_factory=list)
    practice_sections: list[tuple[str, str]] = field(default_factory=list)
    style_level: int = 1
    intro_words: tuple[int, int] = (400, 800)
    conclusion_words: tuple[int, int] = (300, 600)

    @property
    def theory_depth(self) -> int:
        return len(self.theory_sections)

    @property
    def practice_depth(self) -> int:
        return len(self.practice_sections)


REFERAT_PRESET = WorkTypePreset(
    key='referat',
    name='Реферат',
    target_pages_min=20,
    target_pages_max=30,
    theory_sections=[
        ('concepts', 'Основные понятия'),
        ('technologies', 'Обзор технологий'),
    ],
    practice_sections=[
        ('analysis', 'Анализ предметной области'),
        ('implementation', 'Практическое применение'),
    ],
    style_level=1,
    intro_words=(300, 600),
    conclusion_words=(200, 400),
)


DIPLOMA_PRESET = WorkTypePreset(
    key='diploma',
    name='Диплом',
    target_pages_min=40,
    target_pages_max=60,
    theory_sections=[
        ('concepts', 'Основные понятия'),
        ('technologies', 'Обзор технологий'),
        ('comparison', 'Сравнительный анализ'),
        ('methods', 'Методы исследования'),
    ],
    practice_sections=[
        ('analysis', 'Анализ требований'),
        ('architecture', 'Архитектура системы'),
        ('implementation', 'Реализация'),
        ('testing', 'Тестирование'),
    ],
    style_level=3,
    intro_words=(500, 1000),
    conclusion_words=(400, 700),
)


COURSE_PRESET = WorkTypePreset(
    key='course',
    name='Курсовая',
    target_pages_min=25,
    target_pages_max=40,
    theory_sections=[
        ('concepts', 'Основные понятия'),
        ('technologies', 'Обзор технологий'),
        ('comparison', 'Сравнительный анализ'),
    ],
    practice_sections=[
        ('analysis', 'Анализ предметной области'),
        ('architecture', 'Архитектура системы'),
        ('implementation', 'Реализация'),
    ],
    style_level=2,
    intro_words=(400, 800),
    conclusion_words=(300, 500),
)


WORK_TYPE_REGISTRY: dict[str, WorkTypePreset] = {
    'referat': REFERAT_PRESET,
    'diploma': DIPLOMA_PRESET,
    'course': COURSE_PRESET,
}


DEFAULT_CHAPTERS: list[ChapterSpec] = [
    ChapterSpec(key='toc', title='Содержание', order=0, is_auto=True, has_sections=False),
    ChapterSpec(key='intro', title='Введение', order=1, has_sections=False),
    ChapterSpec(key='theory', title='Теоретическая часть', order=2, has_sections=True),
    ChapterSpec(key='practice', title='Практическая часть', order=3, has_sections=True),
    ChapterSpec(key='conclusion', title='Заключение', order=4, has_sections=False),
    ChapterSpec(key='literature', title='Список литературы', order=5, is_auto=True, has_sections=False),
]


def get_work_type_preset(work_type: str) -> WorkTypePreset:
    preset = WORK_TYPE_REGISTRY.get(work_type)
    if not preset:
        raise ValueError(f"Unknown work type: {work_type}. Available: {list(WORK_TYPE_REGISTRY.keys())}")
    return preset


def get_chapters() -> list[ChapterSpec]:
    return DEFAULT_CHAPTERS.copy()


def get_chapter_by_key(key: str) -> ChapterSpec | None:
    for chapter in DEFAULT_CHAPTERS:
        if chapter.key == key:
            return chapter
    return None
