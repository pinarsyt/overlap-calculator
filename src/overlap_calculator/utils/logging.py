from __future__ import annotations

import contextvars
import json
import logging
from datetime import UTC, datetime

from overlap_calculator.exceptions import InputError
from overlap_calculator.utils.errors import ErrorCode, format_error

VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


def normalize_log_level(level: str) -> str:
    normalized = level.upper()
    if normalized not in VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(VALID_LOG_LEVELS))
        raise InputError(
            format_error(ErrorCode.INPUT, f"Invalid log level: {level}. Allowed: {allowed}")
        )
    return normalized


def format_log(action: str, entity: str, **context: object) -> str:
    base = f"action={action} entity={entity}"
    if not context:
        return base
    parts = [f"{key}={value}" for key, value in context.items()]
    return f"{base} " + " ".join(parts)


request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(request_id: str | None) -> None:
    request_id_var.set(request_id)


def get_request_id() -> str | None:
    return request_id_var.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", None)
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id:
            payload["request_id"] = request_id
        return json.dumps(payload, ensure_ascii=True)


def setup_logging(level: str = "INFO", log_format: str = "text") -> None:
    normalized = normalize_log_level(level)
    if log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(RequestIdFilter())
        logging.basicConfig(level=getattr(logging, normalized, logging.INFO), handlers=[handler])
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        handler.addFilter(RequestIdFilter())
        logging.basicConfig(level=getattr(logging, normalized, logging.INFO), handlers=[handler])
    logging.getLogger("overlap_calculator").info(
        format_log("logging", "configured", level=normalized, format=log_format)
    )

