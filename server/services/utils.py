import hashlib
import json


def compute_content_hash(data) -> str:
    if data is None:
        return ''
    if isinstance(data, str):
        raw = data
    else:
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
