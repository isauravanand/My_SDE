import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.models.code_rag import RepoCodeChunk, RepoIndexingJob
from app.models.github import GitHubInstallation, GitHubRepository
from app.models.project import Project
from app.models.task import Task
from app.rag.embeddings.fake import DeterministicFakeEmbeddingProvider
from app.rag.ingestion import RepositoryIngestionService


def register_user(client: TestClient, email: str, name: str = "Test User"):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    user = res.json()
    cookies = {
        SESSION_COOKIE_NAME: res.cookies[SESSION_COOKIE_NAME],
        CSRF_COOKIE_NAME: res.cookies[CSRF_COOKIE_NAME],
    }
    headers = {CSRF_HEADER_NAME: res.cookies[CSRF_COOKIE_NAME]}
    return user, cookies, headers


def setup_mock_repository(db: Session, workspace_id: uuid.UUID):
    """Seed a GitHubInstallation and a selected GitHubRepository."""
    inst = GitHubInstallation(
        workspace_id=workspace_id,
        installation_id=98765432,
        account_login="acme-corp",
        account_type="Organization",
        status="active",
    )
    db.add(inst)
    db.flush()

    repo = GitHubRepository(
        workspace_id=workspace_id,
        installation_id=inst.id,
        github_repo_id=1234567,
        owner_login="acme-corp",
        name="web-service",
        full_name="acme-corp/web-service",
        default_branch="main",
        is_private=True,
        is_selected=True,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return inst, repo


def test_indexing_and_retrieval_flow(client: TestClient, db: Session):
    # 1. Register user and fetch workspace
    _, cookies, headers = register_user(client, "rag_user@example.com", "RAG Tester")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = uuid.UUID(client.get("/api/v1/workspaces").json()[0]["id"])

    inst, repo = setup_mock_repository(db, ws_id)

    # 2. Querying Code RAG before indexing returns is_indexed=False
    query_payload = {"query": "how to authenticate user", "top_k": 3}
    ret_unindexed = client.post(
        f"/api/v1/rag/repositories/{repo.id}/retrieve?workspace_id={ws_id}",
        json=query_payload,
    )
    assert ret_unindexed.status_code == 200
    assert ret_unindexed.json()["is_indexed"] is False
    assert ret_unindexed.json()["results"] == []

    # 3. Trigger indexing with mocked GitHub API
    mock_commit = "a" * 40
    mock_tree = {
        "sha": mock_commit,
        "truncated": False,
        "tree": [
            {"path": "src/auth.py", "type": "blob", "sha": "blob1", "size": 350},
            {"path": "src/db.py", "type": "blob", "sha": "blob2", "size": 420},
            {"path": ".env", "type": "blob", "sha": "blob_env", "size": 100},  # Must be excluded!
            {"path": "app.exe", "type": "blob", "sha": "blob_exe", "size": 5000},  # Must be excluded!
        ],
    }

    auth_code = b"""import hashlib

def authenticate(username, password):
    # Check credentials
    return True
"""
    db_code = b"""from sqlalchemy import create_engine

def get_connection():
    return create_engine("sqlite:///:memory:")
"""

    def mock_get_blob(installation_id, owner, repo, blob_sha):
        if blob_sha == "blob1":
            return auth_code
        if blob_sha == "blob2":
            return db_code
        return b""

    with (
        patch("app.integrations.github.client.GitHubApiClient.get_ref_commit", return_value=mock_commit),
        patch("app.integrations.github.client.GitHubApiClient.get_tree", return_value=mock_tree),
        patch("app.integrations.github.client.GitHubApiClient.get_blob_content", side_effect=mock_get_blob),
    ):
        trigger_res = client.post(
            f"/api/v1/rag/repositories/{repo.id}/index?workspace_id={ws_id}",
            json={"target_ref": "main"},
            headers=headers,
        )
        assert trigger_res.status_code == 202
        job_data = trigger_res.json()
        job_id = job_data["id"]
        assert job_data["commit_sha"] == mock_commit

        # Manually run ingestion synchronously to test chunking & embedding storage in the same session
        provider = DeterministicFakeEmbeddingProvider(dimensions=384)
        ingestion_service = RepositoryIngestionService(embedding_provider=provider)
        import asyncio
        asyncio.run(ingestion_service.ingest_repository(db, uuid.UUID(job_id)))

    # 4. Check status endpoint
    status_res = client.get(f"/api/v1/rag/repositories/{repo.id}/index/status?workspace_id={ws_id}")
    assert status_res.status_code == 200
    stat = status_res.json()
    assert stat["status"] == "completed"
    assert stat["files_accepted"] == 2
    assert stat["files_excluded"] == 2
    assert stat["chunks_count"] >= 2
    assert stat["exclusions_summary"]["secret_file"] >= 1
    assert stat["exclusions_summary"]["binary_or_compiled"] >= 1

    # 5. Query Code RAG with search query
    search_res = client.post(
        f"/api/v1/rag/repositories/{repo.id}/retrieve?workspace_id={ws_id}",
        json={"query": "authenticate user password credentials", "top_k": 3},
    )
    assert search_res.status_code == 200
    data = search_res.json()
    assert data["is_indexed"] is True
    assert len(data["results"]) >= 1

    top_chunk = data["results"][0]
    assert "src/auth.py" in top_chunk["file_path"]
    assert top_chunk["start_line"] >= 1
    assert top_chunk["end_line"] >= top_chunk["start_line"]
    assert "authenticate" in top_chunk["chunk_content"]
    assert top_chunk["score"] > 0.0
    assert "github.com/acme-corp/web-service/blob" in top_chunk["github_url"]


def test_task_context_retrieval(client: TestClient, db: Session):
    _, cookies, _ = register_user(client, "task_rag@example.com", "Task RAG User")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = uuid.UUID(client.get("/api/v1/workspaces").json()[0]["id"])

    inst, repo = setup_mock_repository(db, ws_id)

    # Create Project and Task linked to this repository
    project = Project(
        workspace_id=ws_id,
        name="Backend Core",
        slug="backend-core",
        repository_id=repo.id,
    )
    db.add(project)
    db.flush()

    task = Task(
        workspace_id=ws_id,
        project_id=project.id,
        repository_id=repo.id,
        title="Implement secure password authentication",
        description="Verify user password against hashed credentials",
    )
    db.add(task)
    db.flush()

    # Seed a pre-indexed chunk
    provider = DeterministicFakeEmbeddingProvider(dimensions=384)
    import asyncio
    vec = asyncio.run(provider.embed_query("authenticate user credentials"))

    chunk = RepoCodeChunk(
        workspace_id=ws_id,
        repository_id=repo.id,
        commit_sha="b" * 40,
        file_path="src/security.py",
        file_language="python",
        chunk_index=0,
        start_line=1,
        end_line=15,
        chunk_content="def verify_password(hash, password):\n    return check_hash(hash, password)\n",
        content_hash="h" * 64,
        symbol_name="verify_password",
        symbol_type="function",
        embedding_model="mock-embed-384",
        embedding_dimensions=384,
        embedding_vector=vec,
    )
    db.add(chunk)

    job = RepoIndexingJob(
        workspace_id=ws_id,
        repository_id=repo.id,
        target_ref="main",
        commit_sha="b" * 40,
        status="completed",
        files_discovered=1,
        files_accepted=1,
        embedding_provider="fake",
        embedding_model="mock-embed-384",
        embedding_dimensions=384,
    )
    db.add(job)
    db.commit()

    # Query task context endpoint
    task_res = client.get(f"/api/v1/rag/tasks/{task.id}/retrieve-context")
    assert task_res.status_code == 200
    data = task_res.json()
    assert data["is_indexed"] is True
    assert len(data["results"]) >= 1
    assert "src/security.py" in data["results"][0]["file_path"]


def test_cross_workspace_isolation(client: TestClient, db: Session):
    # User A
    _, cookies_a, _ = register_user(client, "user_a@example.com", "User A")
    ws_a_id = uuid.UUID(client.get("/api/v1/workspaces").json()[0]["id"])
    _, repo_a = setup_mock_repository(db, ws_a_id)

    # User B
    _, cookies_b, _ = register_user(client, "user_b@example.com", "User B")
    client.cookies.clear()
    client.cookies.update(cookies_b)
    ws_b_id = uuid.UUID(client.get("/api/v1/workspaces").json()[0]["id"])

    # User B attempts to access User A's repo indexing or retrieval
    res = client.get(f"/api/v1/rag/repositories/{repo_a.id}/index/status?workspace_id={ws_b_id}")
    assert res.status_code == 200
    assert res.json() is None

    ret_res = client.post(
        f"/api/v1/rag/repositories/{repo_a.id}/retrieve?workspace_id={ws_b_id}",
        json={"query": "test query"},
    )
    assert ret_res.status_code == 404
