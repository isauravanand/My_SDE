import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.github import (
    GitHubInstallation,
    GitHubRepository,
    GitHubWebhookDelivery,
)

logger = logging.getLogger(__name__)


class GitHubWebhookHandler:
    """Validates GitHub webhook signatures and processes installation events idempotently."""

    def __init__(self):
        self.settings = get_settings()

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        """Verify the X-Hub-Signature-256 header using constant-time comparison."""
        webhook_secret = self.settings.GITHUB_WEBHOOK_SECRET
        if not webhook_secret:
            logger.warning("GITHUB_WEBHOOK_SECRET is not configured; rejecting webhook")
            return False

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        computed = hmac.new(
            key=webhook_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        expected = f"sha256={computed}"
        return hmac.compare_digest(expected, signature_header)

    def process_webhook(
        self,
        db: Session,
        delivery_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Process incoming webhook event with deduplication and state synchronization."""
        if not delivery_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-GitHub-Delivery header",
            )

        # 1. Deduplication / Idempotency Check
        existing_delivery = db.scalar(
            select(GitHubWebhookDelivery).where(GitHubWebhookDelivery.delivery_id == delivery_id)
        )
        if existing_delivery:
            logger.info(f"Duplicate webhook delivery {delivery_id} ignored")
            return {"status": "ignored", "reason": "duplicate_delivery"}

        action = payload.get("action")

        # Record delivery
        delivery_record = GitHubWebhookDelivery(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            status="processed",
        )
        db.add(delivery_record)

        # 2. Event Dispatching
        if event_type == "installation":
            self._handle_installation_event(db, action, payload)
        elif event_type == "installation_repositories":
            self._handle_installation_repositories_event(db, action, payload)
        else:
            logger.info(f"Unhandled GitHub webhook event type: {event_type}")
            delivery_record.status = "ignored"

        db.commit()
        return {"status": "success", "event": event_type, "action": action}

    def _handle_installation_event(self, db: Session, action: str | None, payload: dict[str, Any]) -> None:
        """Handle installation created, deleted, suspended, or unsuspended."""
        installation_data = payload.get("installation", {})
        installation_id = installation_data.get("id")
        if not installation_id:
            return

        installation = db.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
        )
        if not installation:
            logger.info(f"Received installation event for unknown installation {installation_id}")
            return

        now = datetime.now(timezone.utc)
        if action == "deleted":
            installation.status = "uninstalled"
            installation.uninstalled_at = now
            installation.updated_at = now
            logger.info(f"GitHub installation {installation_id} marked uninstalled via webhook")
        elif action == "suspend":
            installation.status = "suspended"
            installation.updated_at = now
        elif action == "unsuspend":
            installation.status = "active"
            installation.updated_at = now

    def _handle_installation_repositories_event(
        self, db: Session, action: str | None, payload: dict[str, Any]
    ) -> None:
        """Handle repositories added or removed from an installation."""
        installation_data = payload.get("installation", {})
        installation_id = installation_data.get("id")
        if not installation_id:
            return

        installation = db.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
        )
        if not installation:
            return

        now = datetime.now(timezone.utc)
        workspace_id = installation.workspace_id

        if action == "added":
            repos_added = payload.get("repositories_added", [])
            for r in repos_added:
                gh_id = r.get("id")
                if not gh_id:
                    continue

                full_name = r.get("full_name", "")
                parts = full_name.split("/")
                owner = parts[0] if len(parts) > 0 else ""
                name = parts[1] if len(parts) > 1 else full_name

                existing = db.scalar(
                    select(GitHubRepository).where(
                        GitHubRepository.workspace_id == workspace_id,
                        GitHubRepository.github_repo_id == gh_id,
                    )
                )
                if not existing:
                    new_repo = GitHubRepository(
                        workspace_id=workspace_id,
                        installation_id=installation.id,
                        github_repo_id=gh_id,
                        owner_login=owner,
                        name=name,
                        full_name=full_name,
                        is_private=r.get("private", True),
                        is_selected=False,
                        last_synced_at=now,
                    )
                    db.add(new_repo)

        elif action == "removed":
            repos_removed = payload.get("repositories_removed", [])
            for r in repos_removed:
                gh_id = r.get("id")
                if not gh_id:
                    continue
                repo = db.scalar(
                    select(GitHubRepository).where(
                        GitHubRepository.workspace_id == workspace_id,
                        GitHubRepository.github_repo_id == gh_id,
                    )
                )
                if repo:
                    # Deselect and/or remove from database
                    db.delete(repo)
