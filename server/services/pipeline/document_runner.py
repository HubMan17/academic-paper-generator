import logging
import time
from dataclasses import dataclass, field
from typing import Callable
from uuid import UUID

from apps.projects.models import Document
from services.pipeline.ensure import get_success_artifact
from services.pipeline.kinds import ArtifactKind
from services.pipeline.profiles import get_profile
from services.pipeline.specs import get_all_section_keys, get_section_spec
from services.pipeline.steps import (
    ensure_outline,
    ensure_outline_v2,
    ensure_context_pack,
    ensure_section,
    ensure_section_summary,
    ensure_document_draft,
    ensure_toc,
    ensure_quality_report,
    ensure_enrichment,
    ensure_literature,
)

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    success: bool
    document_id: str
    job_id: str | None
    profile: str
    artifacts_created: list[str] = field(default_factory=list)
    artifacts_cached: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    progress: int = 100


class DocumentRunner:
    def __init__(
        self,
        document_id: UUID,
        profile: str = "default",
        mock_mode: bool = False,
        progress_callback: Callable[[int, str], None] | None = None,
    ):
        self.document_id = document_id
        self.profile = profile
        self.mock_mode = mock_mode
        self.progress_callback = progress_callback

        get_profile(profile)

        self._artifacts_created: list[str] = []
        self._artifacts_cached: list[str] = []
        self._errors: list[dict] = []

    def _report_progress(self, progress: int, message: str):
        if self.progress_callback:
            self.progress_callback(progress, message)
        logger.info(f"Progress {progress}%: {message}")

    def _track_artifact(self, kind: str, was_cached: bool):
        if was_cached:
            self._artifacts_cached.append(kind)
        else:
            self._artifacts_created.append(kind)

    def run_full(
        self,
        job_id: UUID | None = None,
        force: bool = False,
    ) -> RunResult:
        start_time = time.time()
        self._artifacts_created = []
        self._artifacts_cached = []
        self._errors = []

        try:
            self._report_progress(0, "Starting document generation")

            self._run_outline(job_id, force)
            self._report_progress(10, "Outline completed")

            section_keys = get_all_section_keys()
            section_count = len(section_keys)

            for i, key in enumerate(section_keys):
                progress_base = 10 + int((i / section_count) * 75)
                self._run_section_full(key, job_id, force)
                progress = 10 + int(((i + 1) / section_count) * 75)
                self._report_progress(progress, f"Section {key} completed")

            self._report_progress(78, "Running enrichment")
            self._run_enrichment(job_id, force)

            self._report_progress(82, "Running editing")
            self._run_editing(job_id, force)

            self._report_progress(86, "Generating literature")
            self._run_literature(job_id, force)

            self._report_progress(90, "Assembling document")
            self._run_assemble(job_id, force)

            self._report_progress(94, "Generating TOC")
            self._run_toc(job_id, force)

            self._report_progress(97, "Running quality checks")
            duration_ms = int((time.time() - start_time) * 1000)
            self._run_quality(job_id, force, duration_ms)
            self._report_progress(100, "Document generation complete")

            return RunResult(
                success=True,
                document_id=str(self.document_id),
                job_id=str(job_id) if job_id else None,
                profile=self.profile,
                artifacts_created=self._artifacts_created,
                artifacts_cached=self._artifacts_cached,
                errors=self._errors,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception(f"Document run failed: {e}")
            self._errors.append({"step": "run_full", "error": str(e)})
            duration_ms = int((time.time() - start_time) * 1000)
            return RunResult(
                success=False,
                document_id=str(self.document_id),
                job_id=str(job_id) if job_id else None,
                profile=self.profile,
                artifacts_created=self._artifacts_created,
                artifacts_cached=self._artifacts_cached,
                errors=self._errors,
                duration_ms=duration_ms,
                progress=0,
            )

    def run_section(
        self,
        section_key: str,
        job_id: UUID | None = None,
        force: bool = False,
    ) -> RunResult:
        start_time = time.time()
        self._artifacts_created = []
        self._artifacts_cached = []
        self._errors = []

        try:
            self._report_progress(0, f"Starting section {section_key}")

            outline = get_success_artifact(self.document_id, ArtifactKind.OUTLINE.value)
            if not outline:
                self._run_outline(job_id, force=False)

            self._run_section_full(section_key, job_id, force)
            self._report_progress(80, f"Section {section_key} completed")

            self._run_assemble(job_id, force=True)
            self._report_progress(90, "Document reassembled")

            duration_ms = int((time.time() - start_time) * 1000)
            self._run_quality(job_id, force=True, start_time_ms=duration_ms)
            self._report_progress(100, "Quality check complete")

            return RunResult(
                success=True,
                document_id=str(self.document_id),
                job_id=str(job_id) if job_id else None,
                profile=self.profile,
                artifacts_created=self._artifacts_created,
                artifacts_cached=self._artifacts_cached,
                errors=self._errors,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception(f"Section run failed: {e}")
            self._errors.append({"step": f"run_section:{section_key}", "error": str(e)})
            duration_ms = int((time.time() - start_time) * 1000)
            return RunResult(
                success=False,
                document_id=str(self.document_id),
                job_id=str(job_id) if job_id else None,
                profile=self.profile,
                artifacts_created=self._artifacts_created,
                artifacts_cached=self._artifacts_cached,
                errors=self._errors,
                duration_ms=duration_ms,
                progress=0,
            )

    def resume(
        self,
        job_id: UUID | None = None,
    ) -> RunResult:
        start_time = time.time()
        self._artifacts_created = []
        self._artifacts_cached = []
        self._errors = []

        try:
            self._report_progress(0, "Resuming document generation")

            outline = get_success_artifact(self.document_id, ArtifactKind.OUTLINE.value)
            if not outline:
                self._run_outline(job_id, force=False)
                self._report_progress(10, "Outline created")
            else:
                self._track_artifact(ArtifactKind.OUTLINE.value, was_cached=True)
                self._report_progress(10, "Outline exists, skipping")

            section_keys = get_all_section_keys()
            section_count = len(section_keys)
            resume_from = None

            for key in section_keys:
                section_artifact = get_success_artifact(
                    self.document_id, ArtifactKind.section(key)
                )
                if not section_artifact:
                    resume_from = key
                    break
                self._track_artifact(ArtifactKind.section(key), was_cached=True)

            if resume_from is None:
                self._report_progress(85, "All sections complete, reassembling")
            else:
                start_idx = section_keys.index(resume_from)
                for i, key in enumerate(section_keys[start_idx:], start=start_idx):
                    progress_base = 10 + int((i / section_count) * 75)
                    self._run_section_full(key, job_id, force=False)
                    progress = 10 + int(((i + 1) / section_count) * 75)
                    self._report_progress(progress, f"Section {key} completed")

            self._run_assemble(job_id, force=True)
            self._report_progress(90, "Document assembled")

            self._run_toc(job_id, force=True)
            self._report_progress(95, "TOC generated")

            duration_ms = int((time.time() - start_time) * 1000)
            self._run_quality(job_id, force=True, start_time_ms=duration_ms)
            self._report_progress(100, "Resume complete")

            return RunResult(
                success=True,
                document_id=str(self.document_id),
                job_id=str(job_id) if job_id else None,
                profile=self.profile,
                artifacts_created=self._artifacts_created,
                artifacts_cached=self._artifacts_cached,
                errors=self._errors,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception(f"Resume failed: {e}")
            self._errors.append({"step": "resume", "error": str(e)})
            duration_ms = int((time.time() - start_time) * 1000)
            return RunResult(
                success=False,
                document_id=str(self.document_id),
                job_id=str(job_id) if job_id else None,
                profile=self.profile,
                artifacts_created=self._artifacts_created,
                artifacts_cached=self._artifacts_cached,
                errors=self._errors,
                duration_ms=duration_ms,
                progress=0,
            )

    def _run_outline(self, job_id: UUID | None, force: bool):
        kind = ArtifactKind.OUTLINE.value
        existing = get_success_artifact(self.document_id, kind)

        artifact = ensure_outline(
            document_id=self.document_id,
            force=force,
            job_id=job_id,
            profile=self.profile,
            mock_mode=self.mock_mode,
        )
        self._track_artifact(kind, was_cached=(existing is not None and not force))

    def _run_section_full(self, key: str, job_id: UUID | None, force: bool):
        cp_kind = ArtifactKind.context_pack(key)
        existing_cp = get_success_artifact(self.document_id, cp_kind)

        ensure_context_pack(
            document_id=self.document_id,
            section_key=key,
            force=force,
            job_id=job_id,
            profile=self.profile,
        )
        self._track_artifact(cp_kind, was_cached=(existing_cp is not None and not force))

        section_kind = ArtifactKind.section(key)
        existing_section = get_success_artifact(self.document_id, section_kind)

        ensure_section(
            document_id=self.document_id,
            section_key=key,
            force=force,
            job_id=job_id,
            profile=self.profile,
            mock_mode=self.mock_mode,
        )
        self._track_artifact(section_kind, was_cached=(existing_section is not None and not force))

        summary_kind = ArtifactKind.section_summary(key)
        existing_summary = get_success_artifact(self.document_id, summary_kind)

        ensure_section_summary(
            document_id=self.document_id,
            section_key=key,
            force=force,
            job_id=job_id,
            profile=self.profile,
            mock_mode=self.mock_mode,
        )
        self._track_artifact(summary_kind, was_cached=(existing_summary is not None and not force))

    def _run_assemble(self, job_id: UUID | None, force: bool):
        kind = ArtifactKind.DOCUMENT_DRAFT.value
        existing = get_success_artifact(self.document_id, kind)

        ensure_document_draft(
            document_id=self.document_id,
            force=force,
            job_id=job_id,
        )
        self._track_artifact(kind, was_cached=(existing is not None and not force))

    def _run_toc(self, job_id: UUID | None, force: bool):
        kind = ArtifactKind.TOC.value
        existing = get_success_artifact(self.document_id, kind)

        ensure_toc(
            document_id=self.document_id,
            force=force,
            job_id=job_id,
        )
        self._track_artifact(kind, was_cached=(existing is not None and not force))

    def _run_quality(self, job_id: UUID | None, force: bool, start_time_ms: int | None = None):
        kind = ArtifactKind.QUALITY_REPORT.value
        existing = get_success_artifact(self.document_id, kind)

        ensure_quality_report(
            document_id=self.document_id,
            force=force,
            job_id=job_id,
            start_time_ms=start_time_ms,
        )
        self._track_artifact(kind, was_cached=(existing is not None and not force))

    def _run_enrichment(self, job_id: UUID | None, force: bool):
        kind = "enrichment_report:v1"
        existing = get_success_artifact(self.document_id, kind)

        ensure_enrichment(
            document_id=self.document_id,
            force=force,
            job_id=job_id,
            mock_mode=self.mock_mode,
        )
        self._track_artifact(kind, was_cached=(existing is not None and not force))

    def _run_editing(self, job_id: UUID | None, force: bool):
        from asgiref.sync import async_to_sync
        from apps.projects.models import DocumentArtifact
        from services.editor import EditorService
        from services.editor.schema import EditLevel

        document = Document.objects.get(id=self.document_id)

        existing = DocumentArtifact.objects.filter(
            document=document,
            kind=DocumentArtifact.Kind.DOCUMENT_EDITED,
        ).exists()

        if existing and not force:
            self._track_artifact("document_edited:v1", was_cached=True)
            return

        if document.current_stage != Document.Stage.EDITING:
            document.current_stage = Document.Stage.EDITING
            document.status = Document.Status.EDITING
            document.save(update_fields=['current_stage', 'status', 'updated_at'])

        doc_profile = document.profile
        if doc_profile:
            style_level = doc_profile.style_level
            if style_level >= 3:
                level = EditLevel.LEVEL_3
            elif style_level >= 2:
                level = EditLevel.LEVEL_2
            else:
                level = EditLevel.LEVEL_1
        else:
            level = EditLevel.LEVEL_1

        service = EditorService()
        async_to_sync(service.run_full_pipeline)(
            document_id=self.document_id,
            level=level,
            force=force,
        )

        self._track_artifact("document_edited:v1", was_cached=False)

    def _run_literature(self, job_id: UUID | None, force: bool):
        kind = ArtifactKind.LITERATURE.value
        existing = get_success_artifact(self.document_id, kind)

        ensure_literature(
            document_id=self.document_id,
            force=force,
            job_id=job_id,
            profile=self.profile,
            mock_mode=self.mock_mode,
        )
        self._track_artifact(kind, was_cached=(existing is not None and not force))
