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


class LLMTextRequestSerializer(serializers.Serializer):
    system = serializers.CharField(
        required=True,
        help_text="Системный промпт"
    )
    user = serializers.CharField(
        required=True,
        help_text="Пользовательский промпт"
    )
    model = serializers.CharField(
        required=False,
        default=None,
        allow_null=True,
        help_text="Модель (по умолчанию gpt-4o-mini)"
    )
    temperature = serializers.FloatField(
        required=False,
        default=0.7,
        min_value=0,
        max_value=2
    )
    use_cache = serializers.BooleanField(
        required=False,
        default=True
    )


class LLMJsonRequestSerializer(serializers.Serializer):
    system = serializers.CharField(required=True)
    user = serializers.CharField(required=True)
    model = serializers.CharField(required=False, default=None, allow_null=True)
    temperature = serializers.FloatField(required=False, default=0.3)
    use_cache = serializers.BooleanField(required=False, default=True)
    schema = serializers.DictField(required=False, default=None, allow_null=True)


class LLMResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    result = serializers.DictField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
