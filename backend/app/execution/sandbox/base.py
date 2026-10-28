from abc import ABC, abstractmethod


class SandboxError(Exception):
    """Base exception for sandbox lifecycle and execution failures."""

    pass


class SandboxUnavailableError(SandboxError):
    """Raised when the requested sandbox runtime (e.g. Docker daemon) is not available."""

    pass


class SandboxTimeoutError(SandboxError):
    """Raised when command execution exceeds the maximum allocated timeout."""

    pass


class BaseSandbox(ABC):
    """Abstract interface defining isolated sandbox capabilities and lifecycle."""

    @abstractmethod
    def create(self) -> None:
        """Provisions the sandbox environment with strict resource and security constraints."""
        pass

    @abstractmethod
    def provision_working_copy(self, files: dict[str, bytes]) -> None:
        """
        Populates the isolated sandbox workspace with repository files from the immutable snapshot.
        Files are provided as relative paths to raw bytes.
        """
        pass

    @abstractmethod
    def apply_patch(self, unified_diff: str) -> tuple[bool, str]:
        """
        Applies a validated unified diff patch to the sandbox working copy.
        Returns (success: bool, output_or_error_message: str).
        """
        pass

    @abstractmethod
    def run_permitted_command(
        self,
        command_key: str,
        extra_args: list[str] | None = None,
        timeout: int = 60,
    ) -> tuple[int, str, str, float]:
        """
        Executes a validated allowlisted verification command inside the sandbox.
        Returns (exit_code: int, stdout: str, stderr: str, duration_seconds: float).
        """
        pass

    @abstractmethod
    def collect_diff(self) -> str:
        """
        Computes and returns the unified diff of changes made to the sandbox working copy
        relative to the initial base snapshot.
        """
        pass

    @abstractmethod
    def destroy(self) -> bool:
        """
        Destroys the sandbox environment, terminates any lingering processes,
        and completely purges all temporary files.
        Returns True if cleanup succeeded, False otherwise.
        """
        pass
