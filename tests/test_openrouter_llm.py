import json

import httpx
import pytest

from agent.core.config import Settings
from agent.integrations.openrouter_llm import OpenRouterClient


def test_openrouter_key_pool_parses_multiple_keys() -> None:
    config = Settings(
        openrouter_api_key="sk-primary",
        openrouter_api_keys="sk-a, sk-b\nsk-c",
    )

    assert config.openrouter_key_pool == ["sk-a", "sk-b", "sk-c", "sk-primary"]


def test_chat_completion_rotates_after_retryable_credit_error() -> None:
    seen_auth_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers.get("Authorization"))
        if len(seen_auth_headers) == 1:
            return httpx.Response(
                402,
                json={"error": {"message": "insufficient credits"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "rotated successfully"}}]
            },
            request=request,
        )

    client = OpenRouterClient(
        api_keys=["sk-first", "sk-second"],
        transport=httpx.MockTransport(handler),
    )

    response = client.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        metadata={"source": "test"},
    )

    assert response["choices"][0]["message"]["content"] == "rotated successfully"
    assert seen_auth_headers == ["Bearer sk-first", "Bearer sk-second"]


def test_chat_completion_raises_on_non_retryable_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "bad request"}},
            request=request,
        )

    client = OpenRouterClient(
        api_keys=["sk-only"],
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.chat_completion(messages=[{"role": "user", "content": "hello"}])


def test_generate_text_returns_first_choice_content() -> None:
    captured_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.read().decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "drafted response",
                        }
                    }
                ]
            },
            request=request,
        )

    client = OpenRouterClient(
        api_keys=["sk-only"],
        transport=httpx.MockTransport(handler),
    )

    text = client.generate_text(
        system_prompt="You are helpful.",
        user_prompt="Draft a follow-up.",
        max_tokens=120,
    )

    assert text == "drafted response"
    assert captured_payloads[0]["messages"][0]["role"] == "system"
    assert captured_payloads[0]["messages"][1]["content"] == "Draft a follow-up."
