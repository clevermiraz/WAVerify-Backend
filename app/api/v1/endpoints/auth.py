from fastapi import APIRouter, status

from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import AuthServiceDep
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenPair,
    VerifyEmailRequest,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, auth: AuthServiceDep) -> AuthResponse:
    """Create an account, start a Free subscription and send a verification email."""
    user = auth.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        company=payload.company,
    )
    return AuthResponse(user=UserRead.model_validate(user), tokens=auth.issue_tokens(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, auth: AuthServiceDep) -> AuthResponse:
    user = auth.authenticate(email=payload.email, password=payload.password)
    return AuthResponse(user=UserRead.model_validate(user), tokens=auth.issue_tokens(user))


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> TokenPair:
    """Exchange a refresh token for a new pair. The old token is revoked."""
    return auth.refresh(payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: RefreshRequest, auth: AuthServiceDep) -> MessageResponse:
    auth.logout(payload.refresh_token)
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=UserRead)
def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/verify-email", response_model=UserRead)
def verify_email(payload: VerifyEmailRequest, auth: AuthServiceDep) -> UserRead:
    return UserRead.model_validate(auth.verify_email(payload.token))


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    payload: ResendVerificationRequest, auth: AuthServiceDep
) -> MessageResponse:
    auth.resend_verification(payload.email)
    return MessageResponse(
        message="If that address needs verification, a new link is on its way."
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest, auth: AuthServiceDep
) -> MessageResponse:
    auth.request_password_reset(payload.email)
    # Deliberately identical whether or not the address exists.
    return MessageResponse(
        message="If an account exists for that address, we've sent a reset link."
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, auth: AuthServiceDep) -> MessageResponse:
    auth.reset_password(token=payload.token, new_password=payload.password)
    return MessageResponse(message="Your password has been updated.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest, user: CurrentUserDep, auth: AuthServiceDep
) -> MessageResponse:
    auth.change_password(
        user, current=payload.current_password, new=payload.new_password
    )
    return MessageResponse(message="Your password has been updated.")
