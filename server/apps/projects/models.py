import uuid
from django.db import models


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    repo_url = models.URLField(max_length=500)
    default_branch = models.CharField(max_length=100, default='main')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.repo_url}"


class AnalysisRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='analysis_runs')
    commit_sha = models.CharField(max_length=40, blank=True, null=True)
    fingerprint = models.CharField(max_length=64, db_index=True, blank=True, default='')
    params = models.JSONField(default=dict, blank=True)
    analyzer_version = models.CharField(max_length=16, default='v1')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    progress = models.IntegerField(default=0, help_text='0..100')
    error = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analysis_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'commit_sha']),
            models.Index(fields=['status']),
            models.Index(fields=['fingerprint']),
        ]

    def __str__(self):
        return f"AnalysisRun {self.id} ({self.status})"


class Artifact(models.Model):
    class Kind(models.TextChoices):
        FACTS = 'facts', 'Facts JSON'
        SCREENSHOT = 'screenshot', 'Screenshot'
        DOCX = 'docx', 'DOCX Document'
        META = 'meta', 'Meta Info'
        TRACE = 'trace', 'Trace Info'
        ERRORS = 'errors', 'Errors Info'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name='artifacts')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    schema_version = models.CharField(max_length=10, default='v1')
    hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    source = models.CharField(max_length=64, blank=True, default='')
    version = models.CharField(max_length=16, default='v1')
    data = models.JSONField(blank=True, null=True)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'artifacts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', 'schema_version']),
            models.Index(fields=['analysis_run', 'kind', 'hash']),
        ]

    def __str__(self):
        return f"Artifact {self.kind} for {self.analysis_run_id}"


class DocumentArtifact(models.Model):
    class Kind(models.TextChoices):
        OUTLINE = 'outline', 'Outline JSON'
        SECTION_TEXT = 'section_text', 'Section Text'
        SECTION_SUMMARY = 'section_summary', 'Section Summary'
        CONTEXT_PACK = 'context_pack', 'Context Pack'
        TRACE = 'trace', 'Generation Trace'
        LLM_TRACE = 'llm_trace', 'LLM Call Trace'
        EDIT_PLAN = 'edit_plan', 'Edit Plan'
        QUALITY_REPORT = 'quality_report', 'Quality Report'
        EDIT_QUALITY_REPORT = 'edit_quality_report', 'Edit Quality Report'
        GLOSSARY = 'glossary', 'Glossary'
        CONSISTENCY_REPORT = 'consistency_report', 'Consistency Report'
        CHAPTER_CONCLUSIONS = 'chapter_conclusions', 'Chapter Conclusions'
        TRANSITIONS = 'transitions', 'Transitions'
        SECTION_EDITED = 'section_edited', 'Section Edited'
        DOCUMENT_EDITED = 'document_edited', 'Document Edited'

    class Format(models.TextChoices):
        JSON = 'json', 'JSON'
        MARKDOWN = 'markdown', 'Markdown'
        TEXT = 'text', 'Text'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey('Document', on_delete=models.CASCADE, related_name='doc_artifacts')
    section = models.ForeignKey('Section', on_delete=models.CASCADE, related_name='doc_artifacts', null=True, blank=True)
    job_id = models.UUIDField(null=True, blank=True, db_index=True)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    format = models.CharField(max_length=16, choices=Format.choices)
    hash = models.CharField(max_length=64, db_index=True, blank=True, default='')
    source = models.CharField(max_length=64, blank=True, default='')
    version = models.CharField(max_length=16, default='v1')
    data_json = models.JSONField(null=True, blank=True)
    content_text = models.TextField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'document_artifact'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', 'kind', 'created_at']),
            models.Index(fields=['section', 'kind', 'created_at']),
            models.Index(fields=['document', 'kind', 'hash']),
        ]

    def __str__(self):
        return f"DocumentArtifact {self.kind} for {self.document_id}"


class Document(models.Model):
    class Type(models.TextChoices):
        COURSE = 'course', 'Course Work'
        DIPLOMA = 'diploma', 'Diploma'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        GENERATING = 'generating', 'Generating'
        READY = 'ready', 'Ready'
        EDITING = 'editing', 'Editing'
        FINALIZED = 'finalized', 'Finalized'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name='documents')
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.COURSE)
    language = models.CharField(max_length=10, default='ru-RU')
    target_pages = models.IntegerField(default=40)
    params = models.JSONField(default=dict, blank=True)
    outline_current = models.ForeignKey(
        'DocumentArtifact',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='as_current_outline_for_documents'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'documents'
        ordering = ['-created_at']

    def __str__(self):
        return f"Document {self.type} ({self.status})"


class Section(models.Model):
    class Status(models.TextChoices):
        IDLE = 'idle', 'Idle'
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='sections')
    key = models.CharField(max_length=50)
    title = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IDLE)
    text_current = models.TextField(blank=True)
    summary_current = models.TextField(blank=True)
    version = models.IntegerField(default=0)
    last_artifact = models.ForeignKey(
        'DocumentArtifact',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='as_last_for_sections'
    )
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sections'
        ordering = ['order']
        unique_together = ['document', 'key']

    def __str__(self):
        return f"Section {self.key} ({self.status})"
