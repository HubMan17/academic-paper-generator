import re
from collections import Counter
from .schema import (
    QualityReport,
    SectionMetrics,
    RepeatInfo,
)


MIN_PHRASE_LENGTH = 3
MAX_PHRASE_LENGTH = 8
MIN_REPEAT_COUNT = 2
MIN_SECTION_CHARS = 500
MIN_CONTENT_CHARS = 200
NGRAM_SIZES = [3, 4, 5]

PLACEHOLDER_MARKERS = [
    r'\[TBD\]',
    r'\[TODO\]',
    r'\[placeholder\]',
    r'\[здесь будет текст\]',
    r'\[текст секции\]',
    r'\[заполнить\]',
    r'\[добавить\]',
    r'Lorem ipsum',
    r'Текст заглушка',
    r'Заглушка',
]

GENERIC_CONTENT_PATTERNS = [
    r'^Введение\.?\s*$',
    r'^Заключение\.?\s*$',
    r'^В данной секции',
    r'^В данном разделе',
    r'^Данная секция',
    r'^Данный раздел',
    r'^Здесь будет',
    r'^Этот раздел посвящен',
    r'^Рассматриваются вопросы',
]

TEMPLATE_MARKERS = [
    "нет данных",
    "отсутствует информация",
    "данные не предоставлены",
    "информация недоступна",
    "не удалось найти",
    "данные отсутствуют",
    "важно отметить",
    "следует отметить",
    "необходимо подчеркнуть",
    "стоит отметить",
    "нельзя не отметить",
    "в современных условиях",
    "на сегодняшний день",
    "в настоящее время",
    "в наши дни",
    "таким образом",
    "итак",
    "подводя итог",
    "резюмируя вышесказанное",
    "актуальность темы обусловлена",
    "актуальность исследования",
]


def _detect_placeholder(text: str, char_count: int) -> tuple[bool, str | None]:
    if char_count < MIN_CONTENT_CHARS:
        return True, f"Секция слишком короткая ({char_count} символов, минимум {MIN_CONTENT_CHARS})"

    text_lower = text.lower().strip()

    for pattern in PLACEHOLDER_MARKERS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, f"Найден маркер-заглушка: {pattern}"

    for pattern in GENERIC_CONTENT_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE | re.MULTILINE):
            stripped = re.sub(pattern, '', text_lower, flags=re.IGNORECASE | re.MULTILINE).strip()
            if len(stripped) < MIN_CONTENT_CHARS:
                return True, "Только общие вводные фразы без конкретного содержания"

    sentences = _split_sentences(text)
    if len(sentences) <= 2 and char_count < MIN_SECTION_CHARS:
        return True, f"Только {len(sentences)} предложений, недостаточно контента"

    missing_info_count = 0
    for marker in TEMPLATE_MARKERS[:6]:
        if marker.lower() in text_lower:
            missing_info_count += 1

    if missing_info_count >= 2:
        return True, f"Найдено {missing_info_count} маркеров 'отсутствующей информации'"

    return False, None


def analyze_document(sections: list[dict]) -> QualityReport:
    section_metrics = []
    all_text_combined = ""
    global_word_counter: Counter = Counter()
    term_candidates_global: set[str] = set()
    short_sections: list[str] = []
    empty_sections: list[str] = []
    placeholder_sections: list[str] = []

    for section in sections:
        key = section.get("key", "")
        title = section.get("title", "")
        text = section.get("text", "")

        if not text.strip():
            empty_sections.append(key)
            placeholder_sections.append(key)
            section_metrics.append(SectionMetrics(
                key=key,
                title=title,
                char_count=0,
                word_count=0,
                sentence_count=0,
                avg_sentence_length=0.0,
                issues=["Секция пуста"],
                is_placeholder=True,
                placeholder_reason="Секция пуста",
            ))
            continue

        all_text_combined += " " + text
        metrics = _analyze_section(key, title, text)
        section_metrics.append(metrics)

        if metrics.is_placeholder:
            placeholder_sections.append(key)

        if metrics.char_count < MIN_SECTION_CHARS:
            short_sections.append(key)

        for term in metrics.term_candidates:
            term_candidates_global.add(term)

        words = _extract_words(text)
        global_word_counter.update(words)

    global_repeats = _find_global_repeats(all_text_combined, sections)
    style_issues = _detect_style_issues(all_text_combined)
    style_marker_counts = _count_style_markers(all_text_combined)

    total_chars = sum(m.char_count for m in section_metrics)
    total_words = sum(m.word_count for m in section_metrics)

    return QualityReport(
        version="v1",
        total_chars=total_chars,
        total_words=total_words,
        sections=section_metrics,
        global_repeats=global_repeats,
        term_candidates=sorted(term_candidates_global),
        short_sections=short_sections,
        empty_sections=empty_sections,
        style_issues=style_issues,
        style_marker_counts=style_marker_counts,
        placeholder_sections=placeholder_sections,
    )


def _analyze_section(key: str, title: str, text: str) -> SectionMetrics:
    char_count = len(text)
    words = _extract_words(text)
    word_count = len(words)
    sentences = _split_sentences(text)
    sentence_count = len(sentences)
    avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0.0

    repeat_phrases = _find_repeat_phrases(text)
    term_candidates = _extract_term_candidates(text)
    issues = _detect_section_issues(text, char_count, avg_sentence_length)

    is_placeholder, placeholder_reason = _detect_placeholder(text, char_count)

    return SectionMetrics(
        key=key,
        title=title,
        char_count=char_count,
        word_count=word_count,
        sentence_count=sentence_count,
        avg_sentence_length=round(avg_sentence_length, 1),
        repeat_phrases=repeat_phrases,
        term_candidates=term_candidates,
        issues=issues,
        is_placeholder=is_placeholder,
        placeholder_reason=placeholder_reason,
    )


