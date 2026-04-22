from app.core.config import settings  # noqa: F401


class LangfuseClient:
    def trace(self, name: str, payload: dict) -> str:
        # TODO: Langfuse(public_key, secret_key, host).trace(name, input=payload)
        return ""

    def span(self, trace_id: str, name: str, input: dict, output: dict | None = None) -> None:
        # TODO: attach span to existing trace
        pass
