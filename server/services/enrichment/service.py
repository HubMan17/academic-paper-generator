import logging
from typing import Any
from uuid import UUID

from apps.projects.models import Document, Section, DocumentArtifact, Artifact
from services.llm import LLMClient
from services.enrichment.schema import (
    EnrichmentPlan,
    EnrichmentReport,
    EnrichmentResult,
    enrichment_plan_to_dict,
    enrichment_report_to_dict,
)
from services.enrichment.analyzer import detect_short_sections
from services.enrichment.enricher import enrich_section
from services.pipeline.specs import get_section_spec, get_sections_for_work_type

logger = logging.getLogger(__name__)


class EnrichmentService:
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self._llm_client: LLMClient | None = None

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def analyze_document(self, document_id: UUID) -> EnrichmentPlan:
        document = Document.objects.get(id=document_id)
        sections = list(document.sections.all().order_by('order'))

        sections_data = []
        for s in sections:
            sections_data.append({
                'key': s.key,
                'text_current': s.text_current,
            })

        work_type = document.profile.work_type if document.profile else document.type
        section_specs = get_sections_for_work_type(work_type)

        specs_data = []
        for spec in section_specs:
            specs_data.append({
                'key': spec.key,
                'target_words_min': spec.target_words[0],
                'target_words_max': spec.target_words[1],
            })

        plan = detect_short_sections(sections_data, specs_data)

        facts = self._get_facts(document)
        if facts:
            plan.facts_available = len(facts.get('modules', [])) + len(facts.get('frameworks', []))

        return plan

    def run_enrichment(
        self,
        document_id: UUID,
        job_id: UUID | None = None,
    ) -> EnrichmentReport:
        document = Document.objects.select_related('profile').get(id=document_id)

        if document.current_stage != Document.Stage.ENRICHMENT:
            document.current_stage = Document.Stage.ENRICHMENT
            document.status = Document.Status.ENRICHING
            document.save(update_fields=['current_stage', 'status', 'updated_at'])

        plan = self.analyze_document(document_id)

        if not plan.needs_enrichment():
            logger.info(f"Document {document_id} does not need enrichment")
            return EnrichmentReport(
                version="v1",
                sections_enriched=[],
                total_words_added=0,
                total_facts_used=0,
            )

        facts = self._get_facts(document)
        if not facts:
            logger.warning(f"No facts available for document {document_id}")
            return EnrichmentReport(
                version="v1",
                sections_enriched=[],
                total_words_added=0,
                total_facts_used=0,
            )

        work_type = document.profile.work_type if document.profile else document.type
        section_specs = {s.key: s for s in get_sections_for_work_type(work_type)}

        results: list[EnrichmentResult] = []
        total_words_added = 0
        all_facts_used: set[str] = set()

        for need in plan.sections_to_enrich:
            section = document.sections.filter(key=need.section_key).first()
            if not section:
                continue

            spec = section_specs.get(need.section_key)
            fact_tags = list(spec.fact_tags) if spec else []

            if self.mock_mode:
                result = EnrichmentResult(
                    section_key=need.section_key,
                    original_text=section.text_current,
                    enriched_text=section.text_current + "\n\n[MOCK: Additional enriched content based on facts]",
                    facts_used=["mock_fact_1", "mock_fact_2"],
                    words_added=50,
                    success=True,
                )
            else:
                result = enrich_section(
                    llm_client=self.llm_client,
                    section_key=need.section_key,
                    section_text=section.text_current,
                    facts=facts,
                    need=need,
                    fact_tags=fact_tags,
                )

            if result.success and result.enriched_text != result.original_text:
                section.enriched_text = result.enriched_text
                section.save(update_fields=['enriched_text', 'updated_at'])

                self._save_artifact(
                    document=document,
                    section=section,
                    result=result,
                    job_id=job_id,
                )

            results.append(result)
            total_words_added += result.words_added
            all_facts_used.update(result.facts_used)

        report = EnrichmentReport(
            version="v1",
            sections_enriched=results,
            total_words_added=total_words_added,
            total_facts_used=len(all_facts_used),
        )

        logger.info(
            f"Enrichment complete for document {document_id}: "
            f"{len(results)} sections, {total_words_added} words added"
        )

        return report

    def enrich_single_section(
        self,
        document_id: UUID,
        section_key: str,
        job_id: UUID | None = None,
    ) -> EnrichmentResult:
        document = Document.objects.select_related('profile').get(id=document_id)
        section = document.sections.filter(key=section_key).first()

        if not section:
            raise ValueError(f"Section {section_key} not found in document {document_id}")

        facts = self._get_facts(document)
        if not facts:
            return EnrichmentResult(
                section_key=section_key,
                original_text=section.text_current,
                enriched_text=section.text_current,
                success=False,
                error="No facts available",
            )

        work_type = document.profile.work_type if document.profile else document.type
        spec = None
        for s in get_sections_for_work_type(work_type):
            if s.key == section_key:
                spec = s
                break

        from services.enrichment.schema import EnrichmentNeed
        from services.enrichment.analyzer import count_words

        current_words = count_words(section.text_current)
        target_min = spec.target_words[0] if spec else 500
        target_max = spec.target_words[1] if spec else 1000

        need = EnrichmentNeed(
            section_key=section_key,
            current_words=current_words,
            target_words_min=target_min,
            target_words_max=target_max,
            deficit_words=max(0, target_min - current_words),
            priority=5,
            reason="Manual enrichment request",
        )

        fact_tags = list(spec.fact_tags) if spec else []

        result = enrich_section(
            llm_client=self.llm_client,
            section_key=section_key,
            section_text=section.text_current,
            facts=facts,
            need=need,
            fact_tags=fact_tags,
        )

        if result.success and result.enriched_text != result.original_text:
            section.enriched_text = result.enriched_text
            section.save(update_fields=['enriched_text', 'updated_at'])

            self._save_artifact(
                document=document,
                section=section,
                result=result,
                job_id=job_id,
            )

        return result

    def _get_facts(self, document: Document) -> dict[str, Any] | None:
        artifact = Artifact.objects.filter(
            analysis_run=document.analysis_run,
            kind=Artifact.Kind.FACTS
        ).order_by('-created_at').first()

        if artifact and artifact.data:
            return artifact.data
        return None

    def _save_artifact(
        self,
        document: Document,
        section: Section,
        result: EnrichmentResult,
        job_id: UUID | None = None,
    ) -> DocumentArtifact:
        from services.enrichment.schema import enrichment_result_to_dict

        artifact = DocumentArtifact.objects.create(
            document=document,
            section=section,
            job_id=job_id,
            kind=DocumentArtifact.Kind.SECTION_ENRICHED,
            format=DocumentArtifact.Format.JSON,
            data_json=enrichment_result_to_dict(result),
            content_text=result.enriched_text,
            meta={
                "words_added": result.words_added,
                "facts_used_count": len(result.facts_used),
            },
        )
        return artifact
