import json
import logging
from typing import Any

from services.llm import LLMClient
from services.enrichment.schema import EnrichmentResult, EnrichmentNeed
from services.enrichment.prompts import ENRICHMENT_SYSTEM, ENRICHMENT_USER_TEMPLATE
from services.enrichment.analyzer import count_words, select_relevant_facts

logger = logging.getLogger(__name__)


def enrich_section(
    llm_client: LLMClient,
    section_key: str,
    section_text: str,
    facts: dict[str, Any],
    need: EnrichmentNeed,
    fact_tags: list[str],
    max_tokens: int = 3000,
    temperature: float = 0.3,
) -> EnrichmentResult:
    relevant_facts = select_relevant_facts(facts, section_key, fact_tags)

    if not relevant_facts:
        logger.warning(f"No relevant facts found for section {section_key}")
        return EnrichmentResult(
            section_key=section_key,
            original_text=section_text,
            enriched_text=section_text,
            facts_used=[],
            words_added=0,
            success=True,
            error="No relevant facts available for enrichment",
        )

    facts_for_prompt = []
    for f in relevant_facts:
        facts_for_prompt.append({
            "fact_id": f["fact_id"],
            "data": _simplify_fact(f["data"]),
        })

    user_prompt = ENRICHMENT_USER_TEMPLATE.format(
        section_key=section_key,
        section_text=section_text,
        target_words_min=need.target_words_min,
        target_words_max=need.target_words_max,
        current_words=need.current_words,
        deficit_words=need.deficit_words,
        facts_json=json.dumps(facts_for_prompt, ensure_ascii=False, indent=2),
    )

    try:
        result = llm_client.generate_json(
            system=ENRICHMENT_SYSTEM,
            user=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        enriched_text = result.data.get("enriched_text", section_text)
        facts_used = result.data.get("facts_used", [])

        original_words = count_words(section_text)
        enriched_words = count_words(enriched_text)
        words_added = enriched_words - original_words

        return EnrichmentResult(
            section_key=section_key,
            original_text=section_text,
            enriched_text=enriched_text,
            facts_used=facts_used,
            words_added=words_added,
            success=True,
        )

    except Exception as e:
        logger.exception(f"Enrichment failed for section {section_key}: {e}")
        return EnrichmentResult(
            section_key=section_key,
            original_text=section_text,
            enriched_text=section_text,
            facts_used=[],
            words_added=0,
            success=False,
            error=str(e),
        )


def _simplify_fact(fact: Any) -> Any:
    if isinstance(fact, dict):
        simplified = {}
        for k, v in fact.items():
            if k not in ['loc', 'line_count', 'file_count']:
                simplified[k] = _simplify_fact(v)
        return simplified
    elif isinstance(fact, list):
        return [_simplify_fact(item) for item in fact[:10]]
    else:
        return fact


def enrich_sections_batch(
    llm_client: LLMClient,
    sections: list[dict[str, Any]],
    facts: dict[str, Any],
    needs: list[EnrichmentNeed],
    section_specs: dict[str, dict[str, Any]],
    max_tokens: int = 3000,
    temperature: float = 0.3,
) -> list[EnrichmentResult]:
    results = []

    needs_map = {n.section_key: n for n in needs}

    for section in sections:
        key = section.get('key', '')
        need = needs_map.get(key)

        if not need:
            continue

        text = section.get('text', '') or section.get('text_current', '')
        spec = section_specs.get(key, {})
        fact_tags = spec.get('fact_tags', [])

        result = enrich_section(
            llm_client=llm_client,
            section_key=key,
            section_text=text,
            facts=facts,
            need=need,
            fact_tags=fact_tags,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        results.append(result)

    return results
