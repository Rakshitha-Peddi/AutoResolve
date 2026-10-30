
"""Gemini adapter for AutoResolve's AI provider framework."""

import os

from google import genai
from google.genai import errors, types

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


class GeminiProvider(AIProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL")

        if not self.api_key:
            raise AIConfigurationError(
                "GEMINI_API_KEY is not configured."
            )

        if not self.model:
            raise AIConfigurationError(
                "GEMINI_MODEL is not configured."
            )

        if timeout <= 0:
            raise AIConfigurationError(
                "Gemini timeout must be positive."
            )

        self.timeout = timeout

    @property
    def name(self) -> str:
        return "gemini"

    async def generate(self, request: AIRequest) -> AIResponse:
        model = request.model or self.model

        contents = "\n\n".join(
            f"{message.role.upper()}:\n{message.content}"
            for message in request.messages
        )

        client = genai.Client(api_key=self.api_key)

        try:
            async with client.aio as async_client:
                response = await async_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=request.temperature,
                        max_output_tokens=request.max_tokens,
                        http_options=types.HttpOptions(
                            timeout=self.timeout * 1000
                        ),
                    ),
                )

        except errors.APIError as exc:
            if exc.code in (401, 403):
                raise AIAuthenticationError(
                    "Gemini credentials or model access rejected."
                ) from exc

            if exc.code == 429:
                raise AIRateLimitError(
                    "Gemini rate limit or quota reached."
                ) from exc

            if exc.code in (408, 504):
                raise AITimeoutError(
                    "Gemini request timed out."
                ) from exc

            if exc.code in (500, 502, 503):
                raise AITransientError(
                    f"Gemini temporarily unavailable (HTTP {exc.code})."
                ) from exc

            raise AIProviderError(
                f"Gemini API request failed (HTTP {exc.code})."
            ) from exc

        except TimeoutError as exc:
            raise AITimeoutError(
                "Gemini request timed out."
            ) from exc

        text = response.text

        if not text or not text.strip():
            raise AIResponseError(
                "Gemini returned an empty text response."
            )

        usage = response.usage_metadata

        return AIResponse(
            text=text.strip(),
            provider=self.name,
            model=model,
            success=True,
            input_tokens=(
                usage.prompt_token_count
                if usage else None
            ),
            output_tokens=(
                usage.candidates_token_count
                if usage else None
            ),
        )

    async def health_check(self) -> bool:
        """Verify local configuration without consuming API quota."""
        return bool(self.api_key and self.model)
