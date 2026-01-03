DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_S = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_CHARS_TOTAL = 100_000
DEFAULT_LOCK_POLL_INTERVAL = 0.5

MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}
