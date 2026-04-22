from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any

from langfuse import Langfuse

from app.core.config import settings


class LangfuseClient:
    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
        client: Langfuse | None = None,
    ) -> None:
        self.public_key = public_key if public_key is not None else settings.langfuse_public_key
        self.secret_key = secret_key if secret_key is not None else settings.langfuse_secret_key
        self.host = host if host is not None else settings.langfuse_host
        self.client = client if client is not None else self._build_client()

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def trace(self, name: str, payload: dict[str, Any]) -> str:
        if not self.enabled:
            return ""
        with self.client.start_as_current_observation(
            name=name,
            as_type="span",
            input=payload,
        ):
            trace_id = self.client.get_current_trace_id() or ""
            self.client.flush()
            return trace_id

    @contextmanager
    def trace_workflow(self, name: str, payload: dict[str, Any]):
        if not self.enabled:
            yield {"trace_id": ""}
            return

        with self.client.start_as_current_observation(
            name=name,
            as_type="span",
            input=payload,
        ) as observation:
            yield {"trace_id": observation.trace_id}
        self.client.flush()

    @contextmanager
    def span(self, name: str, input: dict[str, Any], output: dict[str, Any] | None = None):
        if not self.enabled:
            with nullcontext():
                yield
            return

        with self.client.start_as_current_observation(
            name=name,
            as_type="span",
            input=input,
            output=output,
        ) as observation:
            yield observation

    def _build_client(self) -> Langfuse | None:
        if not (self.public_key and self.secret_key):
            return None
        return Langfuse(
            public_key=self.public_key,
            secret_key=self.secret_key,
            host=self.host,
            environment=settings.environment,
        )
