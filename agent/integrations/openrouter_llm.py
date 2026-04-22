from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from agent.core.config import settings

RETRYABLE_STATUS_CODES = {402, 429, 500, 502, 503, 504}


class OpenRouterClient:
    def __init__(
        self,
        api_keys: Sequence[str] | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_keys = list(api_keys) if api_keys is not None else settings.openrouter_key_pool
        self.base_url = (base_url if base_url is not None else settings.openrouter_base_url).rstrip(
            "/"
        )
        self.default_model = default_model if default_model is not None else settings.llm_model
        self._next_key_index = 0
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self.api_keys:
            raise RuntimeError(
                "OpenRouter is not configured. Set OPENROUTER_API_KEY or OPENROUTER_API_KEYS."
            )

        last_error: Exception | None = None
        start_index = self._next_key_index

        for offset in range(len(self.api_keys)):
            key_index = (start_index + offset) % len(self.api_keys)
            api_key = self.api_keys[key_index]
            try:
                payload: dict[str, Any] = {
                    "model": model or self.default_model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    payload["max_tokens"] = max_tokens
                if metadata:
                    payload["metadata"] = metadata

                response = self.client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = httpx.HTTPStatusError(
                        f"Retryable OpenRouter status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    continue
                response.raise_for_status()
                self._next_key_index = (key_index + 1) % len(self.api_keys)
                return response.json()
            except httpx.RequestError as exc:
                last_error = exc
                continue
            except httpx.HTTPStatusError as exc:
                last_error = exc
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenRouter request failed without a captured exception.")

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        response = self.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
        )
        return response["choices"][0]["message"]["content"]
