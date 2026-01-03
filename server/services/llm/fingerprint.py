import hashlib
import json
from typing import Any


def normalize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    return {k: v for k, v in sorted(params.items()) if v is not None}


def schema_hash(schema: dict[str, Any] | None) -> str:
    if not schema:
        return ""
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True).encode()
    ).hexdigest()[:16]


def make_fingerprint(
    model: str,
    system: str,
    user: str,
    params: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None
) -> str:
    payload = {
        "model": model,
        "system": system,
        "user": user,
        "params": normalize_params(params),
        "schema_hash": schema_hash(schema),
    }
    content = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()
