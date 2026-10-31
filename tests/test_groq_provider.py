
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from groq import (
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)

from ai_agent.ai.exceptions import (
    AIAuthenticationError,
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
)
from ai_agent.ai.providers.groq import GroqProvider
from ai_agent.ai.schemas import AIMessage, AIRequest


def make_request():
    return AIRequest(
        task="bug_analysis",
        messages=[
            AIMessage(
                role="user",
                content="Identify a Python bug.",
            )
        ],
    )


def mock_groq_client(response=None, error=None):
    client = MagicMock()

    client.chat.completions.create = AsyncMock(
        return_value=response,
        side_effect=error,
    )

    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    return client


def make_api_error(error_type, status):
    request = httpx.Request(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
    )
    response = httpx.Response(
        status_code=status,
        request=request,
        json={"error": {"message": "Simulated failure"}},
    )

    return error_type(
        "Simulated API failure",
        response=response,
        body=None,
    )


@pytest.mark.asyncio
async def test_groq_success():
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="ZeroDivisionError"
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=20,
            completion_tokens=10,
        ),
    )

    with patch(
        "ai_agent.ai.providers.groq.AsyncGroq",
        return_value=mock_groq_client(fake_response),
    ):
        provider = GroqProvider(
            api_key="test-key",
            model="test-model",
        )

        result = await provider.generate(make_request())

    assert result.text == "ZeroDivisionError"
    assert result.provider == "groq"
    assert result.model == "test-model"
    assert result.input_tokens == 20
    assert result.output_tokens == 10


@pytest.mark.asyncio
async def test_groq_rejects_empty_response():
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="")
            )
        ],
        usage=None,
    )

    with patch(
        "ai_agent.ai.providers.groq.AsyncGroq",
        return_value=mock_groq_client(fake_response),
    ):
        provider = GroqProvider(
            api_key="test-key",
            model="test-model",
        )

        with pytest.raises(AIResponseError):
            await provider.generate(make_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "status", "expected"),
    [
        (AuthenticationError, 401, AIAuthenticationError),
        (RateLimitError, 429, AIRateLimitError),
        (InternalServerError, 503, AIProviderError),
    ],
)
async def test_groq_api_errors(error_type, status, expected):
    error = make_api_error(error_type, status)

    with patch(
        "ai_agent.ai.providers.groq.AsyncGroq",
        return_value=mock_groq_client(error=error),
    ):
        provider = GroqProvider(
            api_key="test-key",
            model="test-model",
        )

        with pytest.raises(expected):
            await provider.generate(make_request())
