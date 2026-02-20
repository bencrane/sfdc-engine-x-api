import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_auth
from app.db import get_pool

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


class TokenCreateRequest(BaseModel):
    label: str | None = None
    expires_in_days: int | None = Field(default=None, ge=1)


class TokensListRequest(BaseModel):
    pass


class TokenRevokeRequest(BaseModel):
    id: UUID


class TokenCreateResponse(BaseModel):
    id: str
    token: str
    label: str | None
    expires_at: str | None
    created_at: str


class TokenListItem(BaseModel):
    id: str
    label: str | None
    last_used_at: str | None
    expires_at: str | None
    is_active: bool
    created_at: str


class TokensListResponse(BaseModel):
    data: list[TokenListItem]


class TokenRevokeResponse(BaseModel):
    id: str
    is_active: bool


@router.post("/create", response_model=TokenCreateResponse)
async def create_token(
    body: TokenCreateRequest,
    auth=Depends(get_current_auth),
) -> TokenCreateResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    row = await pool.fetchrow(
        """
        INSERT INTO api_tokens (org_id, user_id, token_hash, label, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, label, expires_at, created_at
        """,
        auth.org_id,
        auth.user_id,
        token_hash,
        body.label,
        expires_at,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create API token")

    return TokenCreateResponse(
        id=str(row["id"]),
        token=raw_token,
        label=row["label"],
        expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
        created_at=row["created_at"].isoformat(),
    )


@router.post("/list", response_model=TokensListResponse)
async def list_tokens(
    _: TokensListRequest,
    auth=Depends(get_current_auth),
) -> TokensListResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    rows = await pool.fetch(
        """
        SELECT id, label, last_used_at, expires_at, is_active, created_at
        FROM api_tokens
        WHERE org_id = $1
          AND is_active = TRUE
        ORDER BY created_at DESC
        """,
        auth.org_id,
    )

    return TokensListResponse(
        data=[
            TokenListItem(
                id=str(row["id"]),
                label=row["label"],
                last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
                expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )


@router.post("/revoke", response_model=TokenRevokeResponse)
async def revoke_token(
    body: TokenRevokeRequest,
    auth=Depends(get_current_auth),
) -> TokenRevokeResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    row = await pool.fetchrow(
        """
        UPDATE api_tokens
        SET is_active = FALSE
        WHERE id = $1
          AND org_id = $2
        RETURNING id, is_active
        """,
        body.id,
        auth.org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="API token not found")

    return TokenRevokeResponse(
        id=str(row["id"]),
        is_active=row["is_active"],
    )
