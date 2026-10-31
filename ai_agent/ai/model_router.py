
"""Task-based provider routing for AutoResolve."""

from .exceptions import AIConfigurationError

DEFAULT_TASK_ROUTES = {
    "bug_analysis": "gemini",
    "root_cause_analysis": "gemini",
    "bug_fix": "groq",
    "test_generation": "groq",
    "error_explanation": "gemini",
    "patch_review": "gemini",
}


class ModelRouter:
    """Select an allowed AI provider for each task."""

    def __init__(
        self,
        enabled_providers: tuple[str, ...],
        default_provider: str = "gemini",
        task_routes: dict[str, str] | None = None,
    ):
        self.enabled_providers = tuple(
            dict.fromkeys(
                name.strip().lower()
                for name in enabled_providers
                if name.strip()
            )
        )

        self.default_provider = default_provider.strip().lower()

        if not self.enabled_providers:
            raise AIConfigurationError(
                "At least one provider must be enabled."
            )

        if self.default_provider not in self.enabled_providers:
            raise AIConfigurationError(
                "Default provider is not enabled."
            )

        configured_routes = (
            DEFAULT_TASK_ROUTES
            if task_routes is None
            else task_routes
        )

        self.task_routes = {
            task: provider.strip().lower()
            for task, provider in configured_routes.items()
        }

    def route(self, task: str) -> str:
        """Return the provider selected for an AI task."""

        preferred = self.task_routes.get(
            task,
            self.default_provider,
        )

        if preferred not in self.enabled_providers:
            return self.default_provider

        return preferred

    def fallback_order(self, task: str) -> tuple[str, ...]:
        """Return eligible backup providers, excluding primary."""

        primary = self.route(task)

        return tuple(
            provider
            for provider in self.enabled_providers
            if provider != primary
        )
