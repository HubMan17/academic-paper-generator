from rest_framework import serializers


class AnalyzeRequestSerializer(serializers.Serializer):
    repo_url = serializers.URLField(
        required=True,
        help_text="URL репозитория для анализа (GitHub, GitLab, Bitbucket)"
    )


class AnalyzeResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    facts = serializers.DictField()
    error = serializers.CharField(required=False, allow_null=True)
