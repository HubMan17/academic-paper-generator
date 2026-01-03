class LLMError(Exception):
    pass


class LLMConfigError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMProviderError(LLMError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.is_retryable = status_code is None or status_code >= 500


class LLMInputTooLargeError(LLMError):
    def __init__(self, message: str, actual: int, limit: int):
        super().__init__(message)
        self.actual = actual
        self.limit = limit


class LLMInvalidJSONError(LLMError):
    pass


class LLMSchemaValidationError(LLMError):
    pass
