import uuid
import json
from dataclasses import asdict
from typing import Optional

from django.db import transaction

from apps.projects.models import (
    AnalysisRun, Artifact, Document, DocumentArtifact, Section
)
from services.llm import LLMClient
from services.llm.errors import LLMError
from services.utils import compute_content_hash
from services.prompting import slice_for_section, make_summary_request, parse_summary_response

from .prompts import (
    OUTLINE_SYSTEM, OUTLINE_USER_TEMPLATE,
    SECTION_SYSTEM, SECTION_USER_TEMPLATE,
    MOCK_OUTLINE, MOCK_SECTION_TEXT
)


class FactsNotFound(Exception):
    pass


class SectionBusy(Exception):
    pass


class DocumentService:
    DEFAULT_SECTIONS = [
        ('intro', 'Введение', 0),
        ('theory', 'Теоретическая часть', 1),
        ('practice', 'Практическая часть', 2),
        ('conclusion', 'Заключение', 3),
        ('references', 'Список литературы', 4),
    ]

    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self._llm_client: Optional[LLMClient] = None

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def create_document(
        self,
        analysis_run_id: str,
        params: Optional[dict] = None,
        doc_type: str = 'course',
        language: str = 'ru-RU',
        target_pages: int = 40
    ) -> Document:
        analysis_run = AnalysisRun.objects.get(id=analysis_run_id)

        with transaction.atomic():
            document = Document.objects.create(
                analysis_run=analysis_run,
                type=doc_type,
                language=language,
                target_pages=target_pages,
                params=params or {},
                status=Document.Status.DRAFT
            )

            sections = []
            for key, title, order in self.DEFAULT_SECTIONS:
                sections.append(Section(
                    document=document,
                    key=key,
                    title=title,
                    order=order,
                    status=Section.Status.IDLE,
                    version=0
                ))
            Section.objects.bulk_create(sections)

        return document

    def get_facts(self, document: Document) -> dict:
        artifact = Artifact.objects.filter(
            analysis_run=document.analysis_run,
            kind=Artifact.Kind.FACTS
        ).order_by('-created_at').first()

        if not artifact or not artifact.data:
            raise FactsNotFound(f"No facts for analysis_run {document.analysis_run_id}")
        return artifact.data

    def request_outline(self, document_id: str) -> str:
        job_id = str(uuid.uuid4())
        from tasks.document_tasks import generate_outline_task
        generate_outline_task.delay(str(document_id), job_id)
        return job_id

    def request_section_generate(self, document_id: str, section_key: str) -> str:
        document = Document.objects.get(id=document_id)
        section = document.sections.get(key=section_key)

        if section.status in (Section.Status.RUNNING, Section.Status.QUEUED):
            raise SectionBusy(f"Section {section_key} is already {section.status}")

        section.status = Section.Status.QUEUED
        section.save(update_fields=['status', 'updated_at'])

        job_id = str(uuid.uuid4())
        from tasks.document_tasks import generate_section_task
        generate_section_task.delay(str(document_id), section_key, job_id)
        return job_id

    def generate_outline(self, document: Document, job_id: Optional[str] = None) -> DocumentArtifact:
        facts = self.get_facts(document)

        if self.mock_mode:
            outline_data = MOCK_OUTLINE.copy()
            meta = {"mock": True, "job_id": job_id}
        else:
            user_prompt = OUTLINE_USER_TEMPLATE.format(
                facts_json=json.dumps(facts, ensure_ascii=False, indent=2)[:8000],
                doc_type=document.get_type_display(),
                title=document.params.get('title', 'Анализ программного обеспечения'),
                language=document.language,
                target_pages=document.target_pages,
                params=json.dumps(document.params, ensure_ascii=False)
            )

            result = self.llm_client.generate_json(
                system=OUTLINE_SYSTEM,
                user=user_prompt,
                temperature=0.3
            )
            outline_data = result.data
            meta = {
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": {
                    "prompt": result.meta.prompt_tokens,
                    "completion": result.meta.completion_tokens,
                    "total": result.meta.total_tokens
                },
                "cost_estimate": result.meta.cost_estimate,
                "job_id": job_id
            }

        content_hash = compute_content_hash(outline_data)

        with transaction.atomic():
            artifact, created = DocumentArtifact.objects.get_or_create(
                document=document,
                kind=DocumentArtifact.Kind.OUTLINE,
                hash=content_hash,
                defaults={
                    'job_id': uuid.UUID(job_id) if job_id else None,
                    'format': DocumentArtifact.Format.JSON,
                    'data_json': outline_data,
                    'meta': meta,
                    'source': 'llm' if not self.mock_mode else 'mock',
                    'version': 'v1',
                }
            )
            if not created:
                artifact.meta = meta
                artifact.job_id = uuid.UUID(job_id) if job_id else None
                artifact.save(update_fields=['meta', 'job_id'])

            document.outline_current = artifact
            document.save(update_fields=['outline_current', 'updated_at'])

        return artifact

    def generate_section_text(
        self,
        document: Document,
        section: Section,
        job_id: Optional[str] = None
    ) -> DocumentArtifact:
        section.status = Section.Status.RUNNING
        section.save(update_fields=['status', 'updated_at'])

        try:
            context_pack_artifact = self._get_context_pack_for_section(
                document, section, job_id
            )

            if self.mock_mode:
                content_text = MOCK_SECTION_TEXT.format(
                    title=section.title,
                    key=section.key
                )
                meta = {"mock": True, "job_id": job_id}
            else:
                rendered_prompt = context_pack_artifact.data_json.get("rendered_prompt", {})
                system_prompt = rendered_prompt.get("system", SECTION_SYSTEM)
                user_prompt = rendered_prompt.get("user", "")

                if not user_prompt:
                    raise ValueError(f"No rendered_prompt in context_pack for section {section.key}")

                result = self.llm_client.generate_text(
                    system=system_prompt,
                    user=user_prompt,
                    temperature=0.7
                )
                content_text = result.text
                meta = {
                    "model": result.meta.model,
                    "latency_ms": result.meta.latency_ms,
                    "tokens": {
                        "prompt": result.meta.prompt_tokens,
                        "completion": result.meta.completion_tokens,
                        "total": result.meta.total_tokens
                    },
                    "cost_estimate": result.meta.cost_estimate,
                    "context_pack_artifact_id": str(context_pack_artifact.id),
                    "job_id": job_id
                }

            content_hash = compute_content_hash(content_text)

            with transaction.atomic():
                artifact = DocumentArtifact.objects.create(
                    document=document,
                    section=section,
                    job_id=uuid.UUID(job_id) if job_id else None,
                    kind=DocumentArtifact.Kind.SECTION_TEXT,
                    format=DocumentArtifact.Format.MARKDOWN,
                    content_text=content_text,
                    hash=content_hash,
                    source='llm' if not self.mock_mode else 'mock',
                    version='v1',
                    meta=meta
                )

                section.text_current = content_text
                section.version += 1
                section.last_artifact = artifact
                section.status = Section.Status.SUCCESS
                section.last_error = ''
                section.save(update_fields=[
                    'text_current', 'version', 'last_artifact',
                    'status', 'last_error', 'updated_at'
                ])

            if not self.mock_mode:
                estimated_tokens = context_pack_artifact.data_json.get(
                    "budget", {}
                ).get("estimated_input_tokens")
                self._save_llm_trace(
                    document=document,
                    section=section,
                    operation='section_generate',
                    result_meta=result.meta,
                    related_artifact_id=str(artifact.id),
                    context_pack_artifact_id=str(context_pack_artifact.id),
                    job_id=job_id,
                    estimated_input_tokens=estimated_tokens
                )

            return artifact

        except (LLMError, FactsNotFound) as e:
            section.status = Section.Status.FAILED
            section.last_error = str(e)[:1000]
            section.save(update_fields=['status', 'last_error', 'updated_at'])
            raise
        except Exception as e:
            section.status = Section.Status.FAILED
            section.last_error = str(e)[:1000]
            section.save(update_fields=['status', 'last_error', 'updated_at'])
            raise

    def build_context_pack(
        self,
        document: Document,
        section_key: str,
        job_id: Optional[str] = None
    ) -> DocumentArtifact:
        facts = self.get_facts(document)
        outline = document.outline_current.data_json if document.outline_current else {}

        summaries = self._get_previous_summaries(document, section_key)

        global_context = f"Проект: {document.params.get('title', 'Анализ ПО')}\nТип документа: {document.get_type_display()}"

        context_pack = slice_for_section(
            section_key=section_key,
            facts=facts,
            outline=outline,
            summaries=summaries,
            global_context=global_context
        )

        context_pack_data = {
            "section_key": context_pack.section_key,
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
            }
        }

        content_hash = compute_content_hash(context_pack_data)

        section = document.sections.get(key=section_key)

        artifact = DocumentArtifact.objects.create(
            document=document,
            section=section,
            job_id=uuid.UUID(job_id) if job_id else None,
            kind=DocumentArtifact.Kind.CONTEXT_PACK,
            format=DocumentArtifact.Format.JSON,
            data_json=context_pack_data,
            hash=content_hash,
            source='prompting',
            version='v1',
            meta={"job_id": job_id}
        )

        return artifact

    def _get_context_pack_for_section(
        self,
        document: Document,
        section: Section,
        job_id: Optional[str] = None
    ) -> DocumentArtifact:
        query = DocumentArtifact.objects.filter(
            document=document,
            section=section,
            kind=DocumentArtifact.Kind.CONTEXT_PACK
        )

        if job_id:
            query = query.filter(job_id=uuid.UUID(job_id))

        artifact = query.order_by('-created_at').first()

        if not artifact:
            raise ValueError(
                f"No context_pack found for section {section.key}. "
                "Call build_context_pack() first."
            )

        return artifact

    def _get_previous_summaries(self, document: Document, current_section_key: str) -> list[dict]:
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

        return summaries[-2:] if len(summaries) > 2 else summaries

    def summarize_section(
        self,
        document: Document,
        section: Section,
        job_id: Optional[str] = None
    ) -> DocumentArtifact:
        if not section.text_current:
            raise ValueError(f"Section {section.key} has no text to summarize")

        summary_request = make_summary_request(section.text_current, section.key)

        if self.mock_mode:
            summary_text = "- Первый ключевой пункт\n- Второй ключевой пункт\n- Третий ключевой пункт"
            meta = {"mock": True, "job_id": job_id}
        else:
            result = self.llm_client.generate_text(
                system=summary_request["system"],
                user=summary_request["user"],
                temperature=0.3
            )
            summary_text = result.text
            meta = {
                "model": result.meta.model,
                "latency_ms": result.meta.latency_ms,
                "tokens": {
                    "prompt": result.meta.prompt_tokens,
                    "completion": result.meta.completion_tokens,
                    "total": result.meta.total_tokens
                },
                "cost_estimate": result.meta.cost_estimate,
                "job_id": job_id
            }

        summary_data = parse_summary_response(summary_text, section.key)
        content_hash = compute_content_hash(summary_data)

        with transaction.atomic():
            artifact = DocumentArtifact.objects.create(
                document=document,
                section=section,
                job_id=uuid.UUID(job_id) if job_id else None,
                kind=DocumentArtifact.Kind.SECTION_SUMMARY,
                format=DocumentArtifact.Format.JSON,
                data_json=summary_data,
                content_text=summary_text,
                hash=content_hash,
                source='llm' if not self.mock_mode else 'mock',
                version='v1',
                meta=meta
            )

            section.summary_current = summary_text
            section.save(update_fields=['summary_current', 'updated_at'])

        if not self.mock_mode:
            self._save_llm_trace(
                document=document,
                section=section,
                operation='section_summary',
                result_meta=result.meta,
                related_artifact_id=str(artifact.id),
                job_id=job_id
            )

        return artifact

    def _save_llm_trace(
        self,
        document: Document,
        section: Optional[Section],
        operation: str,
        result_meta,
        related_artifact_id: Optional[str] = None,
        context_pack_artifact_id: Optional[str] = None,
        job_id: Optional[str] = None,
        estimated_input_tokens: Optional[int] = None
    ) -> DocumentArtifact:
        actual_prompt_tokens = result_meta.prompt_tokens or 0
        estimation_error_ratio = None

        if estimated_input_tokens and estimated_input_tokens > 0 and actual_prompt_tokens > 0:
            estimation_error_ratio = round(
                (actual_prompt_tokens / estimated_input_tokens) - 1.0, 3
            )

        trace_data = {
            "operation": operation,
            "model": result_meta.model,
            "latency_ms": result_meta.latency_ms,
            "tokens": {
                "prompt": actual_prompt_tokens,
                "completion": result_meta.completion_tokens,
                "total": result_meta.total_tokens
            },
            "cost_estimate": result_meta.cost_estimate,
            "section_key": section.key if section else None,
            "related_artifact_id": related_artifact_id,
            "context_pack_artifact_id": context_pack_artifact_id,
            "job_id": job_id,
            "estimated_input_tokens": estimated_input_tokens,
            "estimation_error_ratio": estimation_error_ratio
        }

        return DocumentArtifact.objects.create(
            document=document,
            section=section,
            job_id=uuid.UUID(job_id) if job_id else None,
            kind=DocumentArtifact.Kind.LLM_TRACE,
            format=DocumentArtifact.Format.JSON,
            data_json=trace_data,
            hash='',
            source='llm',
            version='v1',
            meta={}
        )
