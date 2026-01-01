import pytest
from services.llm.client import LLMClient


class TestCleanJsonResponse:
    @pytest.fixture
    def client(self, mocker):
        mocker.patch('services.llm.provider_openai.OpenAIProvider.__init__', return_value=None)
        mocker.patch.object(LLMClient, '__init__', lambda self: None)
        c = object.__new__(LLMClient)
        return c

    def test_clean_json(self, client):
        text = '{"name": "test"}'
        result = client._clean_json_response(text)
        assert result == '{"name": "test"}'

    def test_clean_json_with_json_fence(self, client):
        text = '```json\n{"name": "test"}\n```'
        result = client._clean_json_response(text)
        assert result == '{"name": "test"}'

    def test_clean_json_with_plain_fence(self, client):
        text = '```\n{"name": "test"}\n```'
        result = client._clean_json_response(text)
        assert result == '{"name": "test"}'

    def test_clean_json_with_whitespace(self, client):
        text = '  \n{"name": "test"}\n  '
        result = client._clean_json_response(text)
        assert result == '{"name": "test"}'

    def test_clean_multiline_json(self, client):
        text = '```json\n{\n  "name": "test",\n  "value": 123\n}\n```'
        result = client._clean_json_response(text)
        assert '"name": "test"' in result
        assert '"value": 123' in result
