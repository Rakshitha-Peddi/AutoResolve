
class AIError(Exception):
    """Base exception for AI operations."""


class AIConfigurationError(AIError):
    """Invalid or missing AI configuration."""


class AIAuthenticationError(AIError):
    """API credentials are missing or rejected."""


class AIRateLimitError(AIError):
    """Provider rate or quota limit reached."""


class AIProviderError(AIError):
    """Provider failed to process the request."""


class AITimeoutError(AIProviderError):
    """Provider request timed out."""


class AIResponseError(AIError):
    """Provider returned an invalid response."""


class AINoProviderError(AIError):
    """No eligible AI provider is registered."""

class AITransientError(AIProviderError):
    """Temporary provider failure that may be retried."""