import hmac
from typing import Literal
from uuid import UUID

import bcrypt
import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import settings
from app.db import get_pool

ValidRole = Literal["org_admin", "company_admin", "company_member"]

router = APIRouter(prefix="/api/super-admin", tags=["super-admin"])


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_at: str


class CreateSuperAdminUserRequest(BaseModel):
    org_id: UUID
    email: str
    name: str | None = None
    password: str
    role: ValidRole


class SuperAdminUserResponse(BaseModel):
    id: str
    org_id: str
    email: str
    name: str | None
    role: ValidRole
    created_at: str


def require_super_admin(request: Request) -> None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid super-admin token",
        )

    token = auth_header[7:]
    expected = settings.super_admin_jwt_secret
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid super-admin token",
        )


@router.post("/orgs", response_model=OrganizationResponse, dependencies=[Depends(require_super_admin)])
async def create_organization(body: CreateOrganizationRequest) -> OrganizationResponse:
    pool = get_pool()
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO organizations (name, slug)
            VALUES ($1, $2)
            RETURNING id, name, slug, is_active, created_at
            """,
            body.name,
            body.slug,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Organization slug already exists")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create organization")

    return OrganizationResponse(
        id=str(row["id"]),
        name=row["name"],
        slug=row["slug"],
        is_active=row["is_active"],
        created_at=row["created_at"].isoformat(),
    )


@router.post("/users", response_model=SuperAdminUserResponse, dependencies=[Depends(require_super_admin)])
async def create_super_admin_user(body: CreateSuperAdminUserRequest) -> SuperAdminUserResponse:
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    pool = get_pool()

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO users (org_id, email, name, password_hash, role)
            VALUES ($1, $2, $3, $4, $5::user_role)
            RETURNING id, org_id, email, name, role::text AS role, created_at
            """,
            body.org_id,
            body.email,
            body.name,
            password_hash,
            body.role,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status_code=404, detail="Organization not found")
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="User email already exists in organization")
    except asyncpg.DataError:
        raise HTTPException(status_code=400, detail="Invalid input data")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")

    return SuperAdminUserResponse(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"],
        created_at=row["created_at"].isoformat(),
    )
