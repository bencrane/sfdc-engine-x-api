from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.auth.dependencies import get_current_auth
from app.config import settings
from app.db import get_pool

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class MeResponse(BaseModel):
    org_id: str
    user_id: str
    role: str
    permissions: list[str]
    client_id: str | None
    auth_method: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, org_id, role::text AS role, client_id, password_hash
        FROM users
        WHERE email = $1
          AND is_active = TRUE
        """,
        body.email,
    )

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )
    if row is None or not row["password_hash"]:
        raise invalid_credentials
    if not pwd_context.verify(body.password, row["password_hash"]):
        raise invalid_credentials

    now = datetime.now(UTC)
    expires_in = settings.jwt_expiry_seconds
    exp = now + timedelta(seconds=expires_in)
    claims = {
        "org_id": str(row["org_id"]),
        "user_id": str(row["id"]),
        "role": row["role"],
        "client_id": str(row["client_id"]) if row["client_id"] else None,
        "exp": int(exp.timestamp()),
    }
    access_token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get("/me", response_model=MeResponse)
async def me(auth=Depends(get_current_auth)) -> MeResponse:
    return MeResponse(
        org_id=auth.org_id,
        user_id=auth.user_id,
        role=auth.role,
        permissions=auth.permissions,
        client_id=auth.client_id,
        auth_method=auth.auth_method,
    )
