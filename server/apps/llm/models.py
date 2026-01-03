import uuid
from django.db import models


class LLMCall(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True)
    model = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS
    )
    response_text = models.TextField(blank=True, null=True)
    response_json = models.JSONField(blank=True, null=True)
    meta = models.JSONField(default=dict)
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'llm_calls'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['model', 'status']),
        ]

    def __str__(self):
        return f"LLMCall {self.fingerprint[:8]}... ({self.status})"
