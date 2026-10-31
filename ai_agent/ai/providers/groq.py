
"""Groq adapter for the AutoResolve AI framework."""

import os

from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncGroq,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

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


class GroqProvider(AIProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL")

        if not self.api_key:
            raise AIConfigurationError(
                "GROQ_API_KEY is not configured."
            )

        if not self.model:
            raise AIConfigurationError(
                "GROQ_MODEL is not configured."
            )

        if timeout <= 0:
            raise AIConfigurationError(
                "Groq timeout must be positive."
            )

        self.timeout = timeout

    @property
    def name(self) -> str:
        return "groq"

    async def generate(self, request: AIRequest) -> AIResponse:
        model = request.model or self.model

        messages = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in request.messages
        ]

        try:
            async with AsyncGroq(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=0,
            ) as client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=request.temperature,
                    max_completion_tokens=request.max_tokens,
                )

        except (AuthenticationError, PermissionDeniedError) as exc:
            raise AIAuthenticationError(
                "Groq credentials or access rejected."
            ) from exc

        except RateLimitError as exc:
            raise AIRateLimitError(
                "Groq rate limit or quota reached."
            ) from exc

        except APITimeoutError as exc:
            raise AITimeoutError(
                "Groq request timed out."
            ) from exc

        except APIConnectionError as exc:
            raise AIProviderError(
                "Cannot connect to Groq."
            ) from exc

        except APIStatusError as exc:
            if exc.status_code in (500, 502, 503):
                raise AITransientError(
                    f"Groq temporarily unavailable (HTTP {exc.status_code})."
                ) from exc
            raise AIProviderError(
                f"Groq API request failed (HTTP {exc.status_code})."
            ) from exc

        if not response.choices:
            raise AIResponseError(
                "Groq returned no response choices."
            )

        content = response.choices[0].message.content

        if not isinstance(content, str) or not content.strip():
            raise AIResponseError(
                "Groq returned an empty text response."
            )

        usage = response.usage

        return AIResponse(
            text=content.strip(),
            provider=self.name,
            model=model,
            success=True,
            input_tokens=(
                usage.prompt_tokens if usage else None
            ),
            output_tokens=(
                usage.completion_tokens if usage else None
            ),
        )

    async def health_check(self) -> bool:
        """Check local configuration without making API calls."""
        return bool(self.api_key and self.model)
