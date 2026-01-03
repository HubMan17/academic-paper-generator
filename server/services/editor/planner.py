from dataclasses import asdict
from typing import Optional

from services.llm import LLMClient
from .schema import (
    EditLevel,
    EditPlan,
    SectionEditPlan,
    QualityReport,
)
from . import prompts


def create_edit_plan(
    llm_client: LLMClient,
    outline: dict,
    section_summaries: list[dict],
    quality_report: QualityReport,
    level: EditLevel = EditLevel.LEVEL_1,
    idempotency_key: Optional[str] = None,
) -> EditPlan:
    metrics = _quality_report_to_metrics(quality_report)

    user_prompt = prompts.get_edit_plan_user(
        outline=outline,
        section_summaries=section_summaries,
        metrics=metrics,
        level=level,
    )

    result = llm_client.generate_json(
        system=prompts.EDIT_PLAN_SYSTEM,
        user=user_prompt,
        schema=_EDIT_PLAN_SCHEMA,
    )

    return _parse_edit_plan(result.data, level)


def _quality_report_to_metrics(report: QualityReport) -> dict:
    return {
        "total_chars": report.total_chars,
        "total_words": report.total_words,
        "short_sections": report.short_sections,
        "empty_sections": report.empty_sections,
        "global_repeats": [
            {"phrase": r.phrase, "count": r.count}
            for r in report.global_repeats[:10]
        ],
        "style_issues": report.style_issues,
        "sections": [
            {
                "key": s.key,
                "chars": s.char_count,
                "issues": s.issues,
            }
            for s in report.sections
        ],
    }


def _parse_edit_plan(data: dict, level: EditLevel) -> EditPlan:
    sections = []
    for s in data.get("sections_to_edit", []):
        sections.append(SectionEditPlan(
            key=s.get("key", ""),
            action=s.get("action", "edit"),
            priority=s.get("priority", 5),
            issues=s.get("issues", []),
            suggestions=s.get("suggestions", []),
        ))

    sections.sort(key=lambda x: x.priority)

    transitions = []
    for t in data.get("transitions_needed", []):
        if isinstance(t, list) and len(t) == 2:
            transitions.append((t[0], t[1]))

    return EditPlan(
        version="v1",
        level=level,
        sections_to_edit=sections,
        transitions_needed=transitions,
        terms_to_unify=data.get("terms_to_unify", []),
        global_notes=data.get("global_notes", []),
    )


def edit_plan_to_dict(plan: EditPlan) -> dict:
    return {
        "version": plan.version,
        "level": int(plan.level),
        "sections_to_edit": [
            {
                "key": s.key,
                "action": s.action,
                "priority": s.priority,
                "issues": s.issues,
                "suggestions": s.suggestions,
            }
            for s in plan.sections_to_edit
        ],
        "transitions_needed": list(plan.transitions_needed),
        "terms_to_unify": plan.terms_to_unify,
        "global_notes": plan.global_notes,
    }


_EDIT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "sections_to_edit": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "action": {"type": "string", "enum": ["edit", "rewrite", "expand"]},
                    "priority": {"type": "integer", "minimum": 1, "maximum": 10},
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "suggestions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "action", "priority"],
            },
        },
        "transitions_needed": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "terms_to_unify": {
            "type": "array",
            "items": {"type": "string"},
        },
        "global_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["sections_to_edit"],
}
