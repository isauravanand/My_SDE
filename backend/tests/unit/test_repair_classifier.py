import uuid

from app.execution.repair.classifier import FailureClassifier
from app.models.execution import VerificationResult


def make_verification_result(
    cmd: str = "pytest",
    exit_code: int = 1,
    status: str = "failed",
    stderr: str = "",
    stdout: str = "",
    vtype: str = "test",
) -> VerificationResult:
    return VerificationResult(
        id=uuid.uuid4(),
        execution_run_id=uuid.uuid4(),
        verification_type=vtype,
        command_name=cmd,
        command_args=[cmd],
        exit_code=exit_code,
        status=status,
        duration_seconds=1.2,
        stdout_excerpt=stdout,
        stderr_excerpt=stderr,
    )


def test_classify_assertion_failure():
    res = make_verification_result(
        cmd="pytest",
        exit_code=1,
        status="failed",
        stderr="FAILED tests/test_service.py::test_cache - AssertionError: expected True but got False",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "test_assertion_failure"
    assert classification.is_repairable is True
    assert "assertion" in classification.reason.lower()


def test_classify_syntax_error():
    res = make_verification_result(
        cmd="syntax_check",
        exit_code=1,
        status="failed",
        stderr="File 'app/service.py', line 12\n    def run(\n           ^\nSyntaxError: was never closed",
        vtype="syntax",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "syntax_error"
    assert classification.is_repairable is True
    assert "SyntaxError" in classification.reason or "syntactic" in classification.reason.lower()


def test_classify_lint_failure():
    res = make_verification_result(
        cmd="ruff_check",
        exit_code=1,
        status="failed",
        stderr="app/main.py:10:5: F841 Local variable `x` is assigned to but never used\nFound 1 error.",
        vtype="lint",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "lint_failure"
    assert classification.is_repairable is True


def test_classify_timeout_non_repairable():
    res = make_verification_result(
        cmd="pytest",
        exit_code=124,
        status="timed_out",
        stderr="Sandbox execution exceeded timeout of 60 seconds",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "timeout"
    assert classification.is_repairable is False
    assert "timed out" in classification.reason.lower()


def test_classify_resource_limit_non_repairable():
    res = make_verification_result(
        cmd="pytest",
        exit_code=137,
        status="failed",
        stderr="Process killed: MemoryError / OOMKilled by cgroup memory controller",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "resource_limit_exceeded"
    assert classification.is_repairable is False


def test_classify_network_denied_non_repairable():
    res = make_verification_result(
        cmd="pytest",
        exit_code=1,
        status="failed",
        stderr="urllib.error.URLError: <urlopen error [Errno 101] Network is unreachable>",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "network_denied"
    assert classification.is_repairable is False


def test_classify_sandbox_failure_non_repairable():
    classification = FailureClassifier.classify(
        [],
        sandbox_error="Docker daemon unavailable or container failed to start: permission denied on cgroup",
    )
    assert classification.category == "sandbox_failure"
    assert classification.is_repairable is False


def test_classify_missing_dependency_non_repairable():
    res = make_verification_result(
        cmd="pytest",
        exit_code=1,
        status="failed",
        stderr="ModuleNotFoundError: No module named 'cryptography'",
    )
    classification = FailureClassifier.classify([res])
    assert classification.category == "import_or_dependency_error"
    assert classification.is_repairable is False
    assert "prohibited" in classification.reason.lower() or "missing module" in classification.reason.lower()


def test_classify_secret_redaction_in_evidence():
    res = make_verification_result(
        cmd="pytest",
        exit_code=1,
        status="failed",
        stderr="AssertionError with token ghp_123456789012345678901234567890123456 and password='SuperSecretPassword123!'",
    )
    classification = FailureClassifier.classify([res])
    assert "ghp_" not in classification.evidence_excerpt
    assert "[REDACTED_GITHUB_TOKEN]" in classification.evidence_excerpt
    assert "SuperSecretPassword123!" not in classification.evidence_excerpt


def test_classify_all_passed():
    res = make_verification_result(cmd="pytest", exit_code=0, status="passed")
    classification = FailureClassifier.classify([res])
    assert classification.is_repairable is False
    assert classification.category == "unknown"
