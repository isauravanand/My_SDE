import logging

from app.core.config import get_settings
from app.execution.sandbox.base import BaseSandbox
from app.execution.sandbox.docker import DockerSandbox
from app.execution.sandbox.mock import MockSandbox

logger = logging.getLogger(__name__)


def get_sandbox(
    provider_override: str | None = None,
    **kwargs,
) -> BaseSandbox:
    """
    Factory function returning the configured sandbox implementation.
    If 'docker' is configured but Docker daemon is not available, falls back to MockSandbox
    with explicit logging and status annotation to preserve host safety.
    """
    settings = get_settings()
    provider = provider_override or settings.SANDBOX_PROVIDER

    if provider == "docker":
        if DockerSandbox.is_docker_available():
            logger.info("Instantiating DockerSandbox with container isolation")
            return DockerSandbox(**kwargs)
        else:
            logger.warning(
                "SANDBOX_PROVIDER is 'docker', but Docker daemon is not available. "
                "Falling back to MockSandbox to prevent host command execution."
            )
            return MockSandbox(**kwargs)

    return MockSandbox(**kwargs)
