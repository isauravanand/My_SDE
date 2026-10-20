from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import (
    get_current_user,
    get_current_user_session,
    validate_csrf,
)
from app.core.config import get_settings
from app.core.rate_limit import rate_limit_auth
from app.core.security import clear_auth_cookies, set_auth_cookies
from app.db.session import get_db
from app.models.session import Session as UserSession
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
    summary="Register a new user account",
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> UserResponse:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, workspace, session_token, csrf_token = AuthService.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    set_auth_cookies(
        response=response,
        session_token=session_token,
        csrf_token=csrf_token,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return user


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(rate_limit_auth)],
    summary="Authenticate user and issue session cookie",
)
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> UserResponse:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, session_token, csrf_token = AuthService.login_user(
        db=db,
        email=payload.email,
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    set_auth_cookies(
        response=response,
        session_token=session_token,
        csrf_token=csrf_token,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return user


@router.post(
    "/logout",
    response_model=MessageResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Revoke active session and clear cookies",
)
async def logout(
    response: Response,
    session: UserSession = Depends(get_current_user_session),
    db: DbSession = Depends(get_db),
) -> MessageResponse:
    AuthService.logout_user(db=db, session=session)
    clear_auth_cookies(response=response, secure=settings.COOKIE_SECURE)
    return MessageResponse(message="Logged out successfully.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Fetch profile of currently authenticated user",
)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return current_user


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify user email address using single-use token",
)
async def verify_email(
    payload: VerifyEmailRequest, db: DbSession = Depends(get_db)
) -> MessageResponse:
    AuthService.verify_email(db=db, raw_token=payload.token)
    return MessageResponse(message="Email verified successfully.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
    summary="Resend verification email if account is unverified",
)
async def resend_verification(
    payload: ResendVerificationRequest, db: DbSession = Depends(get_db)
) -> MessageResponse:
    AuthService.resend_verification(db=db, email=payload.email)
    return MessageResponse(
        message="If an unverified account exists with that email, a verification link has been sent."
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
    summary="Initiate password reset workflow (privacy-preserving)",
)
async def forgot_password(
    payload: ForgotPasswordRequest, db: DbSession = Depends(get_db)
) -> MessageResponse:
    AuthService.forgot_password(db=db, email=payload.email)
    return MessageResponse(
        message="If an account with that email exists, password reset instructions have been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_auth)],
    summary="Reset password using single-use reset token",
)
async def reset_password(
    payload: ResetPasswordRequest, db: DbSession = Depends(get_db)
) -> MessageResponse:
    AuthService.reset_password(
        db=db, raw_token=payload.token, new_password=payload.new_password
    )
    return MessageResponse(
        message="Password reset successfully. Please log in with your new credentials."
    )
