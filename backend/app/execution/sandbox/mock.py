import logging
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.execution.command_policy import CommandPolicy
from app.execution.sandbox.base import (
    BaseSandbox,
    SandboxError,
    SandboxTimeoutError,
)

logger = logging.getLogger(__name__)


class MockSandbox(BaseSandbox):
    """
    Simulated isolated sandbox for offline testing, CI, and environments without Docker.
    Enforces directory boundaries, command allowlists, timeouts, and output limits.
    """

    def __init__(
        self,
        sandbox_id: str | None = None,
        simulate_timeout: bool = False,
        simulate_failure_command: str | None = None,
        simulate_cleanup_failure: bool = False,
    ):
        self.settings = get_settings()
        self.sandbox_id = sandbox_id or f"mock-box-{uuid.uuid4().hex[:12]}"
        self.simulate_timeout = simulate_timeout
        self.simulate_failure_command = simulate_failure_command
        self.simulate_cleanup_failure = simulate_cleanup_failure

        self.temp_dir: Path | None = None
        self._initial_files: dict[str, bytes] = {}
        self._current_files: dict[str, str] = {}
        self._is_destroyed = False

    def create(self) -> None:
        """Creates an isolated temporary directory."""
        raw_temp = tempfile.mkdtemp(prefix=f"{self.sandbox_id}_")
        self.temp_dir = Path(raw_temp)
        logger.info(f"MockSandbox created at {self.temp_dir}")

    def provision_working_copy(self, files: dict[str, bytes]) -> None:
        """Populates the sandbox with initial files."""
        if not self.temp_dir or not self.temp_dir.exists():
            raise SandboxError("Sandbox temporary directory does not exist.")

        self._initial_files = dict(files)
        self._current_files = {}

        for rel_path, content in files.items():
            clean_path = Path(rel_path)
            if clean_path.is_absolute() or ".." in clean_path.parts:
                raise SandboxError(f"Illegal path traversal in snapshot file: '{rel_path}'")

            target = self.temp_dir / clean_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            try:
                self._current_files[rel_path] = content.decode("utf-8")
            except UnicodeDecodeError:
                self._current_files[rel_path] = ""

    def apply_patch(self, unified_diff: str) -> tuple[bool, str]:
        """Applies unified diff patch to the isolated working copy."""
        if not self.temp_dir or not self.temp_dir.exists():
            raise SandboxError("Sandbox is not running.")

        if not unified_diff.strip():
            return False, "Cannot apply empty diff."

        # Parse sections
        try:
            # First check if git is available locally to apply
            git_bin = shutil.which("git")
            if git_bin and (self.temp_dir / ".git").exists():
                res = subprocess.run(
                    ["git", "apply", "--verbose", "-"],
                    input=unified_diff,
                    text=True,
                    cwd=str(self.temp_dir),
                    capture_output=True,
                    timeout=10,
                )
                if res.returncode == 0:
                    return True, res.stdout or "Patch applied successfully."

            # Pure Python fallback patch application
            applied_count = 0
            lines = unified_diff.splitlines()
            current_target = None
            hunk_added_lines = []

            for line in lines:
                if line.startswith("+++ b/"):
                    current_target = line[6:].strip()
                elif line.startswith("+") and not line.startswith("+++"):
                    hunk_added_lines.append(line[1:])

            if current_target:
                target_file = self.temp_dir / Path(current_target)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                new_content = "\n".join(hunk_added_lines) + "\n"
                target_file.write_text(new_content, encoding="utf-8")
                self._current_files[current_target] = new_content
                applied_count += 1

            return True, f"Patch applied to {applied_count} file(s) successfully."

        except Exception as e:
            logger.error(f"Failed to apply patch in MockSandbox: {e}")
            return False, f"Failed to apply patch: {e}"

    def run_permitted_command(
        self,
        command_key: str,
        extra_args: list[str] | None = None,
        timeout: int = 60,
    ) -> tuple[int, str, str, float]:
        """Runs a permitted command against allowlist policy."""
        if not self.temp_dir or not self.temp_dir.exists():
            raise SandboxError("Sandbox is not running.")

        # Validate against policy
        verification_type, safe_argv = CommandPolicy.resolve_and_validate(command_key, extra_args)

        if self.simulate_timeout:
            raise SandboxTimeoutError(f"Command '{command_key}' timed out after {timeout} seconds.")

        if self.simulate_failure_command == command_key:
            return (
                1,
                CommandPolicy.sanitize_and_truncate_output("Test run failed: 1 error encountered"),
                CommandPolicy.sanitize_and_truncate_output("AssertionError: condition not met"),
                0.25,
            )

        start_time = time.time()
        # If running real syntax check or python command
        if command_key == "syntax_check":
            py_files = list(self.temp_dir.glob("**/*.py"))
            if py_files:
                res = subprocess.run(
                    ["python", "-m", "py_compile"] + [str(f) for f in py_files[:10]],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                duration = round(time.time() - start_time, 3)
                return (
                    res.returncode,
                    CommandPolicy.sanitize_and_truncate_output(res.stdout),
                    CommandPolicy.sanitize_and_truncate_output(res.stderr),
                    duration,
                )

        # Deterministic simulation for mock sandbox
        duration = round(time.time() - start_time, 3) or 0.05
        stdout_sim = f"=== Mock {command_key} output ===\nAll checks passed successfully.\nTotal items checked: {len(self._current_files)}"
        return (
            0,
            CommandPolicy.sanitize_and_truncate_output(stdout_sim),
            "",
            duration,
        )

    def collect_diff(self) -> str:
        """Returns unified diff of changed files."""
        if not self.temp_dir or not self.temp_dir.exists():
            return ""

        diff_lines = []
        for path_str, current_text in self._current_files.items():
            orig_bytes = self._initial_files.get(path_str, b"")
            orig_text = orig_bytes.decode("utf-8", errors="replace")
            if current_text != orig_text:
                diff_lines.append(f"diff --git a/{path_str} b/{path_str}")
                diff_lines.append(f"--- a/{path_str}")
                diff_lines.append(f"+++ b/{path_str}")
                diff_lines.append("@@ -1,1 +1,2 @@")
                diff_lines.append(f"-{orig_text[:50]}")
                diff_lines.append(f"+{current_text[:50]}")

        return "\n".join(diff_lines)

    def destroy(self) -> bool:
        """Cleans up the temporary directory."""
        if self._is_destroyed:
            return True

        if self.simulate_cleanup_failure:
            logger.warning("Simulated cleanup failure in MockSandbox")
            return False

        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error removing mock sandbox temp dir: {e}")
                return False

        self._is_destroyed = True
        return True
