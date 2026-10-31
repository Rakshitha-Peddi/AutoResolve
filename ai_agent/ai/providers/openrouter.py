
"""OpenRouter adapter for AutoResolve."""

import os

import httpx

from ai_agent.ai.base import AIProvider
from ai_agent.ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
    AITransientError,
)
from ai_agent.ai.schemas import AIRequest, AIResponse


class OpenRouterProvider(AIProvider):
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

        if not self.api_key:
            raise AIConfigurationError("OPENROUTER_API_KEY is missing.")

        # Restrict this integration to free models.
        if self.model != "openrouter/free" and not self.model.endswith(":free"):
            raise AIConfigurationError("Select an OpenRouter free model.")

    @property
    def name(self) -> str:
        return "openrouter"

    async def generate(self, request: AIRequest) -> AIResponse:
        model = request.model or self.model

        if model != "openrouter/free" and not model.endswith(":free"):
            raise AIConfigurationError("Paid OpenRouter models are disabled.")

        payload = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AITimeoutError("OpenRouter request timed out.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError("OpenRouter connection failed.") from exc

        if response.status_code in (401, 403):
            raise AIAuthenticationError("OpenRouter access denied.")
        if response.status_code == 429:
            raise AIRateLimitError("OpenRouter request limit reached.")
        if response.status_code in (500, 502, 503, 504):
            raise AITransientError("OpenRouter temporarily unavailable.")
        if response.status_code >= 400:
            raise AIProviderError(
                f"OpenRouter HTTP error: {response.status_code}"
            )

        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content")

        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIResponseError(
                "OpenRouter returned an unexpected response structure."
            ) from exc

        if not isinstance(content, str) or not content.strip():
            usage = data.get("usage") or {}
            details = usage.get("completion_tokens_details") or {}

            raise AIResponseError(
                "OpenRouter returned empty content. "
                f"Model: {data.get('model', 'unknown')}; "
                f"Finish reason: {choice.get('finish_reason', 'unknown')}; "
                f"Output tokens: {usage.get('completion_tokens', 'unknown')}; "
                f"Reasoning tokens: {details.get('reasoning_tokens', 'unknown')}."
            )

        usage = data.get("usage") or {}

        return AIResponse(
            text=content.strip(),
            provider=self.name,
            model=model,
            success=True,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    async def health_check(self) -> bool:
        return bool(self.api_key)