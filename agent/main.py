import logging
import logging.config
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from agent.api.routes.bookings import router as booking_router
from agent.api.routes.health import router as health_router
from agent.api.routes.outbound import router as outbound_router
from agent.api.routes.webhooks import router as webhook_router
from agent.core.config import settings
from agent.storage.postgres import postgres_enabled, run_migrations

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\+\d{7,15}")


class _PiiRedactingFilter(logging.Filter):
    """Scrub email addresses and E.164 phone numbers from structured log extra fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in record.__dict__.items():
            if isinstance(value, str) and ("@" in value or value.startswith("+")):
                record.__dict__[key] = _PHONE_RE.sub("[phone]", _EMAIL_RE.sub("[email]", value))
        return True


# Snapshot clean record attrs before any extras are added, used by the formatter.
_KNOWN_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class _DetailFormatter(logging.Formatter):
    """Formats log records and appends any structured extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _KNOWN_RECORD_ATTRS and not k.startswith("_")
        }
        if extras:
            fields = "  ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base}  [{fields}]"
        return base


def _configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "detail": {
                    "()": _DetailFormatter,
                    "format": "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
                    "datefmt": "%H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "detail",
                }
            },
            "loggers": {
                "agent": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
            },
            "root": {"level": "WARNING", "handlers": ["console"]},
        }
    )
    pii_filter = _PiiRedactingFilter()
    for handler in logging.getLogger("agent").handlers:
        handler.addFilter(pii_filter)
    for handler in logging.getLogger().handlers:
        handler.addFilter(pii_filter)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    if postgres_enabled():
        run_migrations()
    yield


app = FastAPI(title=settings.app_name, lifespan=_lifespan)


@app.middleware("http")
async def request_logging(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logging.getLogger("agent.api").exception(
            "request.failed",
            extra={
                "req_id": request_id,
                "req_method": request.method,
                "req_path": request.url.path,
                "req_query": request.url.query,
                "req_elapsed_ms": elapsed_ms,
            },
        )
        raise
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logging.getLogger("agent.api").info(
        "request.complete",
        extra={
            "req_id": request_id,
            "req_method": request.method,
            "req_path": request.url.path,
            "req_query": request.url.query,
            "req_status": response.status_code,
            "req_elapsed_ms": elapsed_ms,
        },
    )
    response.headers["x-request-id"] = request_id
    return response


app.include_router(health_router)
app.include_router(booking_router, prefix="/bookings", tags=["bookings"])
app.include_router(outbound_router, prefix="/outbound", tags=["outbound"])
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
