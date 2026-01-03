import json
import re
from typing import Any


def _count_cyrillic_ratio(text: str) -> float:
    if not text:
        return 0.0
    cyrillic_pattern = re.compile(r'[\u0400-\u04FF]')
    cyrillic_count = len(cyrillic_pattern.findall(text))
    return cyrillic_count / len(text)


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0

    cyrillic_ratio = _count_cyrillic_ratio(text)

    if cyrillic_ratio > 0.3:
        divisor = 3.5
    else:
        divisor = 4.0

    return int(len(text) / divisor + 0.5)


def estimate_json_tokens(obj: Any) -> int:
    if obj is None:
        return 0
    try:
        text = json.dumps(obj, ensure_ascii=False)
        return estimate_text_tokens(text)
    except (TypeError, ValueError):
        return 0


def estimate_messages_tokens(system: str, user: str) -> int:
    system_tokens = estimate_text_tokens(system)
    user_tokens = estimate_text_tokens(user)
    overhead = 10
    return system_tokens + user_tokens + overhead


class TokenBudgetEstimator:
    def __init__(self, max_input_tokens: int = 4000, max_output_tokens: int = 2000):
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens

    def estimate_text(self, text: str) -> int:
        return estimate_text_tokens(text)

    def estimate_json(self, obj: Any) -> int:
        return estimate_json_tokens(obj)

    def estimate_messages(self, system: str, user: str) -> int:
        return estimate_messages_tokens(system, user)

    def fits_budget(self, text: str, reserved: int = 0) -> bool:
        tokens = self.estimate_text(text)
        return tokens + reserved <= self.max_input_tokens

    def remaining_tokens(self, used: int) -> int:
        return max(0, self.max_input_tokens - used)

    def trim_to_budget(self, text: str, target_tokens: int) -> str:
        if not text:
            return text

        current_tokens = self.estimate_text(text)
        if current_tokens <= target_tokens:
            return text

        cyrillic_ratio = _count_cyrillic_ratio(text)
        divisor = 3.5 if cyrillic_ratio > 0.3 else 4.0

        target_chars = int(target_tokens * divisor)
        if target_chars >= len(text):
            return text

        trimmed = text[:target_chars]
        last_newline = trimmed.rfind('\n')
        if last_newline > target_chars * 0.7:
            trimmed = trimmed[:last_newline]

        return trimmed + "\n[...]"
