import pytest

from app.execution.repair.classifier import FailureClassification
from app.execution.repair.generator import RepairGenerator, RepairPolicyViolation
from app.planning.llm.mock import MockLLMProvider
from app.schemas.repair import RepairProposalSchema


def test_reject_test_deletion_policy():
    diff = (
        "diff --git a/tests/test_service.py b/tests/test_service.py\n"
        "deleted file mode 100644\n"
        "--- a/tests/test_service.py\n"
        "+++ /dev/null\n"
        "@@ -1,5 +0,0 @@\n"
        "-def test_run():\n"
        "-    assert False\n"
    )
    proposal = RepairProposalSchema(
        change_summary="Delete failing test to pass build",
        root_cause_hypothesis="Test was failing",
        evidence_supporting_hypothesis="None",
        proposed_files=["tests/test_service.py"],
        unified_diff=diff,
        expected_effect="Test passes",
        verification_checks=["pytest"],
        known_risks="High",
    )
    with pytest.raises(RepairPolicyViolation, match="Deleting test file"):
        RepairGenerator._enforce_repair_policies(proposal)


def test_reject_weakening_test_assertions_policy():
    diff = (
        "diff --git a/tests/test_feature.py b/tests/test_feature.py\n"
        "--- a/tests/test_feature.py\n"
        "+++ b/tests/test_feature.py\n"
        "@@ -1,4 +1,3 @@\n"
        " def test_feature():\n"
        "-    assert feature() == 42\n"
        "     return True\n"
    )
    proposal = RepairProposalSchema(
        change_summary="Remove assertion from test",
        root_cause_hypothesis="Assertion was strict",
        evidence_supporting_hypothesis="AssertionError",
        proposed_files=["tests/test_feature.py"],
        unified_diff=diff,
        expected_effect="Green build",
        verification_checks=["pytest"],
        known_risks="Loss of test coverage",
    )
    with pytest.raises(RepairPolicyViolation, match="Weakening or removing test assertions"):
        RepairGenerator._enforce_repair_policies(proposal)


def test_reject_dependency_manifest_mutation():
    diff = (
        "diff --git a/pyproject.toml b/pyproject.toml\n"
        "--- a/pyproject.toml\n"
        "+++ b/pyproject.toml\n"
        "@@ -1,3 +1,4 @@\n"
        " [project]\n"
        "+dependencies = [\"pytest\"]\n"
    )
    proposal = RepairProposalSchema(
        change_summary="Add dependency",
        root_cause_hypothesis="Missing package",
        evidence_supporting_hypothesis="ImportError",
        proposed_files=["pyproject.toml"],
        unified_diff=diff,
        expected_effect="Dependencies installed",
        verification_checks=["pytest"],
        known_risks="Alters lockfile",
    )
    with pytest.raises(RepairPolicyViolation, match="Modifying dependency manifest"):
        RepairGenerator._enforce_repair_policies(proposal)


@pytest.mark.asyncio
async def test_generate_proposal_syntax_repair():
    mock_llm = MockLLMProvider()
    generator = RepairGenerator(llm_provider=mock_llm)

    classification = FailureClassification(
        category="syntax_error",
        verification_result_ids=[],
        evidence_excerpt="SyntaxError on line 1",
        is_repairable=True,
        reason="SyntaxError in python file",
    )

    prop, val = await generator.generate_proposal(
        task_title="Fix syntax defect",
        task_description="Repair invalid function declaration",
        plan_summary="Syntactic fix",
        current_patch="",
        classification=classification,
        attempt_number=1,
        max_attempts=3,
    )

    assert val.is_valid is True
    assert "def run():" in prop.unified_diff
    assert prop.proposed_files == ["src/main.py"]


@pytest.mark.asyncio
async def test_generate_proposal_assertion_repair():
    mock_llm = MockLLMProvider()
    generator = RepairGenerator(llm_provider=mock_llm)

    classification = FailureClassification(
        category="test_assertion_failure",
        verification_result_ids=[],
        evidence_excerpt="AssertionError: expected True but got False",
        is_repairable=True,
        reason="Logic error in run() function",
    )

    prop, val = await generator.generate_proposal(
        task_title="Fix logic defect",
        task_description="Repair boolean return in run()",
        plan_summary="Logic fix",
        current_patch="",
        classification=classification,
        attempt_number=1,
        max_attempts=3,
    )

    assert val.is_valid is True
    assert "+    return True" in prop.unified_diff
    assert prop.proposed_files == ["src/main.py"]


@pytest.mark.asyncio
async def test_generate_proposal_anti_cheating_trigger_rejected():
    mock_llm = MockLLMProvider()
    generator = RepairGenerator(llm_provider=mock_llm)

    classification = FailureClassification(
        category="test_assertion_failure",
        verification_result_ids=[],
        evidence_excerpt="Trigger test: __TRIGGER_UNWEAKENED_TEST_DELETION__",
        is_repairable=True,
        reason="Testing rejection of assertion deletion",
    )

    with pytest.raises(RepairPolicyViolation, match="Weakening or removing test assertions"):
        await generator.generate_proposal(
            task_title="Test assertion deletion rejection",
            task_description="Simulated attack deleting assertion",
            plan_summary="Fix",
            current_patch="",
            classification=classification,
            attempt_number=1,
            max_attempts=3,
        )
