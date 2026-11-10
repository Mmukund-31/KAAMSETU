from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import Email, UserOut


class LoginRequest(BaseModel):
    email: Email
    # No strength rule on login: only on account creation.
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut
