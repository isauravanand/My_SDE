import re
import uuid

from app.execution.command_policy import CommandPolicy
from app.models.execution import VerificationResult
from app.schemas.repair import FailureClassification

# Heuristic patterns for failure classification
SYNTAX_ERROR_PATTERNS = [
    re.compile(r"SyntaxError:\s*(.*)", re.IGNORECASE),
    re.compile(r"IndentationError:\s*(.*)", re.IGNORECASE),
    re.compile(r"TabError:\s*(.*)", re.IGNORECASE),
    re.compile(r"py_compile failed", re.IGNORECASE),
]

ASSERTION_PATTERNS = [
    re.compile(r"AssertionError(?::\s*(.*))?", re.IGNORECASE),
    re.compile(r"FAILED\s+tests/.*?::\w+\s+-\s+assert", re.IGNORECASE),
    re.compile(r"assert\s+.*?(?:==|!=|in|<|>)", re.IGNORECASE),
    re.compile(r"Expected\s+.*?,\s+received", re.IGNORECASE),
    re.compile(r"expect\(.*?\)\.", re.IGNORECASE),
]

LINT_PATTERNS = [
    re.compile(r"\b[EFW]\d{3,4}\b.*?(?:error|violation)", re.IGNORECASE),
    re.compile(r"Found \d+ errors? \(\d+ fixed", re.IGNORECASE),
    re.compile(r"ruff check failed", re.IGNORECASE),
    re.compile(r"eslint: error", re.IGNORECASE),
]

TYPE_PATTERNS = [
    re.compile(r"mypy: error", re.IGNORECASE),
    re.compile(r"Incompatible types in assignment", re.IGNORECASE),
    re.compile(r"Argument \d+ to .*? has incompatible type", re.IGNORECASE),
    re.compile(r"TypeError:\s*(.*)", re.IGNORECASE),
]

IMPORT_PATTERNS = [
    re.compile(r"ModuleNotFoundError:\s*No module named\s*['\"](.*?)['\"]", re.IGNORECASE),
    re.compile(r"ImportError:\s*(.*)", re.IGNORECASE),
    re.compile(r"cannot import name\s*['\"](.*?)['\"]", re.IGNORECASE),
]

TIMEOUT_PATTERNS = [
    re.compile(r"timed out", re.IGNORECASE),
    re.compile(r"Sandbox execution exceeded timeout", re.IGNORECASE),
]

RESOURCE_PATTERNS = [
    re.compile(r"OOMKilled|Out of memory|MemoryError", re.IGNORECASE),
    re.compile(r"pids limit exceeded", re.IGNORECASE),
    re.compile(r"disk quota exceeded", re.IGNORECASE),
]

NETWORK_PATTERNS = [
    re.compile(r"network is unreachable", re.IGNORECASE),
    re.compile(r"connection refused", re.IGNORECASE),
    re.compile(r"failed to establish a new connection", re.IGNORECASE),
    re.compile(r"temporary failure in name resolution", re.IGNORECASE),
]

SANDBOX_PATTERNS = [
    re.compile(r"sandbox container|docker daemon|container failed to start", re.IGNORECASE),
    re.compile(r"permission denied.*?entrypoint", re.IGNORECASE),
]


