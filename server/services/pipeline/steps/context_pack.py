import logging
from typing import Any
from uuid import UUID

from apps.projects.models import Document, DocumentArtifact, Section
from services.pipeline.ensure import ensure_artifact, get_success_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import get_profile
from services.pipeline.specs import get_section_spec
from services.prompting import slice_for_section

logger = logging.getLogger(__name__)


def get_previous_summaries(document: Document, current_section_key: str, limit: int = 3) -> list[dict]:
    summaries = []

    sections = document.sections.filter(
        status=Section.Status.SUCCESS
    ).order_by('order')

    for section in sections:
        if section.key == current_section_key:
            break

        if section.summary_current:
            summary_lines = section.summary_current.strip().split('\n')
            points = [line.lstrip('-•').strip() for line in summary_lines if line.strip()]
            summaries.append({
                "section_key": section.key,
                "points": points
            })

    return summaries[-limit:] if len(summaries) > limit else summaries


def ensure_context_pack(
    document_id: UUID,
    section_key: str,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    profile: str = "default",
) -> DocumentArtifact:
    from services.pipeline.steps.outline import get_facts

    kind = ArtifactKind.context_pack(section_key)
    prof = get_profile(profile)
    spec = get_section_spec(section_key)

    def builder() -> dict[str, Any]:
        document = Document.objects.get(id=document_id)

        outline_artifact = get_success_artifact(document_id, ArtifactKind.OUTLINE.value)
        if not outline_artifact or not outline_artifact.data_json:
            raise ValueError(f"No outline found for document {document_id}")

        outline = outline_artifact.data_json
        facts = get_facts(document)
        summaries = get_previous_summaries(document, section_key, limit=3)

        global_context = f"Проект: {document.params.get('title', 'Анализ ПО')}\nТип документа: {document.get_type_display()}"

        prompting_spec = spec.to_prompting_spec() if spec else None

        context_pack = slice_for_section(
            section_key=section_key,
            facts=facts,
            outline=outline,
            summaries=summaries,
            global_context=global_context,
            max_facts=prof.max_facts,
        )

        selected_fact_keys = [ref.fact_id for ref in context_pack.debug.selected_fact_refs]
        selected_fact_tags = list(set(
            ref.reason.replace("tag_match:", "").replace("key_match:", "")
            for ref in context_pack.debug.selected_fact_refs
            if ref.reason.startswith(("tag_match:", "key_match:"))
        ))

        context_pack_data = {
            "section_key": context_pack.section_key,
            "selected_facts": {
                "keys": selected_fact_keys,
                "tags": selected_fact_tags,
                "count": len(context_pack.debug.selected_fact_refs),
            },
            "outline_excerpt": context_pack.layers.outline_excerpt,
            "summaries_used": [s["section_key"] for s in summaries],
            "layers": {
                "global_context": context_pack.layers.global_context,
                "outline_excerpt": context_pack.layers.outline_excerpt,
                "facts_slice": context_pack.layers.facts_slice,
                "summaries": context_pack.layers.summaries,
                "constraints": context_pack.layers.constraints
            },
            "rendered_prompt": {
                "system": context_pack.rendered_prompt.system,
                "user": context_pack.rendered_prompt.user
            },
            "budget": {
                "max_input_tokens_approx": context_pack.budget.max_input_tokens_approx,
                "max_output_tokens": context_pack.budget.max_output_tokens,
                "soft_char_limit": context_pack.budget.soft_char_limit,
                "estimated_input_tokens": context_pack.budget.estimated_input_tokens
            },
            "debug": {
                "selected_fact_refs": [
                    {"fact_id": ref.fact_id, "reason": ref.reason, "weight": ref.weight}
                    for ref in context_pack.debug.selected_fact_refs
                ],
                "selection_reason": context_pack.debug.selection_reason,
                "trims_applied": context_pack.debug.trims_applied
            },
            "profile": profile,
        }

        return {
            "data_json": context_pack_data,
            "format": DocumentArtifact.Format.JSON,
            "meta": {
                "profile": profile,
                "estimated_tokens": context_pack.budget.estimated_input_tokens,
            },
        }

    return ensure_artifact(
        document_id=document_id,
        kind=kind,
        builder_fn=builder,
        force=force,
        job_id=job_id,
        section_key=section_key,
    )
