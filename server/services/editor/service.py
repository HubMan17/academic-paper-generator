import uuid
from typing import Optional
from django.db import transaction
from asgiref.sync import sync_to_async

from apps.projects.models import Document, Section, DocumentArtifact
from services.llm import LLMClient

from .schema import (
    EditLevel,
    QualityReport,
    EditPlan,
    Glossary,
    ConsistencyReport,
    DocumentEdited,
    SectionEdited,
    Transition,
    ChapterConclusion,
)
from .analyzer import analyze_document
from .planner import create_edit_plan, edit_plan_to_dict
from .terminology import (
    build_glossary,
    apply_glossary,
    glossary_to_dict,
    consistency_report_to_dict,
)
from .section_editor import edit_section, section_edited_to_dict
from .transitions import generate_transitions, transitions_to_dict
from .conclusions import (
    generate_chapter_conclusions,
    generate_final_conclusion,
    chapter_conclusions_to_dict,
)
from .assembler import (
    assemble_document,
    document_edited_to_dict,
    merge_sections_with_edits,
)
from .validator import (
    validate_document,
    compare_quality_reports,
    quality_report_to_dict,
)


class EditorService:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    async def run_full_pipeline(
        self,
        document_id: uuid.UUID,
        level: EditLevel = EditLevel.LEVEL_1,
        force: bool = False,
    ) -> DocumentEdited:
        document = await sync_to_async(
            Document.objects.select_related('analysis_run').get
        )(id=document_id)

        if document.status == Document.Status.FINALIZED and not force:
            existing = await sync_to_async(self._get_existing_document_edited)(document)
            if existing:
                return existing

        document.status = Document.Status.EDITING
        await sync_to_async(document.save)(update_fields=['status'])

        try:
            sections = await sync_to_async(self._get_sections_data)(document)
            outline = await sync_to_async(self._get_outline)(document)
            summaries = await sync_to_async(self._get_section_summaries)(document)
            idempotency_prefix = f"edit:{document_id}"

            quality_report_v1 = await self.step_analyze(document, sections)

            edit_plan = await self.step_plan(
                document, outline, summaries, quality_report_v1, level, idempotency_prefix
            )

            glossary, consistency_report = await self.step_terminology(
                document, sections, quality_report_v1, idempotency_prefix
            )

            sections = self._apply_consistency(sections, consistency_report)

            edited_sections = await self.step_edit_sections(
                document, sections, glossary, edit_plan, level, idempotency_prefix
            )

            transitions = await self.step_transitions(
                document, sections, edit_plan, idempotency_prefix
            )

            chapter_conclusions = await self.step_conclusions(
                document, outline, summaries, idempotency_prefix
            )

            conclusion_text = await self._generate_final_conclusion(
                document, chapter_conclusions, sections, idempotency_prefix
            )

            document_edited = await self.step_assemble(
                document, sections, edited_sections, transitions,
                chapter_conclusions, conclusion_text
            )

            quality_report_v2 = await self.step_validate(
                document, document_edited, quality_report_v1
            )
            document_edited.quality_report_v2 = quality_report_v2

            document.status = Document.Status.FINALIZED
            await sync_to_async(document.save)(update_fields=['status', 'updated_at'])

            return document_edited

        except Exception as e:
            document.status = Document.Status.ERROR
            await sync_to_async(document.save)(update_fields=['status'])
            raise

    async def step_analyze(
        self,
        document: Document,
        sections: list[dict],
    ) -> QualityReport:
        quality_report = analyze_document(sections)

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.EDIT_QUALITY_REPORT,
            data_json=quality_report_to_dict(quality_report),
            version="v1",
        )

        return quality_report

    def run_analyze_only(self, document: Document) -> tuple[QualityReport, DocumentArtifact]:
        sections = self._get_sections_data(document)
        quality_report = analyze_document(sections)

        artifact = self._save_artifact(
            document=document,
            kind=DocumentArtifact.Kind.EDIT_QUALITY_REPORT,
            data_json=quality_report_to_dict(quality_report),
            version="v1",
        )

        return quality_report, artifact

    async def step_plan(
        self,
        document: Document,
        outline: dict,
        summaries: list[dict],
        quality_report: QualityReport,
        level: EditLevel,
        idempotency_prefix: str,
    ) -> EditPlan:
        edit_plan = await sync_to_async(create_edit_plan)(
            llm_client=self.llm_client,
            outline=outline,
            section_summaries=summaries,
            quality_report=quality_report,
            level=level,
            idempotency_key=f"{idempotency_prefix}:plan",
        )

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.EDIT_PLAN,
            data_json=edit_plan_to_dict(edit_plan),
        )

        return edit_plan

    async def step_terminology(
        self,
        document: Document,
        sections: list[dict],
        quality_report: QualityReport,
        idempotency_prefix: str,
    ) -> tuple[Glossary, ConsistencyReport]:
        glossary = await sync_to_async(build_glossary)(
            llm_client=self.llm_client,
            term_candidates=quality_report.term_candidates,
            sections=sections,
            idempotency_key=f"{idempotency_prefix}:glossary",
        )

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.GLOSSARY,
            data_json=glossary_to_dict(glossary),
        )

        _, consistency_report = apply_glossary(sections, glossary)

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.CONSISTENCY_REPORT,
            data_json=consistency_report_to_dict(consistency_report),
        )

        return glossary, consistency_report

    def _apply_consistency(
        self,
        sections: list[dict],
        consistency_report: ConsistencyReport,
    ) -> list[dict]:
        replacements_by_section = {}
        for r in consistency_report.replacements_made:
            if r.section_key not in replacements_by_section:
                replacements_by_section[r.section_key] = []
            replacements_by_section[r.section_key].append(r)

        updated = []
        for section in sections:
            key = section.get("key", "")
            text = section.get("text", "")

            if key in replacements_by_section:
                for r in sorted(
                    replacements_by_section[key],
                    key=lambda x: -x.position
                ):
                    text = (
                        text[:r.position] +
                        r.replacement +
                        text[r.position + len(r.original):]
                    )

            updated.append({**section, "text": text})

        return updated

    async def step_edit_sections(
        self,
        document: Document,
        sections: list[dict],
        glossary: Glossary,
        edit_plan: EditPlan,
        level: EditLevel,
        idempotency_prefix: str,
    ) -> dict[str, SectionEdited]:
        edited_sections: dict[str, SectionEdited] = {}
        completed_keys = await sync_to_async(self._get_completed_section_edits)(document)

        sections_by_key = {s["key"]: s for s in sections}
        ordered_keys = [s["key"] for s in sections]

        for section_plan in edit_plan.sections_to_edit:
            key = section_plan.key

            if key in completed_keys:
                continue

            if key not in sections_by_key:
                continue

            section = sections_by_key[key]
            key_index = ordered_keys.index(key)

            prev_text = ""
            next_text = ""

            if key_index > 0:
                prev_key = ordered_keys[key_index - 1]
                prev_text = sections_by_key[prev_key].get("text", "")

            if key_index < len(ordered_keys) - 1:
                next_key = ordered_keys[key_index + 1]
                next_text = sections_by_key[next_key].get("text", "")

            db_section = await sync_to_async(
                Section.objects.filter(document=document, key=key).first
            )()

            result = await sync_to_async(edit_section)(
                llm_client=self.llm_client,
                section_key=key,
                section_text=section.get("text", ""),
                prev_section_text=prev_text,
                next_section_text=next_text,
                glossary=glossary,
                edit_plan=edit_plan,
                level=level,
                idempotency_key=f"{idempotency_prefix}:section:{key}",
            )

            await sync_to_async(self._save_artifact)(
                document=document,
                section=db_section,
                kind=DocumentArtifact.Kind.SECTION_EDITED,
                content_text=result.edited_text,
                data_json=section_edited_to_dict(result),
            )

            edited_sections[key] = result

        return edited_sections

    async def step_transitions(
        self,
        document: Document,
        sections: list[dict],
        edit_plan: EditPlan,
        idempotency_prefix: str,
    ) -> list[Transition]:
        transitions = await sync_to_async(generate_transitions)(
            llm_client=self.llm_client,
            sections=sections,
            edit_plan=edit_plan,
            idempotency_prefix=idempotency_prefix,
        )

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.TRANSITIONS,
            data_json=transitions_to_dict(transitions),
        )

        return transitions

    async def step_conclusions(
        self,
        document: Document,
        outline: dict,
        summaries: list[dict],
        idempotency_prefix: str,
    ) -> list[ChapterConclusion]:
        conclusions = await sync_to_async(generate_chapter_conclusions)(
            llm_client=self.llm_client,
            outline=outline,
            section_summaries=summaries,
            idempotency_prefix=idempotency_prefix,
        )

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.CHAPTER_CONCLUSIONS,
            data_json=chapter_conclusions_to_dict(conclusions),
        )

        return conclusions

    async def _generate_final_conclusion(
        self,
        document: Document,
        chapter_conclusions: list[ChapterConclusion],
        sections: list[dict],
        idempotency_prefix: str,
    ) -> Optional[str]:
        conclusion_section = next(
            (s for s in sections if s.get("key") == "conclusion"),
            None
        )

        if not conclusion_section:
            return None

        outline = await sync_to_async(self._get_outline)(document)
        document_title = outline.get("title", "Документ")

        return await sync_to_async(generate_final_conclusion)(
            llm_client=self.llm_client,
            document_title=document_title,
            chapter_conclusions=chapter_conclusions,
            original_conclusion=conclusion_section.get("text", ""),
            idempotency_key=f"{idempotency_prefix}:final_conclusion",
        )

    async def step_assemble(
        self,
        document: Document,
        original_sections: list[dict],
        edited_sections: dict[str, SectionEdited],
        transitions: list[Transition],
        chapter_conclusions: list[ChapterConclusion],
        final_conclusion: Optional[str],
    ) -> DocumentEdited:
        document_edited = assemble_document(
            original_sections=original_sections,
            edited_sections=edited_sections,
            transitions=transitions,
            chapter_conclusions=chapter_conclusions,
            final_conclusion=final_conclusion,
        )

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.DOCUMENT_EDITED,
            data_json=document_edited_to_dict(document_edited),
        )

        return document_edited

    async def step_validate(
        self,
        document: Document,
        document_edited: DocumentEdited,
        quality_report_v1: QualityReport,
    ) -> QualityReport:
        quality_report_v2 = validate_document(document_edited)

        comparison = compare_quality_reports(quality_report_v1, quality_report_v2)

        await sync_to_async(self._save_artifact)(
            document=document,
            kind=DocumentArtifact.Kind.EDIT_QUALITY_REPORT,
            data_json={
                **quality_report_to_dict(quality_report_v2),
                "comparison": comparison,
            },
            version="v2",
        )

        return quality_report_v2

    def _get_sections_data(self, document: Document) -> list[dict]:
        sections = Section.objects.filter(document=document).order_by('order')
        return [
            {
                "key": s.key,
                "title": s.title,
                "text": s.text_current,
                "summary": s.summary_current,
            }
            for s in sections
        ]

    def _get_outline(self, document: Document) -> dict:
        if document.outline_current and document.outline_current.data_json:
            return document.outline_current.data_json
        return {}

    def _get_section_summaries(self, document: Document) -> list[dict]:
        sections = Section.objects.filter(document=document).order_by('order')
        return [
            {
                "key": s.key,
                "title": s.title,
                "summary": s.summary_current,
            }
            for s in sections
            if s.summary_current
        ]

    def _get_completed_section_edits(self, document: Document) -> set[str]:
        artifacts = DocumentArtifact.objects.filter(
            document=document,
            kind=DocumentArtifact.Kind.SECTION_EDITED,
        ).values_list('section__key', flat=True)
        return set(k for k in artifacts if k)

    def _get_existing_document_edited(
        self,
        document: Document
    ) -> Optional[DocumentEdited]:
        artifact = DocumentArtifact.objects.filter(
            document=document,
            kind=DocumentArtifact.Kind.DOCUMENT_EDITED,
        ).order_by('-created_at').first()

        if not artifact or not artifact.data_json:
            return None

        data = artifact.data_json
        return DocumentEdited(
            version=data.get("version", "v1"),
            sections=data.get("sections", {}),
            transitions=[
                Transition(
                    from_section=t["from_section"],
                    to_section=t["to_section"],
                    text=t["text"],
                    position=t["position"],
                )
                for t in data.get("transitions", [])
            ],
            chapter_conclusions=[
                ChapterConclusion(
                    chapter_key=c["chapter_key"],
                    chapter_title=c["chapter_title"],
                    bullets=c["bullets"],
                )
                for c in data.get("chapter_conclusions", [])
            ],
        )

    @transaction.atomic
    def _save_artifact(
        self,
        document: Document,
        kind: str,
        data_json: Optional[dict] = None,
        content_text: Optional[str] = None,
        section: Optional[Section] = None,
        version: str = "v1",
    ) -> DocumentArtifact:
        format_type = DocumentArtifact.Format.JSON
        if content_text and not data_json:
            format_type = DocumentArtifact.Format.TEXT

        return DocumentArtifact.objects.create(
            document=document,
            section=section,
            kind=kind,
            format=format_type,
            version=version,
            data_json=data_json,
            content_text=content_text,
        )


