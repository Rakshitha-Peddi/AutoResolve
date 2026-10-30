
"""Compare AutoResolve's configured AI providers."""

import asyncio
import json
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from ai_agent.ai.manager import AIManager
from ai_agent.ai.providers.gemini import GeminiProvider
from ai_agent.ai.providers.groq import GroqProvider
from ai_agent.ai.registry import ProviderRegistry
from ai_agent.ai.schemas import AIMessage, AIRequest


load_dotenv(Path.cwd() / ".env")

PROMPT = """
You are a Python bug-fixing assistant.

Bug: The following function crashes when input is None.

def get_username(user):
    return user["name"]

Required behavior:
- Return "Guest" when user is None.
- Keep existing behavior for valid dictionaries.

Return ONLY the corrected Python function.
Do not include Markdown code fences or explanations.
"""


async def main():
    registry = ProviderRegistry()
    registry.register(GeminiProvider())
    registry.register(GroqProvider())

    manager = AIManager(registry, "gemini")
    results = []

    for provider in ("gemini", "groq"):
        print(f"\nTesting {provider}...")

        request = AIRequest(
            task="bug_fix",
            messages=[
                AIMessage(role="user", content=PROMPT)
            ],
            temperature=0,
            max_tokens=512,
        )

        started = perf_counter()

        try:
            response = await manager.generate(
                request,
                provider_name=provider,
            )

            duration = round(
                perf_counter() - started, 3
            )

            print("Model:", response.model)
            print("Duration:", duration, "seconds")
            print("Response:\n", response.text)

            results.append({
                "provider": provider,
                "model": response.model,
                "success": True,
                "duration_seconds": duration,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "response": response.text,
            })

        except Exception as exc:
            print("Error:", type(exc).__name__, str(exc))

            results.append({
                "provider": provider,
                "success": False,
                "error_type": type(exc).__name__,
            })

    output = Path("benchmarks/results.json")
    output.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )

    print("\nResults saved to:", output)


if __name__ == "__main__":
    asyncio.run(main())
