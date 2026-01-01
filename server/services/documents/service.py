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

        with transaction.atomic():
            artifact = DocumentArtifact.objects.create(
                document=document,
                job_id=uuid.UUID(job_id) if job_id else None,
                kind=DocumentArtifact.Kind.OUTLINE,
                format=DocumentArtifact.Format.JSON,
                data_json=outline_data,
                meta=meta
            )
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
            facts = self.get_facts(document)

            outline_json = ""
            outline_artifact_id = None
            if document.outline_current:
                outline_json = json.dumps(
                    document.outline_current.data_json,
                    ensure_ascii=False,
                    indent=2
                )
                outline_artifact_id = str(document.outline_current.id)

            if self.mock_mode:
                content_text = MOCK_SECTION_TEXT.format(
                    title=section.title,
                    key=section.key
                )
                meta = {"mock": True, "job_id": job_id}
            else:
                facts_slice = json.dumps(facts, ensure_ascii=False, indent=2)[:6000]

                user_prompt = SECTION_USER_TEMPLATE.format(
                    section_key=section.key,
                    section_title=section.title,
                    outline_json=outline_json or "Не задан",
                    facts_slice=facts_slice
                )

                result = self.llm_client.generate_text(
                    system=SECTION_SYSTEM,
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
                    "outline_artifact_id": outline_artifact_id,
                    "job_id": job_id
                }

            with transaction.atomic():
                artifact = DocumentArtifact.objects.create(
                    document=document,
                    section=section,
                    job_id=uuid.UUID(job_id) if job_id else None,
                    kind=DocumentArtifact.Kind.SECTION_TEXT,
                    format=DocumentArtifact.Format.MARKDOWN,
                    content_text=content_text,
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