class FailureClassifier:
    """Classifies verification failures into repairable and non-repairable categories."""

    @classmethod
    def classify(
        cls,
        verification_results: list[VerificationResult],
        sandbox_error: str | None = None,
    ) -> FailureClassification:
        """
        Analyzes verification results and sandbox error messages to produce a deterministic classification.
        """
        # 1. Check for infrastructure or sandbox error first
        if sandbox_error:
            sanitized_err = CommandPolicy.sanitize_and_truncate_output(sandbox_error, max_bytes=1024)
            if any(p.search(sandbox_error) for p in TIMEOUT_PATTERNS):
                return FailureClassification(
                    category="timeout",
                    verification_result_ids=[],
                    evidence_excerpt=sanitized_err[:500],
                    is_repairable=False,
                    reason="Execution timed out. Infrastructure and timeout limits cannot be bypassed by code mutation.",
                    uncertainty_annotation="deterministic_timeout_indicator",
                )
            if any(p.search(sandbox_error) for p in RESOURCE_PATTERNS):
                return FailureClassification(
                    category="resource_limit_exceeded",
                    verification_result_ids=[],
                    evidence_excerpt=sanitized_err[:500],
                    is_repairable=False,
                    reason="Sandbox resource limits exceeded. Hardware allocations cannot be modified by code repairs.",
                    uncertainty_annotation="deterministic_resource_limit",
                )
            return FailureClassification(
                category="sandbox_failure",
                verification_result_ids=[],
                evidence_excerpt=sanitized_err[:500],
                is_repairable=False,
                reason="Sandbox execution infrastructure failure. Container runtime issues are not code-repairable.",
                uncertainty_annotation="deterministic_sandbox_fault",
            )

        if not verification_results:
            return FailureClassification(
                category="unknown",
                verification_result_ids=[],
                evidence_excerpt="No verification results recorded.",
                is_repairable=False,
                reason="No check evidence available to classify.",
                uncertainty_annotation="insufficient_evidence",
            )

        # Find failing or timed out results
        failed_results = [r for r in verification_results if r.status in {"failed", "timed_out", "error"}]
        if not failed_results:
            return FailureClassification(
                category="unknown",
                verification_result_ids=[r.id for r in verification_results],
                evidence_excerpt="All verification checks passed.",
                is_repairable=False,
                reason="No failed checks found to repair.",
                uncertainty_annotation="checks_passed",
            )

        result_ids: list[uuid.UUID] = [r.id for r in failed_results]

        # Aggregate stderr and stdout
        combined_logs: list[str] = []
        for r in failed_results:
            if r.stderr_excerpt:
                combined_logs.append(r.stderr_excerpt)
            if r.stdout_excerpt:
                combined_logs.append(r.stdout_excerpt)

        raw_evidence = "\n".join(combined_logs)
        sanitized_evidence = CommandPolicy.sanitize_and_truncate_output(raw_evidence, max_bytes=4096)

        # 2. Check for explicit timeout status
        if any(r.status == "timed_out" for r in failed_results) or any(p.search(raw_evidence) for p in TIMEOUT_PATTERNS):
            return FailureClassification(
                category="timeout",
                verification_result_ids=result_ids,
                evidence_excerpt=sanitized_evidence[:500],
                is_repairable=False,
                reason="Verification check timed out. Timed out commands cannot be repaired by code modifications.",
                uncertainty_annotation="command_timeout_confirmed",
            )

        # 3. Check for resource exhaustion
        if any(p.search(raw_evidence) for p in RESOURCE_PATTERNS):
            return FailureClassification(
                category="resource_limit_exceeded",
                verification_result_ids=result_ids,
                evidence_excerpt=sanitized_evidence[:500],
                is_repairable=False,
                reason="Container memory or CPU limits exceeded. Infrastructure resources cannot be tuned by automated repair.",
                uncertainty_annotation="resource_exhaustion_detected",
            )

        # 4. Check for network access denial
        if any(p.search(raw_evidence) for p in NETWORK_PATTERNS):
            return FailureClassification(
                category="network_denied",
                verification_result_ids=result_ids,
                evidence_excerpt=sanitized_evidence[:500],
                is_repairable=False,
                reason="Network request rejected by sandbox security policy. Network isolation must not be bypassed.",
                uncertainty_annotation="network_isolation_enforced",
            )

        # 5. Check for syntax error
        for pattern in SYNTAX_ERROR_PATTERNS:
            match = pattern.search(raw_evidence)
            if match:
                return FailureClassification(
                    category="syntax_error",
                    verification_result_ids=result_ids,
                    evidence_excerpt=sanitized_evidence[:500],
                    is_repairable=True,
                    reason=f"Syntactic error detected in working copy: {match.group(0)[:200]}.",
                    uncertainty_annotation="high_confidence_syntax_diagnostic",
                )

        # 6. Check for import or dependency error
        for pattern in IMPORT_PATTERNS:
            match = pattern.search(raw_evidence)
            if match:
                missing_pkg = match.group(1) if match.groups() else "unknown"
                return FailureClassification(
                    category="import_or_dependency_error",
                    verification_result_ids=result_ids,
                    evidence_excerpt=sanitized_evidence[:500],
                    is_repairable=False,
                    reason=f"Missing module or dependency '{missing_pkg}'. Adding or updating package dependencies is prohibited during repair.",
                    uncertainty_annotation="dependency_resolution_denied",
                )

        # 7. Check for lint failure
        for pattern in LINT_PATTERNS:
            match = pattern.search(raw_evidence)
            if match:
                return FailureClassification(
                    category="lint_failure",
                    verification_result_ids=result_ids,
                    evidence_excerpt=sanitized_evidence[:500],
                    is_repairable=True,
                    reason="Style, formatting, or linter diagnostic violation in modified code.",
                    uncertainty_annotation="linter_rule_diagnostic",
                )

        # 8. Check for type or static analysis failure
        for pattern in TYPE_PATTERNS:
            match = pattern.search(raw_evidence)
            if match:
                return FailureClassification(
                    category="type_or_static_analysis_error",
                    verification_result_ids=result_ids,
                    evidence_excerpt=sanitized_evidence[:500],
                    is_repairable=True,
                    reason="Static type checking failure in modified code.",
                    uncertainty_annotation="typecheck_diagnostic",
                )

        # 9. Check for test assertion failure
        for pattern in ASSERTION_PATTERNS:
            match = pattern.search(raw_evidence)
            if match:
                return FailureClassification(
                    category="test_assertion_failure",
                    verification_result_ids=result_ids,
                    evidence_excerpt=sanitized_evidence[:500],
                    is_repairable=True,
                    reason="Deterministic test assertion failed during verification.",
                    uncertainty_annotation="assertion_failure_diagnostic",
                )

        # If any check had verification_type == 'syntax' and failed
        if any(r.verification_type == "syntax" for r in failed_results):
            return FailureClassification(
                category="syntax_error",
                verification_result_ids=result_ids,
                evidence_excerpt=sanitized_evidence[:500],
                is_repairable=True,
                reason="Syntax check failed during compilation.",
                uncertainty_annotation="syntax_compiler_exit_code",
            )

        # If any check had verification_type == 'lint' and failed
        if any(r.verification_type == "lint" for r in failed_results):
            return FailureClassification(
                category="lint_failure",
                verification_result_ids=result_ids,
                evidence_excerpt=sanitized_evidence[:500],
                is_repairable=True,
                reason="Linter check exited with non-zero status.",
                uncertainty_annotation="linter_exit_code",
            )

        # Fallback for general test failures
        if any(r.verification_type == "test" for r in failed_results):
            return FailureClassification(
                category="test_assertion_failure",
                verification_result_ids=result_ids,
                evidence_excerpt=sanitized_evidence[:500],
                is_repairable=True,
                reason="Automated test suite reported failure.",
                uncertainty_annotation="test_runner_non_zero_exit",
            )

        return FailureClassification(
            category="unknown",
            verification_result_ids=result_ids,
            evidence_excerpt=sanitized_evidence[:500],
            is_repairable=False,
            reason="Unrecognized check failure pattern.",
            uncertainty_annotation="unclassified_exit_code",
        )
