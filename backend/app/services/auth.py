import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    SESSION_MAX_AGE_SECONDS,
    VERIFICATION_TOKEN_EXPIRE_HOURS,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.session import Session as UserSession
from app.models.token import SecurityToken
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.email import get_email_service

settings = get_settings()


def slugify(text: str) -> str:
    """Generate clean URL-safe slug from text."""
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "workspace"


class AuthService:
    """Service encapsulating user registration, authentication, sessions, and recovery."""

    @staticmethod
    def register_user(
        db: Session,
        email: str,
        password: str,
        full_name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, Workspace, str, str]:
        """Atomically create user, default workspace, owner membership, verification token, and session."""
        normalized_email = email.strip().lower()

        # Check existing user
        existing_user = db.scalar(select(User).where(User.email == normalized_email))
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        try:
            # 1. Create User
            hashed_pwd = hash_password(password)
            user = User(
                email=normalized_email,
                full_name=full_name.strip() if full_name else None,
                hashed_password=hashed_pwd,
                is_verified=False,
                is_active=True,
            )
            db.add(user)
            db.flush()  # Populates user.id

            # 2. Create Default Workspace
            ws_name = f"{user.full_name or 'Personal'}'s Workspace"
            base_slug = slugify(f"{user.full_name or 'personal'}-workspace")
            slug = f"{base_slug}-{secrets.token_hex(3)}"

            workspace = Workspace(
                name=ws_name,
                slug=slug,
                owner_id=user.id,
            )
            db.add(workspace)
            db.flush()

            # 3. Create Owner Membership
            membership = WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
            )
            db.add(membership)

            # 4. Create Single-Use Email Verification Token
            raw_verify_token = generate_opaque_token(32)
            verify_token = SecurityToken(
                user_id=user.id,
                token_hash=hash_token(raw_verify_token),
                purpose="email_verification",
                expires_at=datetime.now(timezone.utc)
                + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS),
            )
            db.add(verify_token)

            # 5. Create Server-Side Session
            raw_session_token = generate_opaque_token(32)
            raw_csrf_token = generate_opaque_token(32)
            session = UserSession(
                user_id=user.id,
                token_hash=hash_token(raw_session_token),
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(session)

            # Commit all entities atomically
            db.commit()
            db.refresh(user)
            db.refresh(workspace)

            # Dispatch verification email via adapter
            email_service = get_email_service()
            email_service.send_verification_email(user.email, raw_verify_token, user.full_name)

            return user, workspace, raw_session_token, raw_csrf_token

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def login_user(
        db: Session,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str]:
        """Authenticate user credentials and create a server-side session."""
        normalized_email = email.strip().lower()
        user = db.scalar(select(User).where(User.email == normalized_email))

        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated. Please contact support.",
            )

        raw_session_token = generate_opaque_token(32)
        raw_csrf_token = generate_opaque_token(32)
        session = UserSession(
            user_id=user.id,
            token_hash=hash_token(raw_session_token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(session)
        db.commit()

        return user, raw_session_token, raw_csrf_token

    @staticmethod
    def logout_user(db: Session, session: UserSession) -> None:
        """Revoke active session."""
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()

    @staticmethod
    def verify_email(db: Session, raw_token: str) -> User:
        """Verify user email using single-use token."""
        token_digest = hash_token(raw_token)
        token_record = db.scalar(
            select(SecurityToken).where(
                SecurityToken.token_hash == token_digest,
                SecurityToken.purpose == "email_verification",
            )
        )

        if not token_record or not token_record.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token.",
            )

        user = db.get(User, token_record.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Associated user not found.",
            )

        token_record.consumed_at = datetime.now(timezone.utc)
        user.is_verified = True
        user.verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def resend_verification(db: Session, email: str) -> None:
        """Issue new verification token if user is unverified."""
        normalized_email = email.strip().lower()
        user = db.scalar(select(User).where(User.email == normalized_email))
        if user and not user.is_verified:
            raw_token = generate_opaque_token(32)
            token = SecurityToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                purpose="email_verification",
                expires_at=datetime.now(timezone.utc)
                + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS),
            )
            db.add(token)
            db.commit()
            email_service = get_email_service()
            email_service.send_verification_email(user.email, raw_token, user.full_name)

    @staticmethod
    def forgot_password(db: Session, email: str) -> None:
        """Generate single-use reset token and send email (privacy-preserving)."""
        normalized_email = email.strip().lower()
        user = db.scalar(select(User).where(User.email == normalized_email))
        if user and user.is_active:
            raw_token = generate_opaque_token(32)
            token = SecurityToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                purpose="password_reset",
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
            db.add(token)
            db.commit()
            email_service = get_email_service()
            email_service.send_password_reset_email(user.email, raw_token, user.full_name)

    @staticmethod
    def reset_password(db: Session, raw_token: str, new_password: str) -> None:
        """Reset password, consume token, and revoke all active sessions."""
        token_digest = hash_token(raw_token)
        token_record = db.scalar(
            select(SecurityToken).where(
                SecurityToken.token_hash == token_digest,
                SecurityToken.purpose == "password_reset",
            )
        )

        if not token_record or not token_record.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset token.",
            )

        user = db.get(User, token_record.user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account is invalid or deactivated.",
            )

        # Update password & consume token
        user.hashed_password = hash_password(new_password)
        token_record.consumed_at = datetime.now(timezone.utc)

        # Invalidate all current active sessions for security
        now = datetime.now(timezone.utc)
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

        db.commit()
