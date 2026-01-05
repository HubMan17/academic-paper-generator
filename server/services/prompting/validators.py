import re
from dataclasses import dataclass, field
from typing import Any


ENTITY_PATTERNS = [
    r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',
    r'\bUser\b', r'\bDocument\b', r'\bSection\b', r'\bArtifact\b',
    r'\bProject\b', r'\bAnalysis\b', r'\bContext\b', r'\bOutline\b',
    r'\bLLM\b', r'\bAPI\b', r'\bClient\b', r'\bService\b',
    r'\bModel\b', r'\bController\b', r'\bView\b', r'\bHandler\b',
]

ALGORITHM_PATTERNS = [
    r'(?i)\*\*алгоритм\b',
    r'(?i)\balgorithm\b',
    r'(?i)\bшаги?\b.*:',
    r'(?i)\bsteps?\b.*:',
    r'(?i)\binput\s*:',
    r'(?i)\boutput\s*:',
    r'^\s*\d+\.\s+\w+.*:',
]

TABLE_PATTERN = r'\|[^\n]+\|[\r\n]+\s*\|[\s\-:]+\|'


@dataclass
class PracticeValidationResult:
    is_valid: bool = True
    entities_found: list[str] = field(default_factory=list)
    entities_count: int = 0
    has_algorithm: bool = False
    algorithm_markers: list[str] = field(default_factory=list)
    has_table: bool = False
    table_count: int = 0
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "entities_found": self.entities_found,
            "entities_count": self.entities_count,
            "has_algorithm": self.has_algorithm,
            "algorithm_markers": self.algorithm_markers,
            "has_table": self.has_table,
            "table_count": self.table_count,
            "warnings": self.warnings,
            "score": self.score,
        }


def validate_practice_content(
    text: str,
    min_entities: int = 2,
    require_algorithm: bool = True,
    require_table: bool = True
) -> PracticeValidationResult:
    result = PracticeValidationResult()

    entities = set()
    for pattern in ENTITY_PATTERNS:
        matches = re.findall(pattern, text)
        entities.update(matches)

    result.entities_found = sorted(entities)[:20]
    result.entities_count = len(entities)

    if result.entities_count < min_entities:
        result.warnings.append(
            f"Недостаточно конкретных сущностей: {result.entities_count} из {min_entities} требуемых"
        )

    algorithm_markers = []
    for pattern in ALGORITHM_PATTERNS:
        if re.search(pattern, text, re.MULTILINE):
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                algorithm_markers.append(match.group(0)[:30])

    result.has_algorithm = len(algorithm_markers) > 0
    result.algorithm_markers = algorithm_markers[:5]

    if require_algorithm and not result.has_algorithm:
        result.warnings.append("Отсутствует алгоритм или псевдокод с шагами")

    tables = re.findall(TABLE_PATTERN, text, re.MULTILINE)
    result.has_table = len(tables) > 0
    result.table_count = len(tables)

    if require_table and not result.has_table:
        result.warnings.append("Отсутствует markdown-таблица")

    score = 0.0
    if result.entities_count >= min_entities:
        score += 0.4
    elif result.entities_count > 0:
        score += 0.2 * (result.entities_count / min_entities)

    if result.has_algorithm:
        score += 0.3

    if result.has_table:
        score += 0.3

    result.score = round(score, 2)
    result.is_valid = len(result.warnings) == 0

    return result


def is_practice_section(key: str) -> bool:
    practice_markers = [
        "practice", "implementation", "testing", "architecture",
        "api", "analysis", "design", "development"
    ]
    key_lower = key.lower()
    return any(marker in key_lower for marker in practice_markers)


def get_validation_summary(result: PracticeValidationResult) -> str:
    lines = []

    if result.is_valid:
        lines.append("✓ Практическая секция соответствует требованиям")
    else:
        lines.append("✗ Практическая секция требует доработки")

    lines.append(f"  Сущности: {result.entities_count} найдено")
    lines.append(f"  Алгоритм: {'есть' if result.has_algorithm else 'нет'}")
    lines.append(f"  Таблица: {'есть' if result.has_table else 'нет'}")
    lines.append(f"  Оценка: {result.score:.0%}")

    if result.warnings:
        lines.append("  Предупреждения:")
        for w in result.warnings:
            lines.append(f"    - {w}")

    return "\n".join(lines)
