import re
from typing import Optional

from services.llm import LLMClient
from .schema import (
    Glossary,
    GlossaryTerm,
    ConsistencyReport,
    TermReplacement,
)
from . import prompts


def build_glossary(
    llm_client: LLMClient,
    term_candidates: list[str],
    sections: list[dict],
    idempotency_key: Optional[str] = None,
) -> Glossary:
    text_excerpts = _extract_term_excerpts(term_candidates, sections)

    user_prompt = prompts.get_glossary_user(
        term_candidates=term_candidates[:50],
        text_excerpts=text_excerpts,
    )

    result = llm_client.generate_json(
        system=prompts.GLOSSARY_SYSTEM,
        user=user_prompt,
        schema=_GLOSSARY_SCHEMA,
    )

    return _parse_glossary(result.data)


def _extract_term_excerpts(candidates: list[str], sections: list[dict]) -> str:
    excerpts = []
    seen_terms = set()

    for term in candidates[:30]:
        if term.lower() in seen_terms:
            continue

        for section in sections:
            text = section.get("text", "")
            pattern = re.compile(
                rf'.{{0,50}}\b{re.escape(term)}\b.{{0,50}}',
                re.IGNORECASE
            )
            matches = pattern.findall(text)
            if matches:
                excerpt = matches[0].strip()
                excerpts.append(f"[{term}]: ...{excerpt}...")
                seen_terms.add(term.lower())
                break

        if len(excerpts) >= 20:
            break

    return "\n".join(excerpts)


def _parse_glossary(data: dict) -> Glossary:
    terms = []
    for t in data.get("terms", []):
        terms.append(GlossaryTerm(
            canonical=t.get("canonical", ""),
            variants=t.get("variants", []),
            context=t.get("context", ""),
        ))
    return Glossary(version="v1", terms=terms)


def apply_glossary(
    sections: list[dict],
    glossary: Glossary,
) -> tuple[list[dict], ConsistencyReport]:
    replacements: list[TermReplacement] = []
    issues_found: list[str] = []
    issues_fixed: list[str] = []
    updated_sections = []

    for section in sections:
        key = section.get("key", "")
        text = section.get("text", "")
        original_text = text

        for term in glossary.terms:
            if not term.variants:
                continue

            for variant in term.variants:
                if variant.lower() == term.canonical.lower():
                    continue

                pattern = re.compile(
                    rf'\b{re.escape(variant)}\b',
                    re.IGNORECASE
                )

                matches = list(pattern.finditer(text))
                actual_matches = [
                    m for m in matches
                    if m.group() != term.canonical
                ]

                if actual_matches:
                    issues_found.append(
                        f"Секция '{key}': найдено '{variant}' ({len(actual_matches)} раз)"
                    )

                    for match in actual_matches:
                        replacements.append(TermReplacement(
                            original=match.group(),
                            replacement=term.canonical,
                            section_key=key,
                            position=match.start(),
                        ))

                    text = pattern.sub(
                        lambda m: term.canonical if m.group() != term.canonical else m.group(),
                        text
                    )
                    issues_fixed.append(
                        f"Секция '{key}': заменено '{variant}' → '{term.canonical}'"
                    )

        updated_sections.append({
            **section,
            "text": text,
        })

    report = ConsistencyReport(
        version="v1",
        replacements_made=replacements,
        issues_found=issues_found,
        issues_fixed=issues_fixed,
    )

    return updated_sections, report


def _preserve_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original.islower():
        return replacement.lower()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def glossary_to_dict(glossary: Glossary) -> dict:
    return {
        "version": glossary.version,
        "terms": [
            {
                "canonical": t.canonical,
                "variants": t.variants,
                "context": t.context,
            }
            for t in glossary.terms
        ],
    }


def consistency_report_to_dict(report: ConsistencyReport) -> dict:
    return {
        "version": report.version,
        "replacements_made": [
            {
                "original": r.original,
                "replacement": r.replacement,
                "section_key": r.section_key,
                "position": r.position,
            }
            for r in report.replacements_made
        ],
        "issues_found": report.issues_found,
        "issues_fixed": report.issues_fixed,
        "total_replacements": len(report.replacements_made),
    }


_GLOSSARY_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical": {"type": "string"},
                    "variants": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "context": {"type": "string"},
                },
                "required": ["canonical", "variants"],
            },
        },
    },
    "required": ["terms"],
}
