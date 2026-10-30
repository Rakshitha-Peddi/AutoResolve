
from typing import Literal

from pydantic import BaseModel, Field


class AIMessage(BaseModel):
    """A single message sent to an AI provider."""

    role: Literal["system", "user", "assistant"]
    content: str


class AIRequest(BaseModel):
    """Provider-independent AI request."""

    task: str
    messages: list[AIMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2048, gt=0)


class AIResponse(BaseModel):
    """Standardized response from any AI provider."""

    text: str
    provider: str
    model: str
    success: bool = True
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_seconds: float | None = None
