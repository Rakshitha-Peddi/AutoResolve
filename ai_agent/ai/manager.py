
"""Central AI manager with provider fallback and cooldown tracking."""
import asyncio
from time import perf_counter

from .exceptions import (
    AIConfigurationError,
    AINoProviderError,
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
    AITransientError,
)
from .model_router import ModelRouter
from .prompt_safety import validate_outbound_prompt
from .provider_health import ProviderHealthTracker
from .registry import ProviderRegistry
from .schemas import AIRequest, AIResponse
from .sqlite_usage_tracker import SQLiteUsageTracker
from .usage_tracker import AIUsageLimitError, AIUsageTracker


class AIManager:
    def __init__(
        self,
        registry: ProviderRegistry,
        default_provider: str,
        fallback_enabled: bool = False,
        fallback_providers: tuple[str, ...] = (),
        health_tracker: ProviderHealthTracker | None = None,
        model_router: ModelRouter | None = None,
        request_timeout: float = 60,
        max_retries: int = 0,
        usage_tracker: AIUsageTracker | SQLiteUsageTracker | None = None,
    ):
        self.registry = registry
        self.usage_tracker = usage_tracker
        self.model_router = model_router
        self.default_provider = default_provider.strip().lower()
        self.fallback_enabled = fallback_enabled
        self.fallback_providers = fallback_providers
        self.health_tracker = (
            health_tracker
            if health_tracker is not None
            else ProviderHealthTracker()
        )
        if request_timeout <= 0:
            raise AIConfigurationError(
                "Request timeout must be positive."
            )

        if not 0 <= max_retries <= 2:
            raise AIConfigurationError(
                "Maximum retries must be between 0 and 2."
            )

        self.request_timeout = request_timeout
        self.max_retries = max_retries

        if not self.default_provider:
            raise AIConfigurationError(
                "Default AI provider cannot be empty."
            )

    async def _generate_with_provider(
        self,
        provider_name: str,
        request: AIRequest,
    ) -> AIResponse:
        provider = self.registry.get(provider_name)
        if self.usage_tracker is not None:
            self.usage_tracker.reserve_request(provider_name)

        started = perf_counter()
        try:
            response = await asyncio.wait_for(
                provider.generate(request),
                timeout=self.request_timeout,
            )
        except TimeoutError as exc:
            raise AITimeoutError(
                f"AI provider '{provider.name}' exceeded "
                f"{self.request_timeout} seconds."
            ) from exc
        elapsed = perf_counter() - started

        if not response.success or not response.text.strip():
            raise AIResponseError(
                f"AI provider '{provider.name}' returned an invalid response."
            )

        if response.duration_seconds is None:
            response = response.model_copy(
                update={"duration_seconds": elapsed}
            )

        return response

    async def generate(
        self,
        request: AIRequest,
        provider_name: str | None = None,
    ) -> AIResponse:
        # Validate every message before provider selection, quota
        # reservation, network requests, retries, or fallback.
        for message in request.messages:
            validate_outbound_prompt(message.content)

        if provider_name:
            primary = provider_name.strip().lower()
        elif self.model_router is not None:
            primary = self.model_router.route(request.task)
        else:
            primary = self.default_provider


        # Reject explicitly selected providers that are not enabled.
        if (
            self.model_router is not None
            and primary not in self.model_router.enabled_providers
        ):
            raise AIConfigurationError(
                f"AI provider '{primary}' is not enabled."
            )


        candidates = [primary]


        if self.fallback_enabled:
            if self.model_router is not None:
                backups = tuple(
                    name
                    for name in self.model_router.enabled_providers
                    if name != primary
                )
            else:
                backups = self.fallback_providers


            for name in backups:
                name = name.strip().lower()

                if name and name not in candidates:
                    candidates.append(name)

        # Validate registrations before attempting requests.
        for name in candidates:
            self.registry.get(name)


        last_error = None

        for name in candidates:
            if not self.health_tracker.is_available(name):
                continue

            try:
                for attempt in range(self.max_retries + 1):
                    try:
                        response = await self._generate_with_provider(
                            name, request
                        )

                        self.health_tracker.record_success(name)
                        return response

                    except AITransientError:
                        if attempt >= self.max_retries:
                            raise

                        await asyncio.sleep(
                            min(2 ** attempt, 4)
                        )

            except AIUsageLimitError as exc:
                # A configured budget is exhausted.
                # Do not put the provider in a network-failure cooldown.
                last_error = exc

                if not self.fallback_enabled:
                    raise

            except (
                AIRateLimitError,
                AITimeoutError,
                AIProviderError,
            ) as exc:
                last_error = exc
                self.health_tracker.record_failure(name)

                if not self.fallback_enabled:
                    raise

        raise AINoProviderError(
            "All eligible AI providers are unavailable "
            "or have exhausted their request budgets."
        ) from last_error


    def available_providers(self) -> list[str]:
        return self.registry.list_providers()
