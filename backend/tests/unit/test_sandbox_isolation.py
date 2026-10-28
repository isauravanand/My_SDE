from unittest.mock import MagicMock, patch

import pytest

from app.execution.sandbox.base import (
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from app.execution.sandbox.docker import DockerSandbox
from app.execution.sandbox.factory import get_sandbox
from app.execution.sandbox.mock import MockSandbox


def test_docker_sandbox_flag_configuration():
    """Verify Docker container is configured with mandatory Linux security and resource flags."""
    sandbox = DockerSandbox(
        image="python:3.10-slim",
        memory_limit="512m",
        cpu_limit=0.5,
        sandbox_id="test-box-flags",
    )

    with patch("shutil.which", return_value="C:\\Program Files\\Docker\\docker.exe"), \
         patch("app.execution.sandbox.docker.DockerSandbox.is_docker_available", return_value=True), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="container123\n", returncode=0)

        sandbox.create()

        # Verify docker run command arguments
        assert mock_run.called
        run_args = mock_run.call_args[0][0]

        assert "--read-only" in run_args
        assert "--network" in run_args and run_args[run_args.index("--network") + 1] == "none"
        assert "--cap-drop" in run_args and run_args[run_args.index("--cap-drop") + 1] == "ALL"
        assert "--security-opt" in run_args and "no-new-privileges:true" in run_args
        assert "--user" in run_args and run_args[run_args.index("--user") + 1] == "1000:1000"
        assert "--memory=512m" in run_args
        assert "--cpus=0.5" in run_args
        assert "--pids-limit=100" in run_args

        # Verify no docker socket mounted
        for arg in run_args:
            assert "docker.sock" not in arg
            assert "C:\\" not in arg or "mysde_sandboxes" in arg


def test_docker_unavailable_raises_clean_error():
    """When Docker daemon is unavailable, container creation raises SandboxUnavailableError without host execution."""
    sandbox = DockerSandbox()

    with patch("app.execution.sandbox.docker.DockerSandbox.is_docker_available", return_value=False):
        with pytest.raises(SandboxUnavailableError, match="Docker is not available"):
            sandbox.create()


def test_mock_sandbox_lifecycle():
    """Verifies complete isolated lifecycle of MockSandbox."""
    sandbox = MockSandbox()
    sandbox.create()
    assert sandbox.temp_dir is not None
    assert sandbox.temp_dir.exists()

    # 1. Provision working copy
    snapshot = {
        "src/calc.py": b"def calculate():\n    return 10\n",
        "README.md": b"# Test Project\n",
    }
    sandbox.provision_working_copy(snapshot)

    assert (sandbox.temp_dir / "src" / "calc.py").exists()
    assert (sandbox.temp_dir / "src" / "calc.py").read_bytes() == snapshot["src/calc.py"]

    # 2. Apply patch
    patch_diff = """diff --git a/src/calc.py b/src/calc.py
--- a/src/calc.py
+++ b/src/calc.py
@@ -1,2 +1,3 @@
 def calculate():
+    # Updated
     return 20
"""
    ok, msg = sandbox.apply_patch(patch_diff)
    assert ok is True
    assert "Applied" in msg or "applied" in msg.lower()

    # Verify file changed
    content = (sandbox.temp_dir / "src" / "calc.py").read_text()
    assert "Updated" in content

    # 3. Run permitted command
    exit_code, stdout, stderr, duration = sandbox.run_permitted_command("syntax_check")
    assert exit_code == 0
    assert duration >= 0.0

    # 4. Collect diff
    diff_output = sandbox.collect_diff()
    assert "diff --git" in diff_output
    assert "src/calc.py" in diff_output

    # 5. Destroy
    temp_path = sandbox.temp_dir
    cleanup_ok = sandbox.destroy()
    assert cleanup_ok is True
    assert not temp_path.exists()


def test_mock_sandbox_timeout_handling():
    """Verifies command execution timeout raises SandboxTimeoutError."""
    sandbox = MockSandbox(simulate_timeout=True)
    sandbox.create()
    sandbox.provision_working_copy({"src/app.py": b"print('test')\n"})

    with pytest.raises(SandboxTimeoutError, match="timed out"):
        sandbox.run_permitted_command("syntax_check", timeout=5)

    sandbox.destroy()


def test_mock_sandbox_cleanup_failure_reporting():
    """Verifies that cleanup failures are accurately reported as False."""
    sandbox = MockSandbox(simulate_cleanup_failure=True)
    sandbox.create()
    sandbox.provision_working_copy({"file.txt": b"content"})

    cleanup_ok = sandbox.destroy()
    assert cleanup_ok is False


def test_factory_fallback():
    """Verifies factory safely selects provider or falls back when Docker is unavailable."""
    with patch("app.execution.sandbox.docker.DockerSandbox.is_docker_available", return_value=False):
        sb = get_sandbox(provider_override="docker")
        assert isinstance(sb, MockSandbox)

    with patch("app.execution.sandbox.docker.DockerSandbox.is_docker_available", return_value=True):
        sb = get_sandbox(provider_override="docker")
        assert isinstance(sb, DockerSandbox)
