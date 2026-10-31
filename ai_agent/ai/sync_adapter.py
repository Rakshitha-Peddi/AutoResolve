
"""Synchronous adapter for AutoResolve's asynchronous AI manager."""

import asyncio

from .manager import AIManager
from .schemas import AIMessage, AIRequest


class SyncAIAdapter:
    """Expose task-based AI generation to synchronous workers."""

    def __init__(self, manager: AIManager):
        self.manager = manager

    async def agenerate_text(
        self,
        prompt: str,
        task: str,
        max_tokens: int = 2048,
    ) -> str:
        request = AIRequest(
            task=task,
            messages=[
                AIMessage(
                    role="user",
                    content=prompt,
                )
            ],
            temperature=0,
            max_tokens=max_tokens,
        )

        response = await self.manager.generate(request)
        return response.text

    def generate_text(
        self,
        prompt: str,
        task: str,
        max_tokens: int = 2048,
    ) -> str:
        """Call from synchronous code, not an active event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.agenerate_text(
                    prompt=prompt,
                    task=task,
                    max_tokens=max_tokens,
                )
            )

        raise RuntimeError(
            "SyncAIAdapter cannot run inside an active event loop. "
            "Use agenerate_text() or run the synchronous workflow "
            "in a worker thread."
        )
