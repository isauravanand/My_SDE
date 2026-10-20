import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.github.client import GitHubApiClient, GitHubApiError
from app.models.github import (
    GitHubInstallation,
    GitHubOAuthState,
    GitHubRepository,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.github import GitHubInstallUrlResponse, GitHubIntegrationStatusResponse
from app.services.activity import ActivityService


class GitHubService:
    """Service orchestrating GitHub App installations, repository syncing, and workspace isolation."""

    def __init__(self, client: GitHubApiClient | None = None):
        self.settings = get_settings()
        self.client = client or GitHubApiClient(self.settings)

    def get_integration_status(self, db: Session, workspace_id: uuid.UUID) -> GitHubIntegrationStatusResponse:
        """Retrieve safe metadata on the GitHub App connection status for a workspace."""
        is_configured = self.settings.is_github_configured

        # Find active installation for workspace
        query = select(GitHubInstallation).where(
            GitHubInstallation.workspace_id == workspace_id,
            GitHubInstallation.status == "active",
        )
        installation = db.scalar(query)

        if not installation:
            return GitHubIntegrationStatusResponse(
                is_configured=is_configured,
                is_connected=False,
                app_slug=self.settings.GITHUB_APP_SLUG,
            )

        # Count repositories
        total_repos = db.scalar(
            select(func.count(GitHubRepository.id)).where(
                GitHubRepository.workspace_id == workspace_id,
                GitHubRepository.installation_id == installation.id,
            )
        ) or 0

        selected_repos = db.scalar(
            select(func.count(GitHubRepository.id)).where(
                GitHubRepository.workspace_id == workspace_id,
                GitHubRepository.installation_id == installation.id,
                GitHubRepository.is_selected.is_(True),
            )
        ) or 0

        # Get most recent sync time
        last_synced = db.scalar(
            select(func.max(GitHubRepository.last_synced_at)).where(
                GitHubRepository.workspace_id == workspace_id,
                GitHubRepository.installation_id == installation.id,
            )
        )

        return GitHubIntegrationStatusResponse(
            is_configured=is_configured,
            is_connected=True,
            installation_id=installation.installation_id,
            account_login=installation.account_login,
            account_type=installation.account_type,
            account_avatar_url=installation.account_avatar_url,
            status=installation.status,
            total_repositories=total_repos,
            selected_repositories=selected_repos,
            last_synced_at=last_synced,
            app_slug=self.settings.GITHUB_APP_SLUG,
        )

    def initiate_installation(
        self, db: Session, workspace: Workspace, user: User
    ) -> GitHubInstallUrlResponse:
        """Generate a cryptographically secure, single-use state token and build the install URL."""
        if not self.settings.is_github_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub App integration is not configured in this environment.",
            )

        state_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        oauth_state = GitHubOAuthState(
            workspace_id=workspace.id,
            user_id=user.id,
            state_token=state_token,
            expires_at=expires_at,
        )
        db.add(oauth_state)
        db.commit()

        # Build GitHub installation URL
        if self.settings.GITHUB_APP_SLUG:
            install_url = f"https://github.com/apps/{self.settings.GITHUB_APP_SLUG}/installations/new?state={state_token}"
        else:
            install_url = f"https://github.com/apps/installations/new?state={state_token}"

        return GitHubInstallUrlResponse(install_url=install_url, state=state_token)

    def handle_callback(
        self, db: Session, state: str, installation_id: int, user: User
    ) -> GitHubInstallation:
        """Validate single-use state token and bind installation to target workspace."""
        if not self.settings.is_github_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub App integration is not configured in this environment.",
            )

        # 1. Validate State Token
        oauth_state = db.scalar(
            select(GitHubOAuthState).where(GitHubOAuthState.state_token == state)
        )
        if not oauth_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or missing GitHub installation state token.",
            )

        if oauth_state.consumed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub installation state token has already been consumed.",
            )

        now = datetime.now(timezone.utc)
        if oauth_state.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub installation state token has expired.",
            )

        if oauth_state.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="State token does not belong to the authenticated user.",
            )

        workspace_id = oauth_state.workspace_id

        # 2. Check if installation_id is already bound to another workspace
        existing_other = db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.installation_id == installation_id,
                GitHubInstallation.workspace_id != workspace_id,
                GitHubInstallation.status == "active",
            )
        )
        if existing_other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This GitHub App installation is already connected to another workspace.",
            )

        # 3. Mark state as consumed
        oauth_state.consumed_at = now

        # 4. Fetch details from GitHub API
        try:
            details = self.client.get_installation_details(installation_id)
        except GitHubApiError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"Failed to verify installation with GitHub: {e.message}",
            ) from e

        account = details.get("account", {})
        account_login = account.get("login", f"account-{installation_id}")
        account_type = account.get("type", "User")
        account_avatar = account.get("avatar_url")
        permissions_str = json.dumps(details.get("permissions", {}))

        # 5. Upsert Installation for this workspace
        installation = db.scalar(
            select(GitHubInstallation).where(GitHubInstallation.workspace_id == workspace_id)
        )
        if installation:
            installation.installation_id = installation_id
            installation.account_login = account_login
            installation.account_type = account_type
            installation.account_avatar_url = account_avatar
            installation.permissions_json = permissions_str
            installation.status = "active"
            installation.uninstalled_at = None
            installation.updated_at = now
        else:
            installation = GitHubInstallation(
                workspace_id=workspace_id,
                installation_id=installation_id,
                account_login=account_login,
                account_type=account_type,
                account_avatar_url=account_avatar,
                permissions_json=permissions_str,
                status="active",
            )
            db.add(installation)

        db.commit()
        db.refresh(installation)

        # 6. Fetch and synchronize initial repositories
        try:
            self.sync_repositories(db, workspace_id, user_id=user.id)
        except Exception:
            # If initial repo fetch fails, don't abort installation binding
            pass

        # 7. Audit Log
        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="github_connected",
            resource_type="installation",
            resource_id=installation.id,
            metadata={
                "account_login": account_login,
                "installation_id": installation_id,
            },
        )

        return installation

    def list_repositories(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        search: str | None = None,
        is_selected: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GitHubRepository], int]:
        """List repositories synchronized for the given workspace."""
        base_query = select(GitHubRepository).where(
            GitHubRepository.workspace_id == workspace_id
        )

        if is_selected is not None:
            base_query = base_query.where(GitHubRepository.is_selected == is_selected)

        if search:
            search_pattern = f"%{search.strip().lower()}%"
            base_query = base_query.where(
                func.lower(GitHubRepository.full_name).like(search_pattern)
            )

        total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0

        # Prioritize selected repositories, then alphabetical
        query = (
            base_query.order_by(
                GitHubRepository.is_selected.desc(),
                GitHubRepository.full_name.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        repos = list(db.scalars(query).all())
        return repos, total

    def sync_repositories(
        self, db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> int:
        """Fetch repositories from GitHub for the active installation and upsert them."""
        installation = db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.workspace_id == workspace_id,
                GitHubInstallation.status == "active",
            )
        )
        if not installation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active GitHub App installation found for this workspace.",
            )

        try:
            gh_repos = self.client.list_installation_repositories(installation.installation_id)
        except GitHubApiError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"GitHub API error during repository synchronization: {e.message}",
            ) from e

        now = datetime.now(timezone.utc)
        synced_count = 0
        current_gh_ids = set()

        for r in gh_repos:
            gh_id = r["id"]
            current_gh_ids.add(gh_id)
            owner = r.get("owner", {}).get("login", "")
            name = r.get("name", "")
            full_name = r.get("full_name", f"{owner}/{name}")
            default_branch = r.get("default_branch", "main")
            is_private = r.get("private", True)
            is_archived = r.get("archived", False)

            repo = db.scalar(
                select(GitHubRepository).where(
                    GitHubRepository.workspace_id == workspace_id,
                    GitHubRepository.github_repo_id == gh_id,
                )
            )

            if repo:
                repo.owner_login = owner
                repo.name = name
                repo.full_name = full_name
                repo.default_branch = default_branch
                repo.is_private = is_private
                repo.is_archived = is_archived
                repo.last_synced_at = now
                repo.updated_at = now
            else:
                repo = GitHubRepository(
                    workspace_id=workspace_id,
                    installation_id=installation.id,
                    github_repo_id=gh_id,
                    owner_login=owner,
                    name=name,
                    full_name=full_name,
                    default_branch=default_branch,
                    is_private=is_private,
                    is_archived=is_archived,
                    is_selected=False,
                    last_synced_at=now,
                )
                db.add(repo)
            synced_count += 1

        db.commit()

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user_id,
            event_type="github_repositories_synced",
            resource_type="installation",
            resource_id=installation.id,
            metadata={"synced_count": synced_count},
        )

        return synced_count

    def toggle_repository_selection(
        self, db: Session, workspace_id: uuid.UUID, repo_id: uuid.UUID, is_selected: bool
    ) -> GitHubRepository:
        """Select or deselect a repository for active use within the workspace."""
        repo = db.scalar(
            select(GitHubRepository).where(
                GitHubRepository.id == repo_id,
                GitHubRepository.workspace_id == workspace_id,
            )
        )
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found in this workspace.",
            )

        repo.is_selected = is_selected
        repo.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(repo)
        return repo

    def disconnect_installation(
        self, db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> GitHubInstallation:
        """Disconnect the GitHub App integration for this workspace."""
        installation = db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.workspace_id == workspace_id,
                GitHubInstallation.status == "active",
            )
        )
        if not installation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active GitHub App installation to disconnect.",
            )

        now = datetime.now(timezone.utc)
        installation.status = "uninstalled"
        installation.uninstalled_at = now
        installation.updated_at = now

        db.commit()

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user_id,
            event_type="github_disconnected",
            resource_type="installation",
            resource_id=installation.id,
            metadata={"account_login": installation.account_login},
        )

        return installation
