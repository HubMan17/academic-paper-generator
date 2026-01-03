import random
import time

BACKOFF_BASE = 0.5
BACKOFF_CAP = 8.0
JITTER_MIN = 0.8
JITTER_MAX = 1.2


def calculate_backoff(attempt: int) -> float:
    delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
    jitter = random.uniform(JITTER_MIN, JITTER_MAX)
    return delay * jitter


def sleep_with_backoff(attempt: int) -> None:
    time.sleep(calculate_backoff(attempt))
