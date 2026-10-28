import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.github.client import GitHubApiClient
from app.models.code_rag import RepoCodeChunk
from app.models.github import GitHubInstallation, GitHubRepository

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """Raised when repository snapshot acquisition or validation fails."""

    pass


class SnapshotManager:
    """Acquires and verifies immutable repository snapshot copies for execution."""

    def __init__(self, db: Session, github_client: GitHubApiClient | None = None):
        self.db = db
        self.github_client = github_client or GitHubApiClient()

    def prepare_snapshot(
        self,
        repository_id: UUID,
        expected_commit_sha: str,
    ) -> dict[str, bytes]:
        """
        Fetches repository contents for the exact expected_commit_sha.
        Returns a mapping of relative file paths to raw file bytes.
        Raises SnapshotError if the commit cannot be verified or contents cannot be retrieved.
        """
        if not expected_commit_sha or len(expected_commit_sha) != 40:
            raise SnapshotError(f"Invalid commit SHA format: '{expected_commit_sha}'")

        repo = self.db.execute(
            select(GitHubRepository).where(GitHubRepository.id == repository_id)
        ).scalar_one_or_none()

        if not repo:
            raise SnapshotError(f"Repository {repository_id} not found.")

        # Attempt 1: Fetch via GitHub App API if installation is available
        if repo.installation_id:
            try:
                snapshot_files = self._fetch_github_snapshot(repo, expected_commit_sha)
                if snapshot_files:
                    return snapshot_files
            except Exception as e:
                logger.warning(
                    f"GitHub API snapshot fetch failed for {repo.full_name}@{expected_commit_sha}: {e}. "
                    "Falling back to database-indexed chunks."
                )

        # Attempt 2: Reconstruct from indexed Code RAG chunks in PostgreSQL
        chunks = self.db.execute(
            select(RepoCodeChunk).where(
                RepoCodeChunk.repository_id == repository_id,
                RepoCodeChunk.commit_sha == expected_commit_sha,
            ).order_by(RepoCodeChunk.file_path, RepoCodeChunk.chunk_index)
        ).scalars().all()

        if chunks:
            files_dict: dict[str, bytes] = {}
            for chunk in chunks:
                if chunk.file_path not in files_dict:
                    files_dict[chunk.file_path] = chunk.chunk_content.encode("utf-8")
                else:
                    files_dict[chunk.file_path] += b"\n" + chunk.chunk_content.encode("utf-8")
            return files_dict

        # If repo is connected but has no chunks or GitHub error
        raise SnapshotError(
            f"Unable to materialize snapshot for {repo.full_name} at commit {expected_commit_sha}. "
            "Neither GitHub API nor indexed code chunks could provide the repository files."
        )

    def _fetch_github_snapshot(
        self,
        repo: GitHubRepository,
        commit_sha: str,
    ) -> dict[str, bytes]:
        """Fetches tree and blobs via GitHub REST API."""
        inst = self.db.execute(
            select(GitHubInstallation).where(GitHubInstallation.id == repo.installation_id)
        ).scalar_one_or_none()

        if not inst:
            raise SnapshotError(f"GitHub Installation {repo.installation_id} not found.")

        owner, repo_name = repo.full_name.split("/", 1)

        # Verify commit SHA exists
        resolved_commit = self.github_client.get_ref_commit(
            installation_id=inst.installation_id,
            owner=owner,
            repo=repo_name,
            ref=commit_sha,
        )
        if resolved_commit != commit_sha:
            raise SnapshotError(
                f"Resolved commit mismatch: expected {commit_sha}, got {resolved_commit}."
            )

        # Fetch git tree
        tree_data = self.github_client.get_tree(
            installation_id=inst.installation_id,
            owner=owner,
            repo=repo_name,
            tree_sha=commit_sha,
            recursive=True,
        )

        tree_items = tree_data.get("tree", [])
        files_dict: dict[str, bytes] = {}

        # Limit maximum files fetched
        for item in tree_items[:200]:
            if item.get("type") == "blob":
                path = item.get("path")
                blob_sha = item.get("sha")
                if path and blob_sha:
                    blob_content = self.github_client.get_blob_content(
                        installation_id=inst.installation_id,
                        owner=owner,
                        repo=repo_name,
                        blob_sha=blob_sha,
                    )
                    files_dict[path] = blob_content

        return files_dict
