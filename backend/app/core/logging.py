"""Structured Logging System.

Conforms to Section 19 of Phase 0:
- Outputs timestamp, level, service, message, and request_id.
- ContextVar-driven request_id propagation.
- Masks sensitive data (passwords, tokens, authorization headers).
"""

from contextvars import ContextVar
import datetime
import json
import logging
import re
import sys
from typing import Any

# Context variable for request tracing
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# Sensitive patterns to sanitize
SENSITIVE_PATTERNS = [
    re.compile(r"(bearer\s+)[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"('?(?:api_key|password|jwt_secret|secret)'?\s*[:=]\s*'?[^',}\s]+'?)", re.IGNORECASE),
]


def sanitize_message(msg: str) -> str:
    """Mask credentials and secrets in log messages."""
    for pattern in SENSITIVE_PATTERNS:
        msg = pattern.sub(r"[REDACTED]", msg)
    return msg


class StructuredJsonFormatter(logging.Formatter):
    """Custom JSON formatter producing structured log entries."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        current_req_id = request_id_ctx.get() or getattr(record, "request_id", "")
        message = sanitize_message(record.getMessage())

        log_data: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "service": "backend",
            "message": message,
            "request_id": current_req_id,
            "logger": record.name,
        }

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_data["exception"] = sanitize_message(record.exc_text)

        return json.dumps(log_data)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root and application loggers."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(StructuredJsonFormatter())

    # Quiet overly chatty libraries in production/tests
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger = logging.getLogger("rag.backend")
    logger.setLevel(log_level)
    return logger


logger = setup_logging()
