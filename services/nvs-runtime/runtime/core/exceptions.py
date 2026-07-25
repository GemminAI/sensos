class RuntimeErrorBase(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(RuntimeErrorBase):
    pass


class NotFoundError(RuntimeErrorBase):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=404)


class ConflictError(RuntimeErrorBase):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=409)


class AnnotationValidationError(RuntimeErrorBase):
    """Semantic Annotator rejected our request (HTTP 422) - e.g. empty text."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=422)


class AnnotationUnavailableError(RuntimeErrorBase):
    """Semantic Annotator is unreachable, or reports it cannot serve a
    request right now (HTTP 503, e.g. its backend has no API key)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=503)


class AnnotationBackendError(RuntimeErrorBase):
    """Semantic Annotator's own backend failed (HTTP 502), or its response
    did not match the AnnotationResult contract Runtime expects (Fail Fast -
    see runtime/services/semantic_annotator_client.py)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=502)
