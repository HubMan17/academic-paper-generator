from rest_framework import serializers
from .models import Project, AnalysisRun, Artifact, Document, Section


class AnalyzeRequestSerializer(serializers.Serializer):
    repo_url = serializers.URLField(
        required=True,
        help_text="URL репозитория для анализа (GitHub, GitLab, Bitbucket)"
    )
    branch = serializers.CharField(
        required=False,
        default='main',
        help_text="Ветка для анализа"
    )


class JobCreateResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField(help_text='ID задачи анализа (= analysis_run_id)')
    project_id = serializers.UUIDField(help_text='ID проекта')
    status = serializers.CharField()
    message = serializers.CharField()


class ArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact
        fields = ['id', 'kind', 'schema_version', 'created_at']


class ArtifactDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact
        fields = ['id', 'kind', 'schema_version', 'data', 'file_path', 'created_at']


class JobStatusSerializer(serializers.ModelSerializer):
    project_url = serializers.CharField(source='project.repo_url', read_only=True)
    artifacts = ArtifactSerializer(many=True, read_only=True)
    progress = serializers.IntegerField(help_text='0..100')

    class Meta:
        model = AnalysisRun
        fields = [
            'id', 'project_url', 'commit_sha', 'status', 'progress',
            'error', 'started_at', 'finished_at', 'created_at', 'artifacts'
        ]


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'key', 'title', 'order', 'status', 'text_current', 'summary_current', 'version']


class DocumentSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = ['id', 'type', 'language', 'target_pages', 'status', 'sections', 'created_at']


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'repo_url', 'default_branch', 'created_at']


class DocumentCreateSerializer(serializers.Serializer):
    analysis_run_id = serializers.UUIDField()
    params = serializers.JSONField(required=False, default=dict)
    doc_type = serializers.ChoiceField(choices=['course', 'diploma'], default='course')
    language = serializers.CharField(default='ru-RU')
    target_pages = serializers.IntegerField(default=40)


class DocumentResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'analysis_run', 'type', 'language', 'target_pages', 'params', 'status', 'created_at']


class OutlineResponseSerializer(serializers.Serializer):
    outline = serializers.JSONField(allow_null=True)
    artifact_id = serializers.UUIDField(allow_null=True)


class SectionListSerializer(serializers.ModelSerializer):
    last_artifact_id = serializers.UUIDField(source='last_artifact.id', allow_null=True, read_only=True)

    class Meta:
        model = Section
        fields = ['key', 'title', 'order', 'status', 'version', 'last_artifact_id']


class SectionDetailSerializer(serializers.ModelSerializer):
    last_artifact_id = serializers.UUIDField(source='last_artifact.id', allow_null=True, read_only=True)

    class Meta:
        model = Section
        fields = ['key', 'title', 'order', 'status', 'version', 'text_current', 'summary_current', 'last_artifact_id', 'last_error']


class JobIdResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
