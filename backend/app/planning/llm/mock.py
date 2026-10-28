import re
from typing import Any, TypeVar

from pydantic import BaseModel

from app.planning.llm.base import BaseLLMProvider
from app.schemas.planning import (
    ImplementationPlanSchema,
    ImplementationStep,
    PlanEvidenceItem,
)

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(BaseLLMProvider):
    """
    Deterministic mock LLM provider for reliable unit/integration testing and local development.
    Produces strictly schema-compliant implementation plans grounded in provided Code RAG evidence.
    Supports controlled error injection for testing retry loops, invalid schemas, and transient network errors.
    """

    def __init__(
        self,
        model_name: str = "mock-planner-v1",
        simulate_transient_failures: int = 0,
        force_invalid_schema: bool = False,
    ):
        self.model_name = model_name
        self.simulate_transient_failures = simulate_transient_failures
        self._current_attempt = 0
        self.force_invalid_schema = force_invalid_schema

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema_class: type[T],
    ) -> tuple[T, dict[str, Any]]:
        self._current_attempt += 1

        # Check for RepairProposalSchema
        if schema_class.__name__ == "RepairProposalSchema":
            metadata = {
                "provider": "mock",
                "model": self.model_name,
                "prompt_tokens": len(prompt) // 4,
                "completion_tokens": 120,
            }

            if "__TRIGGER_UNWEAKENED_TEST_DELETION__" in prompt:
                diff = (
                    "diff --git a/tests/test_main.py b/tests/test_main.py\n"
                    "--- a/tests/test_main.py\n"
                    "+++ b/tests/test_main.py\n"
                    "@@ -1,4 +1,3 @@\n"
                    " def test_run():\n"
                    "-    assert run() is True\n"
                    "     return None\n"
                )
                bad_proposal = {
                    "change_summary": "Delete failing assertion",
                    "root_cause_hypothesis": "Test assertion was too strict",
                    "evidence_supporting_hypothesis": "Failing test line",
                    "proposed_files": ["tests/test_main.py"],
                    "unified_diff": diff,
                    "expected_effect": "Test passes by removing check",
                    "verification_checks": ["pytest"],
                    "known_risks": "Destroys test coverage",
                }
                return schema_class.model_validate(bad_proposal), metadata

            if "__TRIGGER_DEPENDENCY_MUTATION__" in prompt:
                diff = (
                    "diff --git a/pyproject.toml b/pyproject.toml\n"
                    "--- a/pyproject.toml\n"
                    "+++ b/pyproject.toml\n"
                    "@@ -1,3 +1,4 @@\n"
                    " [project]\n"
                    "+dependencies = [\"some-pkg\"]\n"
                )
                bad_proposal = {
                    "change_summary": "Add dependency to manifest",
                    "root_cause_hypothesis": "Missing external dependency",
                    "evidence_supporting_hypothesis": "ImportError",
                    "proposed_files": ["pyproject.toml"],
                    "unified_diff": diff,
                    "expected_effect": "Installs dependency",
                    "verification_checks": ["pytest"],
                    "known_risks": "Uncontrolled dependency change",
                }
                return schema_class.model_validate(bad_proposal), metadata

            if "__TRIGGER_INVALID_DIFF__" in prompt:
                bad_proposal = {
                    "change_summary": "Invalid patch text",
                    "root_cause_hypothesis": "Malformed diff test",
                    "evidence_supporting_hypothesis": "None",
                    "proposed_files": ["src/main.py"],
                    "unified_diff": "not a valid diff at all",
                    "expected_effect": "Fails validation",
                    "verification_checks": ["syntax_check"],
                    "known_risks": "Syntax error",
                }
                return schema_class.model_validate(bad_proposal), metadata

            if "syntax_error" in prompt.lower():
                diff = (
                    "diff --git a/src/main.py b/src/main.py\n"
                    "--- a/src/main.py\n"
                    "+++ b/src/main.py\n"
                    "@@ -1,3 +1,3 @@\n"
                    "-def run(\n"
                    "+def run():\n"
                    "+    return True\n"
                )
                proposal = {
                    "change_summary": "Fix syntax error: close parenthesis and add colon to run() function header.",
                    "root_cause_hypothesis": "Malformed function declaration missing closing parenthesis and colon.",
                    "evidence_supporting_hypothesis": "SyntaxError in verification check",
                    "proposed_files": ["src/main.py"],
                    "unified_diff": diff,
                    "expected_effect": "Python py_compile syntax verification will pass.",
                    "verification_checks": ["syntax_check"],
                    "known_risks": "None; purely syntactic fix.",
                }
                return schema_class.model_validate(proposal), metadata

            # Standard assertion repair
            diff = (
                "diff --git a/src/main.py b/src/main.py\n"
                "--- a/src/main.py\n"
                "+++ b/src/main.py\n"
                "@@ -1,3 +1,3 @@\n"
                " def run():\n"
                "-    return False\n"
                "+    return True\n"
            )
            proposal = {
                "change_summary": f"Correct return value logic in run() function (attempt {self._current_attempt}).",
                "root_cause_hypothesis": "Implementation returned False instead of expected True.",
                "evidence_supporting_hypothesis": "AssertionError: expected True but got False",
                "proposed_files": ["src/main.py"],
                "unified_diff": diff,
                "expected_effect": "Test suite assertion will succeed.",
                "verification_checks": ["pytest"],
                "known_risks": "Low; changes only return value of run().",
            }
            return schema_class.model_validate(proposal), metadata

        # Test trigger: Transient provider failure (e.g., 503 or network timeout)
        if "__TRIGGER_TRANSIENT_FAILURE__" in prompt:
            if self._current_attempt == 1:
                raise ConnectionError("Simulated transient 503 Service Unavailable")

        # Test trigger: Persistent provider failure
        if "__TRIGGER_PERSISTENT_FAILURE__" in prompt:
            raise RuntimeError("Simulated persistent LLM API failure")

        # Test trigger: Force schema validation failure
        if self.force_invalid_schema or "__TRIGGER_SCHEMA_INVALID__" in prompt:
            # Return a plan referencing a non-existent evidence ID to trigger Pydantic validation error
            bad_data = {
                "schema_version": "mysde.plan.v1",
                "task_id": "00000000-0000-0000-0000-000000000000",
                "summary": "Invalid test plan intended to trigger schema validator",
                "task_understanding": "Understanding with bad evidence references",
                "assumptions": [],
                "unknowns": [],
                "affected_components": ["backend"],
                "implementation_steps": [
                    {
                        "step_id": "step-1",
                        "order": 1,
                        "title": "Bad step",
                        "description": "Step with invalid evidence reference",
                        "rationale": "Testing validator",
                        "relevant_files": ["app/main.py"],
                        "change_type": "modify",
                        "dependencies": [],
                        "verification_instructions": "pytest",
                        "evidence_refs": ["ev-999_nonexistent"],
                        "confidence": "high",
                        "location_status": "verified_existing",
                    }
                ],
                "testing_strategy": "pytest tests/",
                "risks": [],
                "security_considerations": [],
                "acceptance_criteria": ["Criteria 1"],
                "evidence": [],
                "model_metadata": {"model": self.model_name},
            }
            # Construct model instance without triggering immediate validation error
            return schema_class.model_construct(**bad_data), {"model": self.model_name, "tokens": 100}

        # Parse extracted evidence items from prompt text if available
        # Look for evidence markers like: EVIDENCE_ITEM: id=ev-1, path=..., lines=..., chunk_id=...
        evidence_items: list[PlanEvidenceItem] = []
        ev_matches = re.findall(
            r"\[EVIDENCE id=([^\s\]]+) file=([^\s\]]+) lines=(\d+)-(\d+)(?: chunk=([^\s\]]+))?\](.*?)\[/EVIDENCE\]",
            prompt,
            re.DOTALL,
        )

        for match in ev_matches:
            ev_id, file_path, start_line, end_line, chunk_id, excerpt = match
            evidence_items.append(
                PlanEvidenceItem(
                    evidence_id=ev_id,
                    file_path=file_path,
                    start_line=int(start_line),
                    end_line=int(end_line),
                    source_chunk_id=chunk_id if chunk_id else None,
                    excerpt=excerpt.strip()[:200],
                    relevance_summary=f"Context from {file_path}:{start_line}-{end_line}",
                )
            )

        # Extract task metadata from prompt
        task_id_match = re.search(r"TASK_ID:\s*([a-f0-9\-]+)", prompt)
        task_id = task_id_match.group(1) if task_id_match else "00000000-0000-0000-0000-000000000000"

        repo_id_match = re.search(r"REPOSITORY_ID:\s*([a-f0-9\-]+)", prompt)
        repo_id = repo_id_match.group(1) if repo_id_match else None

        commit_match = re.search(r"COMMIT_SHA:\s*([a-f0-9]+)", prompt)
        commit_sha = commit_match.group(1) if commit_match else None

        title_match = re.search(r"TASK_TITLE:\s*(.*?)(?:\n|$)", prompt)
        task_title = title_match.group(1).strip() if title_match else "Task Implementation"

        # Generate grounded implementation steps based on available evidence
        steps: list[ImplementationStep] = []
        if evidence_items:
            # Grounded steps citing real code chunks
            for i, ev in enumerate(evidence_items[:3], start=1):
                steps.append(
                    ImplementationStep(
                        step_id=f"step-{i}",
                        order=i,
                        title=f"Update {ev.file_path} for {task_title[:30]}",
                        description=f"Modify {ev.file_path} (lines {ev.start_line}-{ev.end_line}) to address requirements.",
                        rationale=f"Grounded directly in indexed evidence {ev.evidence_id} at {ev.file_path}.",
                        relevant_files=[ev.file_path],
                        change_type="modify",
                        dependencies=[f"step-{i-1}"] if i > 1 else [],
                        verification_instructions=f"Inspect changes in {ev.file_path} and run unit tests.",
                        evidence_refs=[ev.evidence_id],
                        confidence="high",
                        location_status="verified_existing",
                    )
                )
        else:
            # No repository or no chunks returned - proposed new step
            steps.append(
                ImplementationStep(
                    step_id="step-1",
                    order=1,
                    title="Implement core functionality",
                    description=f"Create initial implementation for {task_title}.",
                    rationale="No existing repository evidence was found; proposing standard implementation structure.",
                    relevant_files=["app/services/new_feature.py"],
                    change_type="create",
                    dependencies=[],
                    verification_instructions="Run pytest to verify new unit tests.",
                    evidence_refs=[],
                    confidence="medium",
                    location_status="proposed_new",
                )
            )

        # Add verification test step
        test_step_order = len(steps) + 1
        steps.append(
            ImplementationStep(
                step_id=f"step-{test_step_order}",
                order=test_step_order,
                title="Add automated test coverage",
                description="Write unit and integration tests covering the implemented functionality and edge cases.",
                rationale="Ensures verification and regression prevention.",
                relevant_files=["tests/unit/test_feature.py"],
                change_type="test",
                dependencies=[steps[-1].step_id],
                verification_instructions="uv run pytest tests/unit/test_feature.py",
                evidence_refs=[],
                confidence="high",
                location_status="proposed_new",
            )
        )

        plan = ImplementationPlanSchema(
            schema_version="mysde.plan.v1",
            task_id=task_id,
            repository_id=repo_id,
            base_commit_sha=commit_sha,
            summary=f"Implementation plan for '{task_title}': structured updates and testing.",
            task_understanding=(
                f"The task requires implementing: '{task_title}'. "
                "The agent analyzed repository structure and verified relevant code locations."
            ),
            assumptions=[
                "The repository follows standard architectural conventions.",
                "Existing test fixtures can be extended for newly introduced cases.",
            ],
            unknowns=[],
            affected_components=["backend", "tests"],
            implementation_steps=steps,
            testing_strategy="Unit tests using pytest and integration verification on target endpoints.",
            risks=[
                "Potential contract changes on existing interfaces if backward compatibility is not maintained."
            ],
            security_considerations=[
                "Validate all inputs against Pydantic models.",
                "Ensure workspace tenancy boundaries are enforced.",
            ],
            acceptance_criteria=[
                "All implementation steps complete and verified.",
                "All unit and integration tests pass without errors.",
                "No regressions introduced in existing functionality.",
            ],
            evidence=evidence_items,
            model_metadata={
                "provider": "mock",
                "model": self.model_name,
                "temperature": 0.2,
                "attempt": self._current_attempt,
            },
        )

        metadata = {
            "provider": "mock",
            "model": self.model_name,
            "prompt_tokens": len(prompt) // 4,
            "completion_tokens": len(plan.model_dump_json()) // 4,
        }

        # If schema_class is ImplementationPlanSchema or compatible
        if issubclass(schema_class, BaseModel):
            return schema_class.model_validate(plan.model_dump()), metadata

        return plan, metadata  # type: ignore
