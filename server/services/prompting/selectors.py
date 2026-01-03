from typing import Any
from .schema import SectionSpec, FactRef


def select_facts(
    spec: SectionSpec,
    facts: dict[str, Any],
    max_facts: int = 30
) -> tuple[list[dict[str, Any]], list[FactRef]]:
    selected_facts = []
    fact_refs = []

    if not isinstance(facts, dict):
        return selected_facts, fact_refs

    facts_list = facts.get("facts", [])
    if not isinstance(facts_list, list):
        return selected_facts, fact_refs

    for fact in facts_list:
        if not isinstance(fact, dict):
            continue

        fact_id = fact.get("id", "")
        fact_tags = fact.get("tags", [])
        fact_key = fact.get("key_path", "")

        if not fact_id:
            continue

        selected = False
        reason = ""

        if fact_key in spec.fact_keys:
            selected = True
            reason = f"key:{fact_key}"

        if not selected:
            for tag in spec.fact_tags:
                if tag in fact_tags:
                    selected = True
                    reason = f"tag:{tag}"
                    break

        if selected:
            selected_facts.append(fact)
            fact_refs.append(FactRef(fact_id=fact_id, reason=reason))

            if len(selected_facts) >= max_facts:
                break

    return selected_facts, fact_refs
