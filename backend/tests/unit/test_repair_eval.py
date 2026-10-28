import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.execution.repair.graph.workflow import build_repair_graph
from app.execution.sandbox.mock import MockSandbox
from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.project import Project
from app.models.repair import RepairRun
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership


@pytest.fixture
def eval_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def setup_eval_env(db):
    user = User(
        id=uuid.uuid4(),
        email="eval@example.com",
        hashed_password="mockhash",
        full_name="Eval Engineer",
    )
    workspace = Workspace(id=uuid.uuid4(), name="Eval Workspace", slug="eval-ws", owner_id=user.id)
    membership = WorkspaceMembership(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    project = Project(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        name="Eval Project",
        slug="eval-proj",
    )
    task = Task(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        project_id=project.id,
        title="Eval Bug Task",
        description="Fix failing logic",
        status="in_progress",
    )
    db.add_all([user, workspace, membership, project, task])
    db.commit()
    return user, workspace, task


def create_eval_run(db, user, workspace, task, err_type="assertion", exit_code=1):
    exec_run = ExecutionRun(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        task_id=task.id,
        plan_id=uuid.uuid4(),
        requested_by_user_id=user.id,
        base_commit_sha="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
        status="failed",
        started_at=datetime.now(timezone.utc),
    )
    db.add(exec_run)

    patch = PatchArtifact(
        id=uuid.uuid4(),
        execution_run_id=exec_run.id,
        patch_hash="patchhash123",
        validation_status="applied",
        raw_diff="diff --git a/src/main.py b/src/main.py\n--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,3 @@\n-def run():\n+def run():\n     return False\n",
        changed_files_count=1,
    )
    db.add(patch)

    if err_type == "syntax":
        stderr = "File 'src/main.py', line 1\n    def run(\n           ^\nSyntaxError: was never closed"
        vtype = "syntax"
        cmd = "syntax_check"
    elif err_type == "timeout":
        stderr = "Sandbox execution exceeded timeout of 60 seconds"
        vtype = "test"
        cmd = "pytest"
        exit_code = 124
    else:
        stderr = "FAILED tests/test_main.py::test_run - AssertionError: assert False is True"
        vtype = "test"
        cmd = "pytest"

    v_res = VerificationResult(
        id=uuid.uuid4(),
        execution_run_id=exec_run.id,
        verification_type=vtype,
        command_name=cmd,
        command_args=[cmd],
        exit_code=exit_code,
        status="timed_out" if exit_code == 124 else "failed",
        duration_seconds=1.0,
        stderr_excerpt=stderr,
    )
    db.add(v_res)
    db.commit()
    return exec_run


def test_eval_case_1_assertion_repair_success(eval_db):
    user, ws, task = setup_eval_env(eval_db)
    exec_run = create_eval_run(eval_db, user, ws, task, err_type="assertion")

    repair_run = RepairRun(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        execution_run_id=exec_run.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="queued",
        max_attempts=3,
        consumed_attempts=0,
        max_model_calls=6,
        consumed_model_calls=0,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    eval_db.add(repair_run)
    eval_db.commit()

    sandbox = MockSandbox()
    graph = build_repair_graph(db=eval_db, sandbox_override=sandbox)
    state = {
        "execution_run_id": str(exec_run.id),
        "repair_run_id": str(repair_run.id),
        "task_id": str(task.id),
        "workspace_id": str(ws.id),
        "user_id": str(user.id),
        "attempt_number": 1,
        "max_attempts": 3,
        "consumed_attempts": 0,
        "max_model_calls": 6,
        "consumed_model_calls": 0,
        "deadline_at_iso": repair_run.deadline_at.isoformat(),
        "checks_to_run": ["pytest"],
        "status": "queued",
    }
    graph.invoke(state)

    eval_db.refresh(repair_run)
    assert repair_run.status == "completed"
    assert repair_run.final_outcome == "passed"
    assert repair_run.consumed_attempts == 1
    assert len(repair_run.attempts) == 1
    assert repair_run.attempts[0].proposal_status == "applied"


def test_eval_case_2_syntax_repair_success(eval_db):
    user, ws, task = setup_eval_env(eval_db)
    exec_run = create_eval_run(eval_db, user, ws, task, err_type="syntax")

    repair_run = RepairRun(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        execution_run_id=exec_run.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="queued",
        max_attempts=3,
        consumed_attempts=0,
        max_model_calls=6,
        consumed_model_calls=0,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    eval_db.add(repair_run)
    eval_db.commit()

    sandbox = MockSandbox()
    graph = build_repair_graph(db=eval_db, sandbox_override=sandbox)
    state = {
        "execution_run_id": str(exec_run.id),
        "repair_run_id": str(repair_run.id),
        "task_id": str(task.id),
        "workspace_id": str(ws.id),
        "user_id": str(user.id),
        "attempt_number": 1,
        "max_attempts": 3,
        "consumed_attempts": 0,
        "max_model_calls": 6,
        "consumed_model_calls": 0,
        "deadline_at_iso": repair_run.deadline_at.isoformat(),
        "checks_to_run": ["syntax_check"],
        "status": "queued",
    }
    graph.invoke(state)

    eval_db.refresh(repair_run)
    assert repair_run.status == "completed"
    assert repair_run.final_outcome == "passed"
    assert repair_run.consumed_attempts == 1


def test_eval_case_3_non_repairable_timeout_stopped(eval_db):
    user, ws, task = setup_eval_env(eval_db)
    exec_run = create_eval_run(eval_db, user, ws, task, err_type="timeout", exit_code=124)

    repair_run = RepairRun(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        execution_run_id=exec_run.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="queued",
        max_attempts=3,
        consumed_attempts=0,
        max_model_calls=6,
        consumed_model_calls=0,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    eval_db.add(repair_run)
    eval_db.commit()

    sandbox = MockSandbox()
    graph = build_repair_graph(db=eval_db, sandbox_override=sandbox)
    state = {
        "execution_run_id": str(exec_run.id),
        "repair_run_id": str(repair_run.id),
        "task_id": str(task.id),
        "workspace_id": str(ws.id),
        "user_id": str(user.id),
        "attempt_number": 1,
        "max_attempts": 3,
        "consumed_attempts": 0,
        "max_model_calls": 6,
        "consumed_model_calls": 0,
        "deadline_at_iso": repair_run.deadline_at.isoformat(),
        "checks_to_run": ["pytest"],
        "status": "queued",
    }
    graph.invoke(state)

    eval_db.refresh(repair_run)
    assert repair_run.status == "non_repairable"
    assert repair_run.final_outcome == "non_repairable"
    assert repair_run.consumed_attempts == 0
    assert len(repair_run.attempts) == 0  # No repair attempts executed for non-repairable defect!


def test_eval_case_4_anti_cheating_policy_stops_invalid_patch(eval_db):
    user, ws, task = setup_eval_env(eval_db)
    exec_run = create_eval_run(eval_db, user, ws, task, err_type="assertion")

    # Set task description to trigger test deletion proposal in mock provider
    task.description = "Test trigger: __TRIGGER_UNWEAKENED_TEST_DELETION__"
    eval_db.commit()

    repair_run = RepairRun(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        execution_run_id=exec_run.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="queued",
        max_attempts=1,  # limit to 1 attempt
        consumed_attempts=0,
        max_model_calls=6,
        consumed_model_calls=0,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    eval_db.add(repair_run)
    eval_db.commit()

    sandbox = MockSandbox()
    graph = build_repair_graph(db=eval_db, sandbox_override=sandbox)
    state = {
        "execution_run_id": str(exec_run.id),
        "repair_run_id": str(repair_run.id),
        "task_id": str(task.id),
        "workspace_id": str(ws.id),
        "user_id": str(user.id),
        "attempt_number": 1,
        "max_attempts": 1,
        "consumed_attempts": 0,
        "max_model_calls": 6,
        "consumed_model_calls": 0,
        "deadline_at_iso": repair_run.deadline_at.isoformat(),
        "checks_to_run": ["pytest"],
        "status": "queued",
    }
    graph.invoke(state)

    eval_db.refresh(repair_run)
    assert repair_run.status == "budget_exhausted"
    assert repair_run.final_outcome == "repair_exhausted"
    assert len(repair_run.attempts) == 1
    assert repair_run.attempts[0].proposal_status == "invalid"
    assert repair_run.attempts[0].application_result == "skipped"  # Never applied to sandbox!


def test_eval_case_5_budget_exhaustion_on_persistent_failure(eval_db):
    user, ws, task = setup_eval_env(eval_db)
    exec_run = create_eval_run(eval_db, user, ws, task, err_type="assertion")

    repair_run = RepairRun(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        execution_run_id=exec_run.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="queued",
        max_attempts=3,
        consumed_attempts=0,
        max_model_calls=6,
        consumed_model_calls=0,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    eval_db.add(repair_run)
    eval_db.commit()

    # Sandbox that always fails verification checks
    class PersistentFailingSandbox(MockSandbox):
        def run_permitted_command(self, command_key: str, extra_args=None, timeout=60):
            return 1, "test failed", "AssertionError: still failing", 0.5

    sandbox = PersistentFailingSandbox()
    graph = build_repair_graph(db=eval_db, sandbox_override=sandbox)
    state = {
        "execution_run_id": str(exec_run.id),
        "repair_run_id": str(repair_run.id),
        "task_id": str(task.id),
        "workspace_id": str(ws.id),
        "user_id": str(user.id),
        "attempt_number": 1,
        "max_attempts": 3,
        "consumed_attempts": 0,
        "max_model_calls": 6,
        "consumed_model_calls": 0,
        "deadline_at_iso": repair_run.deadline_at.isoformat(),
        "checks_to_run": ["pytest"],
        "status": "queued",
    }
    graph.invoke(state)

    eval_db.refresh(repair_run)
    assert repair_run.status == "budget_exhausted"
    assert repair_run.final_outcome == "repair_exhausted"
    assert repair_run.consumed_attempts == 3
    assert len(repair_run.attempts) == 3


def test_eval_case_6_deadline_exceeded(eval_db):
    user, ws, task = setup_eval_env(eval_db)
    exec_run = create_eval_run(eval_db, user, ws, task, err_type="assertion")

    # Deadline already in the past
    past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    repair_run = RepairRun(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        execution_run_id=exec_run.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="queued",
        max_attempts=3,
        consumed_attempts=0,
        max_model_calls=6,
        consumed_model_calls=0,
        started_at=past_time - timedelta(minutes=10),
        deadline_at=past_time,
    )
    eval_db.add(repair_run)
    eval_db.commit()

    sandbox = MockSandbox()
    graph = build_repair_graph(db=eval_db, sandbox_override=sandbox)
    state = {
        "execution_run_id": str(exec_run.id),
        "repair_run_id": str(repair_run.id),
        "task_id": str(task.id),
        "workspace_id": str(ws.id),
        "user_id": str(user.id),
        "attempt_number": 1,
        "max_attempts": 3,
        "consumed_attempts": 0,
        "max_model_calls": 6,
        "consumed_model_calls": 0,
        "deadline_at_iso": past_time.isoformat(),
        "checks_to_run": ["pytest"],
        "status": "queued",
    }
    graph.invoke(state)

    eval_db.refresh(repair_run)
    assert repair_run.status == "budget_exhausted"
    assert repair_run.final_outcome == "repair_exhausted"
    assert "deadline" in repair_run.safe_error_summary.lower()
