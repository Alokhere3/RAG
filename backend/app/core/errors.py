"""Centralized Error Handling.

Conforms to Section 20 & 21:
- Consistent structured error schema:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Description",
            "request_id": "req-123"
        }
    }
- Masks internal exception traces from public responses.
- Integrates with structured logging and request ID context.
"""

from typing import Any
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import logger, request_id_ctx


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "APPLICATION_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class ConfigurationError(AppException):
    """Raised on invalid configuration."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ServiceUnavailableError(AppException):
    """Raised when an infrastructure dependency fails."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class AuthenticationError(AppException):
    """Raised on authentication failure or invalid/expired credentials."""

    def __init__(self, message: str = "Invalid email or password.", code: str = "INVALID_CREDENTIALS"):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthorizationError(AppException):
    """Raised on permission denial or role mismatch."""

    def __init__(self, message: str = "Permission denied.", code: str = "FORBIDDEN"):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class NotFoundError(AppException):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str = "Resource not found.", code: str = "NOT_FOUND"):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class BadRequestError(AppException):
    """Raised when a request is malformed, invalid, or violates operational policy."""

    def __init__(self, message: str = "Bad request.", code: str = "BAD_REQUEST", details: Any = None):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class PayloadTooLargeError(AppException):
    """Raised when an uploaded payload exceeds the maximum permitted size."""

    def __init__(
        self,
        message: str = "Payload exceeds maximum allowed size.",
        code: str = "PAYLOAD_TOO_LARGE",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )


class FileValidationError(AppException):
    """Raised when an uploaded file violates formatting, extension, or content-integrity rules."""

    def __init__(self, message: str, code: str = "INVALID_FILE"):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ParserError(AppException):
    """Base exception for document parsing failures."""

    def __init__(
        self,
        message: str,
        code: str = "PARSER_ERROR",
        status_code: int = 422,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
        )


class CorruptFileError(ParserError):
    """Raised when a file archive or structure is corrupt or unreadable."""

    def __init__(self, message: str = "File is corrupt or cannot be read."):
        super().__init__(
            message=message,
            code="CORRUPT_FILE",
            status_code=422,
        )


class UnsupportedFormatError(ParserError):
    """Raised when attempting to parse an unsupported format."""

    def __init__(self, message: str = "File format is not supported for extraction."):
        super().__init__(
            message=message,
            code="UNSUPPORTED_FORMAT",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


class OcrRequiredError(ParserError):
    """Raised when a document (such as a scanned PDF) requires OCR that is not currently enabled."""

    def __init__(self, message: str = "Document contains scanned images requiring OCR extraction."):
        super().__init__(
            message=message,
            code="OCR_REQUIRED",
            status_code=422,
        )


class ParserTimeoutError(ParserError):
    """Raised when parser execution exceeds the maximum allowed time."""

    def __init__(self, message: str = "Document parsing timed out."):
        super().__init__(
            message=message,
            code="PARSER_TIMEOUT",
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
        )


class EmbeddingError(AppException):
    """Base exception for embedding provider and vectorization failures."""

    def __init__(
        self,
        message: str,
        code: str = "EMBEDDING_ERROR",
        status_code: int = status.HTTP_502_BAD_GATEWAY,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
        )


class MissingProviderKeyError(EmbeddingError):
    """Raised when an embedding provider requires an API key that is missing or empty."""

    def __init__(self, message: str = "Embedding provider API key is not configured."):
        super().__init__(
            message=message,
            code="MISSING_PROVIDER_KEY",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class DimensionMismatchError(EmbeddingError):
    """Raised when generated embedding vectors do not match configured index dimensions."""

    def __init__(self, message: str = "Embedding vector dimensions do not match the index schema."):
        super().__init__(
            message=message,
            code="DIMENSION_MISMATCH",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ProviderTimeoutError(EmbeddingError):
    """Raised when an embedding provider call times out."""

    def __init__(self, message: str = "Embedding provider request timed out."):
        super().__init__(
            message=message,
            code="PROVIDER_TIMEOUT",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class ProviderRateLimitError(EmbeddingError):
    """Raised when an embedding provider rejects requests due to rate limits."""

    def __init__(self, message: str = "Embedding provider rate limit exceeded. Retry later."):
        super().__init__(
            message=message,
            code="PROVIDER_RATE_LIMITED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class IncompatibleModelError(EmbeddingError):
    """Raised when attempting to mix incompatible embedding models or vectors in an index."""

    def __init__(self, message: str = "Embedding model is incompatible with the existing vector index."):
        super().__init__(
            message=message,
            code="INCOMPATIBLE_MODEL",
            status_code=status.HTTP_409_CONFLICT,
        )


class LlmError(AppException):
    """Base exception for LLM provider and generation failures."""

    def __init__(
        self,
        message: str,
        code: str = "LLM_ERROR",
        status_code: int = status.HTTP_502_BAD_GATEWAY,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
        )


class MissingLlmKeyError(LlmError):
    """Raised when an LLM provider requires an API key that is missing or unset."""

    def __init__(self, message: str = "LLM provider API key is not configured."):
        super().__init__(
            message=message,
            code="MISSING_LLM_KEY",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class LlmTimeoutError(LlmError):
    """Raised when an LLM provider call times out."""

    def __init__(self, message: str = "LLM provider request timed out."):
        super().__init__(
            message=message,
            code="LLM_TIMEOUT",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class LlmRateLimitError(LlmError):
    """Raised when an LLM provider rejects requests due to rate limits."""

    def __init__(self, message: str = "LLM provider rate limit exceeded. Retry later."):
        super().__init__(
            message=message,
            code="LLM_RATE_LIMITED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class MalformedLlmOutputError(LlmError):
    """Raised when an LLM provider returns invalid, empty, or unparseable output."""

    def __init__(self, message: str = "LLM provider returned malformed or unparseable output."):
        super().__init__(
            message=message,
            code="MALFORMED_LLM_OUTPUT",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class ContextBudgetExceededError(LlmError):
    """Raised when prompt content exceeds maximum permitted token/context budget."""

    def __init__(self, message: str = "Prompt content exceeds maximum permitted token/context budget."):
        super().__init__(
            message=message,
            code="CONTEXT_BUDGET_EXCEEDED",
            status_code=status.HTTP_400_BAD_REQUEST,
        )



def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    """Build canonical JSON error payload."""
    req_id = request_id_ctx.get()
    error_payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": req_id,
    }
    if details:
        error_payload["details"] = details

    return JSONResponse(
        status_code=status_code,
        content={"error": error_payload},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.error(
            f"AppException [{exc.code}] on {request.method} {request.url.path}: {exc.message}",
            extra={"request_id": request_id_ctx.get()},
        )
        return build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            f"Validation error on {request.method} {request.url.path}: {exc.errors()}",
            extra={"request_id": request_id_ctx.get()},
        )
        # Transform errors to safe dict
        sanitized_errors = [
            {"loc": err["loc"], "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="Request input validation failed.",
            details=sanitized_errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        logger.warning(
            f"HTTPException [{exc.status_code}] on {request.method} {request.url.path}: {exc.detail}",
            extra={"request_id": request_id_ctx.get()},
        )
        return build_error_response(
            status_code=exc.status_code,
            code="HTTP_ERROR",
            message=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}",
            extra={"request_id": request_id_ctx.get()},
        )
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
        )
