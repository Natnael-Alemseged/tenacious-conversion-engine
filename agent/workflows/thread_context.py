from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.storage.conversations import ConversationStore


@dataclass(frozen=True)
class ThreadContext:
    thread_id: str
    messages: list[dict[str, Any]]
    state: dict[str, Any] | None


def load_thread_context(
    *, store: ConversationStore, thread_id: str, limit: int = 10
) -> ThreadContext:
    messages = store.fetch_recent_messages(thread_id=thread_id, limit=limit)
    state = store.fetch_state(thread_id=thread_id)
    return ThreadContext(thread_id=thread_id, messages=messages, state=state)