async def edit_single_section(
    document_id: uuid.UUID,
    section_key: str,
    level: EditLevel = EditLevel.LEVEL_1,
    force: bool = False,
) -> SectionEdited:
    service = EditorService()
    document = await sync_to_async(Document.objects.get)(id=document_id)

    if not force:
        existing = await sync_to_async(
            DocumentArtifact.objects.filter(
                document=document,
                section__key=section_key,
                kind=DocumentArtifact.Kind.SECTION_EDITED,
            ).first
        )()
        if existing and existing.content_text:
            return SectionEdited(
                key=section_key,
                original_text="",
                edited_text=existing.content_text,
                changes_made=["Loaded from cache"],
            )

    sections = await sync_to_async(service._get_sections_data)(document)
    outline = await sync_to_async(service._get_outline)(document)
    summaries = await sync_to_async(service._get_section_summaries)(document)

    quality_report = analyze_document(sections)

    edit_plan = await sync_to_async(create_edit_plan)(
        llm_client=service.llm_client,
        outline=outline,
        section_summaries=summaries,
        quality_report=quality_report,
        level=level,
    )

    glossary = await sync_to_async(build_glossary)(
        llm_client=service.llm_client,
        term_candidates=quality_report.term_candidates,
        sections=sections,
    )

    sections_by_key = {s["key"]: s for s in sections}
    ordered_keys = [s["key"] for s in sections]

    if section_key not in sections_by_key:
        raise ValueError(f"Section {section_key} not found")

    section = sections_by_key[section_key]
    key_index = ordered_keys.index(section_key)

    prev_text = ""
    next_text = ""

    if key_index > 0:
        prev_key = ordered_keys[key_index - 1]
        prev_text = sections_by_key[prev_key].get("text", "")

    if key_index < len(ordered_keys) - 1:
        next_key = ordered_keys[key_index + 1]
        next_text = sections_by_key[next_key].get("text", "")

    result = await sync_to_async(edit_section)(
        llm_client=service.llm_client,
        section_key=section_key,
        section_text=section.get("text", ""),
        prev_section_text=prev_text,
        next_section_text=next_text,
        glossary=glossary,
        edit_plan=edit_plan,
        level=level,
    )

    db_section = await sync_to_async(
        Section.objects.filter(document=document, key=section_key).first
    )()

    await sync_to_async(service._save_artifact)(
        document=document,
        section=db_section,
        kind=DocumentArtifact.Kind.SECTION_EDITED,
        content_text=result.edited_text,
        data_json=section_edited_to_dict(result),
    )

    return result
