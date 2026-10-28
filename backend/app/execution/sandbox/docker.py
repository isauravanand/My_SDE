import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.execution.command_policy import CommandPolicy
from app.execution.sandbox.base import (
    BaseSandbox,
    SandboxError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)

logger = logging.getLogger(__name__)


class DockerSandbox(BaseSandbox):
    """
    Production-grade OS-isolated container sandbox enforced by Docker daemon.

    Security Boundaries Enforced:
    - Dedicated unprivileged user (UID 1000:1000)
    - Read-only container root filesystem (--read-only)
    - Complete network isolation (--network none)
    - All Linux capabilities dropped (--cap-drop ALL)
    - No privilege escalation (--security-opt no-new-privileges:true)
    - Kernel resource limits: memory (e.g. 1024m), cpu quota (1.0), pids limit (100)
    - Host filesystem isolation: Only a dedicated disposable per-run directory is mounted
    - Never mounts host root, home directory, or docker socket
    """

    def __init__(
        self,
        image: str | None = None,
        memory_limit: str | None = None,
        cpu_limit: float | None = None,
        sandbox_id: str | None = None,
    ):
        self.settings = get_settings()
        self.image = image or self.settings.SANDBOX_DOCKER_IMAGE
        self.memory_limit = memory_limit or self.settings.SANDBOX_MEMORY_LIMIT
        self.cpu_limit = cpu_limit or self.settings.SANDBOX_CPU_LIMIT
        self.sandbox_id = sandbox_id or f"mysde-box-{uuid.uuid4().hex[:12]}"

        self.workspace_dir: Path | None = None
        self.container_id: str | None = None
        self._is_destroyed = False

    @staticmethod
    def is_docker_available() -> bool:
        """Checks if Docker CLI executable is installed and responding."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def create(self) -> None:
        """Provisions a isolated container with strict security bounds."""
        if not self.is_docker_available():
            raise SandboxUnavailableError(
                "Docker is not available or daemon is not running on this system. "
                "Container-enforced sandbox execution cannot be initiated."
            )

        # Create temporary workspace folder on host to mount
        temp_base = Path(os.environ.get("TEMP", "/tmp")) / "mysde_sandboxes"
        temp_base.mkdir(parents=True, exist_ok=True)
        self.workspace_dir = temp_base / self.sandbox_id
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Start isolated paused or sleep-loop container
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.sandbox_id,
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "1000:1000",
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpu_limit}",
            "--pids-limit=100",
            "-v",
            f"{self.workspace_dir}:/workspace:rw",
            "-w",
            "/workspace",
            self.image,
            "sleep",
            "3600",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.container_id = result.stdout.strip()
            logger.info(f"Docker sandbox created: id={self.sandbox_id}, container={self.container_id}")
        except subprocess.CalledProcessError as e:
            self.destroy()
            raise SandboxError(f"Failed to create Docker sandbox container: {e.stderr}") from e

    def provision_working_copy(self, files: dict[str, bytes]) -> None:
        """Copies immutable repository snapshot files into the workspace volume."""
        if not self.workspace_dir or not self.workspace_dir.exists():
            raise SandboxError("Sandbox workspace directory does not exist.")

        for rel_path, content in files.items():
            clean_path = Path(rel_path)
            if clean_path.is_absolute() or ".." in clean_path.parts:
                raise SandboxError(f"Illegal relative path in snapshot: '{rel_path}'")

            target_file = self.workspace_dir / clean_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_bytes(content)

        # Initialize disposable git repo inside container for clean diff tracking
        subprocess.run(
            ["docker", "exec", "-u", "1000:1000", self.sandbox_id, "git", "init"],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "exec", "-u", "1000:1000", self.sandbox_id, "git", "config", "user.email", "sandbox@mysde.local"],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "exec", "-u", "1000:1000", self.sandbox_id, "git", "config", "user.name", "MySDE Sandbox"],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "exec", "-u", "1000:1000", self.sandbox_id, "git", "add", "-A"],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "exec", "-u", "1000:1000", self.sandbox_id, "git", "commit", "-m", "base snapshot", "--allow-empty"],
            capture_output=True,
        )

    def apply_patch(self, unified_diff: str) -> tuple[bool, str]:
        """Applies a validated unified diff using git apply inside container."""
        if not self.container_id:
            raise SandboxError("Sandbox is not running.")

        # Pass patch via stdin to docker exec
        cmd = ["docker", "exec", "-i", "-u", "1000:1000", self.sandbox_id, "git", "apply", "--verbose", "-"]
        try:
            res = subprocess.run(
                cmd,
                input=unified_diff,
                text=True,
                capture_output=True,
                timeout=15,
            )
            success = res.returncode == 0
            output = res.stdout if success else (res.stderr or res.stdout)
            return success, output
        except subprocess.TimeoutExpired:
            return False, "Patch application timed out inside container."
        except Exception as e:
            return False, f"Failed to execute git apply in container: {e}"

    def run_permitted_command(
        self,
        command_key: str,
        extra_args: list[str] | None = None,
        timeout: int = 60,
    ) -> tuple[int, str, str, float]:
        """Executes a validated allowlisted verification command."""
        if not self.container_id:
            raise SandboxError("Sandbox is not running.")

        verification_type, safe_argv = CommandPolicy.resolve_and_validate(command_key, extra_args)

        docker_cmd = ["docker", "exec", "-u", "1000:1000", self.sandbox_id] + safe_argv
        start_time = time.time()

        try:
            res = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = round(time.time() - start_time, 3)
            stdout = CommandPolicy.sanitize_and_truncate_output(
                res.stdout,
                max_bytes=self.settings.SANDBOX_MAX_OUTPUT_BYTES,
            )
            stderr = CommandPolicy.sanitize_and_truncate_output(
                res.stderr,
                max_bytes=self.settings.SANDBOX_MAX_OUTPUT_BYTES,
            )
            return res.returncode, stdout, stderr, duration

        except subprocess.TimeoutExpired as e:
            duration = round(time.time() - start_time, 3)
            raise SandboxTimeoutError(f"Command '{command_key}' timed out after {timeout} seconds.") from e
        except Exception as e:
            duration = round(time.time() - start_time, 3)
            return 1, "", f"Execution error: {e}", duration

    def collect_diff(self) -> str:
        """Returns unified diff of changes against base snapshot commit."""
        if not self.container_id:
            return ""

        res = subprocess.run(
            ["docker", "exec", "-u", "1000:1000", self.sandbox_id, "git", "diff", "HEAD"],
            capture_output=True,
            text=True,
        )
        return res.stdout if res.returncode == 0 else ""

    def destroy(self) -> bool:
        """Terminates container and deletes mounted workspace directory."""
        if self._is_destroyed:
            return True

        success = True
        if self.container_id or self.sandbox_id:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self.sandbox_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Error removing docker container {self.sandbox_id}: {e}")
                success = False

        if self.workspace_dir and self.workspace_dir.exists():
            try:
                shutil.rmtree(self.workspace_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error deleting workspace dir {self.workspace_dir}: {e}")
                success = False

        self._is_destroyed = True
        return success