def _extract_words(text: str) -> list[str]:
    return re.findall(r'\b[а-яёa-z]+\b', text.lower())


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if s.strip()]


def _find_repeat_phrases(text: str) -> list[RepeatInfo]:
    words = _extract_words(text)
    repeats: list[RepeatInfo] = []
    seen_phrases: set[str] = set()

    for n in NGRAM_SIZES:
        ngrams = _get_ngrams(words, n)
        counter = Counter(ngrams)

        for phrase_tuple, count in counter.items():
            if count >= MIN_REPEAT_COUNT:
                phrase = " ".join(phrase_tuple)
                if phrase not in seen_phrases:
                    seen_phrases.add(phrase)
                    repeats.append(RepeatInfo(
                        phrase=phrase,
                        count=count,
                        locations=[]
                    ))

    repeats.sort(key=lambda r: (-r.count, -len(r.phrase.split())))
    return repeats[:20]


def _get_ngrams(words: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def _find_global_repeats(combined_text: str, sections: list[dict]) -> list[RepeatInfo]:
    words = _extract_words(combined_text)
    repeats: list[RepeatInfo] = []

    for n in [4, 5, 6]:
        ngrams = _get_ngrams(words, n)
        counter = Counter(ngrams)

        for phrase_tuple, count in counter.items():
            if count >= 3:
                phrase = " ".join(phrase_tuple)
                locations = _find_phrase_locations(phrase, sections)
                if len(set(loc[0] for loc in locations)) > 1:
                    repeats.append(RepeatInfo(
                        phrase=phrase,
                        count=count,
                        locations=locations
                    ))

    repeats.sort(key=lambda r: -r.count)
    return repeats[:15]


def _find_phrase_locations(phrase: str, sections: list[dict]) -> list[tuple[str, int]]:
    locations: list[tuple[str, int]] = []
    pattern = re.compile(re.escape(phrase), re.IGNORECASE)

    for section in sections:
        key = section.get("key", "")
        text = section.get("text", "")
        for match in pattern.finditer(text):
            locations.append((key, match.start()))

    return locations


def _extract_term_candidates(text: str) -> list[str]:
    candidates: set[str] = set()

    camel_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text)
    candidates.update(camel_case)

    abbreviations = re.findall(r'\b[A-Z]{2,6}\b', text)
    candidates.update(abbreviations)

    quoted = re.findall(r'«([^»]+)»', text)
    candidates.update(quoted)

    code_terms = re.findall(r'`([^`]+)`', text)
    candidates.update(code_terms)

    tech_terms = re.findall(
        r'\b(?:API|REST|GraphQL|HTTP|JSON|XML|SQL|NoSQL|Redis|Celery|Docker|'
        r'Kubernetes|PostgreSQL|MongoDB|FastAPI|Django|Flask|React|Vue|Angular|'
        r'TypeScript|JavaScript|Python|Java|Golang|Rust|WebSocket|OAuth|JWT|'
        r'CRUD|ORM|MVC|MVP|MVVM|microservice|monolith)\b',
        text, re.IGNORECASE
    )
    candidates.update(t.upper() if len(t) <= 4 else t for t in tech_terms)

    return sorted(candidates)[:30]


def _detect_section_issues(text: str, char_count: int, avg_sentence_length: float) -> list[str]:
    issues: list[str] = []

    if char_count < MIN_SECTION_CHARS:
        issues.append(f"Слишком короткая секция ({char_count} символов)")

    if avg_sentence_length > 40:
        issues.append(f"Слишком длинные предложения (в среднем {avg_sentence_length:.0f} слов)")

    if avg_sentence_length < 8 and char_count > 200:
        issues.append(f"Слишком короткие предложения (в среднем {avg_sentence_length:.0f} слов)")

    passive_markers = len(re.findall(
        r'\b(?:был[аои]?\s+\w+[аоыи]н[аоы]?|'
        r'является|являются|'
        r'осуществляется|выполняется|производится|'
        r'было\s+\w+ено)\b',
        text, re.IGNORECASE
    ))
    if passive_markers > 10:
        issues.append(f"Много пассивных конструкций ({passive_markers})")

    filler_count = len(re.findall(
        r'\b(?:данный|вышеуказанный|нижеследующий|'
        r'в целом|в общем|как таковой|'
        r'в рамках|в контексте|на основе|'
        r'соответствующий|определённый)\b',
        text, re.IGNORECASE
    ))
    if filler_count > 5:
        issues.append(f"Много канцеляризмов ({filler_count})")

    return issues


def _detect_style_issues(text: str) -> list[str]:
    issues: list[str] = []
    text_lower = text.lower()

    if "отсутствует информация" in text_lower:
        issues.append("Найдено 'отсутствует информация' — заменить на нейтральную формулировку")

    if "не удалось найти" in text_lower or "не найдено" in text_lower:
        issues.append("Найдены фразы о ненайденных данных — переформулировать")

    first_person = re.findall(r'\b(?:я|мы|мной|нами|наш[аеиу]?)\b', text, re.IGNORECASE)
    if len(first_person) > 3:
        issues.append(f"Много первого лица ({len(first_person)}) — использовать безличные конструкции")

    exclamations = text.count('!')
    if exclamations > 2:
        issues.append(f"Восклицательные знаки ({exclamations}) — не характерны для академического стиля")

    return issues


def _count_style_markers(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    text_lower = text.lower()

    for marker in TEMPLATE_MARKERS:
        count = text_lower.count(marker.lower())
        if count > 0:
            counts[marker] = count

    return counts
