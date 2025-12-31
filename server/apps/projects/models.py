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
        ]

    def __str__(self):
        return f"AnalysisRun {self.id} ({self.status})"


class Artifact(models.Model):
    class Kind(models.TextChoices):
        FACTS = 'facts', 'Facts JSON'
        SCREENSHOT = 'screenshot', 'Screenshot'
        DOCX = 'docx', 'DOCX Document'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name='artifacts')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    schema_version = models.CharField(max_length=10, default='v1', help_text='Schema version for forward compatibility')
    data = models.JSONField(blank=True, null=True)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'artifacts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', 'schema_version']),
        ]

    def __str__(self):
        return f"Artifact {self.kind} for {self.analysis_run_id}"


class Document(models.Model):
    class Type(models.TextChoices):
        COURSE = 'course', 'Course Work'
        DIPLOMA = 'diploma', 'Diploma'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        GENERATING = 'generating', 'Generating'
        READY = 'ready', 'Ready'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name='documents')
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.COURSE)
    language = models.CharField(max_length=10, default='ru-RU')
    target_pages = models.IntegerField(default=40)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'documents'
        ordering = ['-created_at']

    def __str__(self):
        return f"Document {self.type} ({self.status})"


class Section(models.Model):
    class Key(models.TextChoices):
        OUTLINE = 'outline', 'Outline'
        THEORY = 'theory', 'Theory'
        PRACTICE = 'practice', 'Practice'
        CONCLUSION = 'conclusion', 'Conclusion'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        GENERATING = 'generating', 'Generating'
        READY = 'ready', 'Ready'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='sections')
    key = models.CharField(max_length=20, choices=Key.choices)
    title = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    content = models.TextField(blank=True)
    summary = models.TextField(blank=True, help_text='200-300 words summary for next section context')
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sections'
        ordering = ['order']
        unique_together = ['document', 'key']

    def __str__(self):
        return f"Section {self.key} ({self.status})"
