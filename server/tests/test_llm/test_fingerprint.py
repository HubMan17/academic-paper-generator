import pytest
from services.llm.fingerprint import normalize_params, make_fingerprint, schema_hash


class TestNormalizeParams:
    def test_removes_none_values(self):
        params = {"a": 1, "b": None, "c": "test"}
        result = normalize_params(params)
        assert "b" not in result
        assert result == {"a": 1, "c": "test"}

    def test_sorts_keys(self):
        params = {"z": 1, "a": 2, "m": 3}
        result = normalize_params(params)
        keys = list(result.keys())
        assert keys == ["a", "m", "z"]

    def test_empty_dict(self):
        assert normalize_params({}) == {}

    def test_none_input(self):
        assert normalize_params(None) == {}


class TestSchemaHash:
    def test_returns_empty_for_none(self):
        assert schema_hash(None) == ""

    def test_returns_16_chars(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        result = schema_hash(schema)
        assert len(result) == 16

    def test_deterministic(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        assert schema_hash(schema) == schema_hash(schema)

    def test_different_schemas_different_hash(self):
        schema1 = {"type": "object"}
        schema2 = {"type": "array"}
        assert schema_hash(schema1) != schema_hash(schema2)


class TestMakeFingerprint:
    def test_deterministic(self):
        fp1 = make_fingerprint("gpt-4", "sys", "user", {"temp": 0.7})
        fp2 = make_fingerprint("gpt-4", "sys", "user", {"temp": 0.7})
        assert fp1 == fp2

    def test_different_params_different_fingerprint(self):
        fp1 = make_fingerprint("gpt-4", "sys", "user", {"temp": 0.7})
        fp2 = make_fingerprint("gpt-4", "sys", "user", {"temp": 0.5})
        assert fp1 != fp2

    def test_different_model_different_fingerprint(self):
        fp1 = make_fingerprint("gpt-4", "sys", "user")
        fp2 = make_fingerprint("gpt-3.5", "sys", "user")
        assert fp1 != fp2

    def test_schema_affects_fingerprint(self):
        schema1 = {"type": "object"}
        schema2 = {"type": "array"}
        fp1 = make_fingerprint("gpt-4", "sys", "user", schema=schema1)
        fp2 = make_fingerprint("gpt-4", "sys", "user", schema=schema2)
        assert fp1 != fp2

    def test_special_chars_in_content(self):
        fp1 = make_fingerprint("gpt-4", "sys:with:colons", "user\nwith\nnewlines")
        fp2 = make_fingerprint("gpt-4", "sys:with:colons", "user\nwith\nnewlines")
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_returns_64_char_hex(self):
        fp = make_fingerprint("gpt-4", "sys", "user")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)
