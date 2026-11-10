from fastapi import APIRouter, Depends, status

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession, SupervisorOrManager
from app.core.rate_limit import rate_limit
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import ErrorResponse
from app.schemas.user import ProfileUpdate, UserCreate, UserOut
from app.services import auth as auth_service
from app.services import users as users_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    dependencies=[Depends(rate_limit("login", lambda: get_settings().rate_limit_login_per_minute))],
)
def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    user = auth_service.authenticate(db, body.email, body.password)
    return auth_service.issue_token(user)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def register(body: UserCreate, db: DbSession, actor: SupervisorOrManager) -> UserOut:
    """Create an account. Managers may create any role; supervisors may create technicians at their own site."""
    return UserOut.model_validate(users_service.create_user(db, actor, body))


@router.get("/me", response_model=UserOut, responses={401: {"model": ErrorResponse}})
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut, responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def update_me(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> UserOut:
    """Self-service profile change: only the preferred language (it sets the Prisma language and Timbre voice
    for this user, including spoken task announcements). Role, site and email stay with supervisors/managers."""
    return UserOut.model_validate(users_service.update_language(db, user, body.preferred_language))
