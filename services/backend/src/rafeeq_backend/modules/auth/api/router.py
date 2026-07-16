from fastapi import APIRouter, status

from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.auth.application.service import (
    authenticate,
    issue_tokens,
    register_user,
    revoke_token,
    rotate_tokens,
)
from rafeeq_backend.modules.auth.domain.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: DbSession) -> UserResponse:
    return UserResponse.model_validate(register_user(db, request))


@router.post("/login", response_model=TokenPair)
def login(request: LoginRequest, db: DbSession) -> TokenPair:
    return issue_tokens(db, authenticate(db, str(request.email), request.password))


@router.post("/refresh", response_model=TokenPair)
def refresh(request: RefreshRequest, db: DbSession) -> TokenPair:
    return rotate_tokens(db, request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: LogoutRequest, db: DbSession) -> None:
    revoke_token(db, request.refresh_token)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
