
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors

from ai_agent.ai.exceptions import (
    AIAuthenticationError,
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
)
from ai_agent.ai.providers.gemini import GeminiProvider
from ai_agent.ai.schemas import AIMessage, AIRequest


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(
                role="user",
                content="Identify a Python bug."
            )
        ],
    )


def mock_gemini_client(response=None, error=None):
    """Simulate the Google SDK without network access."""
    client = MagicMock()

    async_client = MagicMock()
    async_client.models.generate_content = AsyncMock(
        return_value=response,
        side_effect=error,
    )

    client.aio.__aenter__ = AsyncMock(
        return_value=async_client
    )
    client.aio.__aexit__ = AsyncMock(
        return_value=None
    )

    return client


@pytest.mark.asyncio
async def test_gemini_success():
    fake_response = SimpleNamespace(
        text="ZeroDivisionError",
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=5,
        ),
    )

    fake_client = mock_gemini_client(fake_response)

    with patch(
        "ai_agent.ai.providers.gemini.genai.Client",
        return_value=fake_client,
    ):
        provider = GeminiProvider(
            api_key="test-key",
            model="test-model",
        )

        result = await provider.generate(make_request())

    assert result.text == "ZeroDivisionError"
    assert result.provider == "gemini"
    assert result.model == "test-model"
    assert result.input_tokens == 12
    assert result.output_tokens == 5


@pytest.mark.asyncio
async def test_gemini_rejects_empty_response():
    fake_response = SimpleNamespace(
        text="",
        usage_metadata=None,
    )

    with patch(
        "ai_agent.ai.providers.gemini.genai.Client",
        return_value=mock_gemini_client(fake_response),
    ):
        provider = GeminiProvider(
            api_key="test-key",
            model="test-model",
        )

        with pytest.raises(AIResponseError):
            await provider.generate(make_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (401, AIAuthenticationError),
        (429, AIRateLimitError),
        (503, AIProviderError),
    ],
)
async def test_gemini_api_errors(status, expected_error):
    api_error = errors.ClientError(
        status,
        {"error": {"message": "Simulated API failure"}},
    ) if status < 500 else errors.ServerError(
        status,
        {"error": {"message": "Simulated API failure"}},
    )

    with patch(
        "ai_agent.ai.providers.gemini.genai.Client",
        return_value=mock_gemini_client(error=api_error),
    ):
        provider = GeminiProvider(
            api_key="test-key",
            model="test-model",
        )

        with pytest.raises(expected_error):
            await provider.generate(make_request())
