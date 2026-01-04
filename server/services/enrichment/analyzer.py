import re
from typing import Any

from services.enrichment.schema import EnrichmentNeed, EnrichmentPlan

SKIP_ENRICHMENT_SECTIONS = {'intro', 'conclusion', 'toc', 'literature'}


def count_words(text: str) -> int:
    if not text:
        return 0
    words = re.findall(r'\b\w+\b', text)
    return len(words)


def detect_short_sections(
    sections: list[dict[str, Any]],
    section_specs: list[dict[str, Any]],
) -> EnrichmentPlan:
    needs: list[EnrichmentNeed] = []
    total_deficit = 0

    spec_map = {s['key']: s for s in section_specs}

    for section in sections:
        key = section.get('key', '')
        if key in SKIP_ENRICHMENT_SECTIONS:
            continue

        text = section.get('text', '') or section.get('text_current', '')
        current_words = count_words(text)

        spec = spec_map.get(key)
        if not spec:
            continue

        target_min = spec.get('target_words_min', spec.get('target_words', (500, 1000))[0])
        target_max = spec.get('target_words_max', spec.get('target_words', (500, 1000))[1])

        if isinstance(target_min, tuple):
            target_min, target_max = target_min

        if current_words < target_min:
            deficit = target_min - current_words
            priority = _calculate_priority(current_words, target_min, target_max)

            needs.append(EnrichmentNeed(
                section_key=key,
                current_words=current_words,
                target_words_min=target_min,
                target_words_max=target_max,
                deficit_words=deficit,
                priority=priority,
                reason=_get_reason(current_words, target_min),
            ))
            total_deficit += deficit

    needs.sort(key=lambda n: n.priority, reverse=True)

    return EnrichmentPlan(
        version="v1",
        sections_to_enrich=needs,
        total_deficit=total_deficit,
    )


def _calculate_priority(current: int, target_min: int, target_max: int) -> int:
    if current == 0:
        return 10
    ratio = current / target_min
    if ratio < 0.3:
        return 9
    elif ratio < 0.5:
        return 7
    elif ratio < 0.7:
        return 5
    else:
        return 3


def _get_reason(current: int, target_min: int) -> str:
    if current == 0:
        return "Секция пустая"
    ratio = current / target_min
    if ratio < 0.3:
        return f"Критически короткая ({int(ratio * 100)}% от минимума)"
    elif ratio < 0.5:
        return f"Существенно короткая ({int(ratio * 100)}% от минимума)"
    elif ratio < 0.7:
        return f"Недостаточный объём ({int(ratio * 100)}% от минимума)"
    else:
        return f"Немного ниже минимума ({int(ratio * 100)}% от минимума)"


def select_relevant_facts(
    facts: dict[str, Any],
    section_key: str,
    fact_tags: list[str],
    max_facts: int = 15,
) -> list[dict[str, Any]]:
    selected = []

    for fact_id, fact_data in _extract_facts(facts).items():
        score = _score_fact(fact_data, fact_tags, section_key)
        if score > 0:
            selected.append({
                "fact_id": fact_id,
                "data": fact_data,
                "score": score,
            })

    selected.sort(key=lambda f: f['score'], reverse=True)
    return selected[:max_facts]


def _extract_facts(facts: dict[str, Any]) -> dict[str, Any]:
    result = {}

    if 'languages' in facts:
        for lang in facts['languages']:
            result[f"lang:{lang.get('name', 'unknown')}"] = lang

    if 'frameworks' in facts:
        for fw in facts['frameworks']:
            result[f"framework:{fw.get('name', 'unknown')}"] = fw

    if 'architecture' in facts:
        result['architecture'] = facts['architecture']

    if 'modules' in facts:
        for module in facts['modules']:
            result[f"module:{module.get('name', 'unknown')}"] = module

    if 'endpoints' in facts:
        for ep in facts['endpoints']:
            result[f"endpoint:{ep.get('path', 'unknown')}"] = ep

    if 'models' in facts:
        for model in facts['models']:
            result[f"model:{model.get('name', 'unknown')}"] = model

    if 'dependencies' in facts:
        for dep in facts['dependencies']:
            result[f"dep:{dep.get('name', 'unknown')}"] = dep

    if 'testing' in facts:
        result['testing'] = facts['testing']

    if 'project_name' in facts:
        result['project_name'] = {'name': facts['project_name']}

    if 'description' in facts:
        result['description'] = {'text': facts['description']}

    return result


TAG_WEIGHTS = {
    'tech_stack': 2.0,
    'frameworks': 2.0,
    'architecture': 2.5,
    'modules': 2.0,
    'api': 2.5,
    'endpoints': 2.0,
    'models': 1.5,
    'testing': 2.0,
    'quality': 1.5,
    'dependencies': 1.0,
    'languages': 1.5,
    'project_name': 1.0,
    'description': 1.0,
    'purpose': 1.0,
}


def _score_fact(fact: Any, tags: list[str], section_key: str) -> float:
    score = 0.0

    fact_str = str(fact).lower() if fact else ""

    for tag in tags:
        weight = TAG_WEIGHTS.get(tag, 1.0)
        if tag.lower() in fact_str:
            score += weight

    section_keywords = {
        'intro': ['project', 'description', 'purpose', 'цель'],
        'theory': ['framework', 'technology', 'pattern', 'architecture'],
        'analysis': ['module', 'model', 'requirement', 'domain'],
        'architecture': ['layer', 'component', 'service', 'module', 'storage'],
        'implementation': ['endpoint', 'api', 'method', 'function'],
        'testing': ['test', 'coverage', 'quality', 'pytest'],
        'conclusion': ['result', 'итог', 'вывод'],
    }

    for kw in section_keywords.get(section_key, []):
        if kw.lower() in fact_str:
            score += 0.5

    return score
