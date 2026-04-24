import logging
import logging.config
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.api.routes.bookings import router as booking_router
from agent.api.routes.health import router as health_router
from agent.api.routes.webhooks import router as webhook_router
from agent.core.config import settings

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


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    yield


app = FastAPI(title=settings.app_name, lifespan=_lifespan)
app.include_router(health_router)
app.include_router(booking_router, prefix="/bookings", tags=["bookings"])
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
