"""
Request correlation and log formatting.

* `request_id_var` holds the id of the request (or task) being handled by the
  current thread/async context. The middleware sets it for HTTP requests; the
  Celery task sets it from the id it was queued with, so a worker log line can
  be tied back to the API call that caused it.
* `ContextFilter` copies that id (and the Celery task id, if any) onto every
  log record so both formatters can print them.
* `JsonFormatter` emits one JSON object per line for log aggregators; the text
  formatter stays the default for local `make logs` readability.
"""

import json
import logging
import re
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_request_id() -> str:
    return uuid.uuid4().hex


def clean_request_id(raw: str | None) -> str | None:
    """Accept an upstream id only if it is short and printable; otherwise ignore it."""
    if raw and _SAFE_ID.match(raw):
        return raw
    return None


def current_request_id() -> str:
    return request_id_var.get()


def _current_task_id() -> str:
    try:
        from celery import current_task

        request = getattr(current_task, "request", None)
        return getattr(request, "id", None) or "-"
    except Exception:  # celery not loaded in this process
        return "-"


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.task_id = _current_task_id()
        return True


class JsonFormatter(logging.Formatter):
    _SKIP = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "thread", "threadName", "taskName", "request_id", "task_id",
    }  # fmt: skip

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
        }
        # Structured extras passed via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
