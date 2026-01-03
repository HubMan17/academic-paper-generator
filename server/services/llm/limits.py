from django.conf import settings

from .errors import LLMInputTooLargeError
from .pricing import DEFAULT_MAX_CHARS_TOTAL


def check_input_limits(system: str, user: str) -> None:
    max_chars = getattr(settings, 'LLM_MAX_CHARS_TOTAL', DEFAULT_MAX_CHARS_TOTAL)
    total_chars = len(system) + len(user)

    if total_chars > max_chars:
        raise LLMInputTooLargeError(
            f"Input too large: {total_chars} chars > {max_chars} limit",
            actual=total_chars,
            limit=max_chars
        )
