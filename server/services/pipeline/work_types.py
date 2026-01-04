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
    theory_sections: list[tuple[str, str, int]] = field(default_factory=list)
    practice_sections: list[tuple[str, str, int]] = field(default_factory=list)
    style_level: int = 1
    intro_words: tuple[int, int] = (400, 800)
    conclusion_words: tuple[int, int] = (300, 600)
    theory_ratio: int = 45
    practice_ratio: int = 55
    use_subsections: bool = True

    @property
    def theory_depth(self) -> int:
        return len(self.theory_sections)

    @property
    def practice_depth(self) -> int:
        return len(self.practice_sections)

    @property
    def total_words_avg(self) -> int:
        pages_avg = (self.target_pages_min + self.target_pages_max) // 2
        return pages_avg * 280

    @property
    def theory_words_budget(self) -> int:
        return int(self.total_words_avg * self.theory_ratio / 100)

    @property
    def practice_words_budget(self) -> int:
        return int(self.total_words_avg * self.practice_ratio / 100)

    def get_section_target_words(self, section_key: str) -> int:
        for key, title, words in self.theory_sections:
            if key == section_key:
                return words
        for key, title, words in self.practice_sections:
            if key == section_key:
                return words
        return 800


REFERAT_PRESET = WorkTypePreset(
    key='referat',
    name='Реферат',
    target_pages_min=10,
    target_pages_max=15,
    theory_sections=[
        ('concepts', 'Основные понятия и принципы', 600),
        ('approaches', 'Подходы к решению задачи', 500),
    ],
    practice_sections=[
        ('analysis', 'Анализ предметной области', 500),
        ('implementation', 'Практическое применение', 600),
    ],
    style_level=1,
    intro_words=(300, 450),
    conclusion_words=(200, 350),
    theory_ratio=50,
    practice_ratio=50,
    use_subsections=True,
)


DIPLOMA_PRESET = WorkTypePreset(
    key='diploma',
    name='Диплом',
    target_pages_min=40,
    target_pages_max=60,
    theory_sections=[
        ('concepts', 'Теоретические основы и понятийный аппарат', 1800),
        ('technologies', 'Анализ существующих решений и технологий', 1600),
        ('methods', 'Методологические подходы к разработке', 1400),
    ],
    practice_sections=[
        ('analysis', 'Анализ требований и постановка задачи', 1200),
        ('architecture', 'Проектирование архитектуры системы', 1800),
        ('implementation', 'Реализация основного функционала', 2400),
        ('testing', 'Тестирование и оценка результатов', 1200),
    ],
    style_level=3,
    intro_words=(700, 1000),
    conclusion_words=(500, 700),
    theory_ratio=40,
    practice_ratio=60,
)


COURSE_PRESET = WorkTypePreset(
    key='course',
    name='Курсовая',
    target_pages_min=20,
    target_pages_max=30,
    theory_sections=[
        ('concepts', 'Основные принципы и понятия предметной области', 1500),
        ('approaches', 'Подходы к разработке и выбор решений', 1400),
    ],
    practice_sections=[
        ('analysis', 'Анализ задачи и требований', 900),
        ('architecture', 'Архитектурные решения', 1100),
        ('implementation', 'Реализация ключевого функционала', 1500),
        ('testing', 'Тестирование и результаты', 700),
    ],
    style_level=2,
    intro_words=(400, 550),
    conclusion_words=(300, 400),
    theory_ratio=45,
    practice_ratio=55,
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
