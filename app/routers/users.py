import bcrypt
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreateRequest(BaseModel):
    email: str
    name: str | None = None
    password: str
    role: str
    client_id: UUID | None = None


class UsersListRequest(BaseModel):
    pass


class UserCreateResponse(BaseModel):
    id: str
    org_id: str
    email: str
    name: str | None
    role: str
    client_id: str | None
    created_at: str


class UserListItem(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    client_id: str | None
    is_active: bool
    created_at: str


class UsersListResponse(BaseModel):
    data: list[UserListItem]


def _validate_user_scope(role: str, client_id: str | None) -> None:
    company_roles = {"company_admin", "company_member"}
    if role == "org_admin" and client_id is not None:
        raise HTTPException(
            status_code=400,
            detail="org_admin users cannot have client_id",
        )
    if role in company_roles and client_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"{role} users must include client_id",
        )


@router.post("/create", response_model=UserCreateResponse)
async def create_user(
    body: UserCreateRequest,
    auth=Depends(get_current_auth),
) -> UserCreateResponse:
    auth.assert_permission("org.manage")
    _validate_user_scope(body.role, body.client_id)

    pool = get_pool()
    client_id: str | None = None
    if body.client_id is not None:
        client_id = await validate_client_access(auth, body.client_id, pool=pool)

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO users (org_id, email, name, password_hash, role, client_id)
            VALUES ($1, $2, $3, $4, $5::user_role, $6)
            RETURNING id, org_id, email, name, role::text AS role, client_id, created_at
            """,
            auth.org_id,
            body.email,
            body.name,
            password_hash,
            body.role,
            client_id,
        )
    except asyncpg.InvalidTextRepresentationError:
        raise HTTPException(status_code=400, detail="Invalid role")
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="User email already exists in organization")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")

    return UserCreateResponse(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"],
        client_id=str(row["client_id"]) if row["client_id"] else None,
        created_at=row["created_at"].isoformat(),
    )


@router.post("/list", response_model=UsersListResponse)
async def list_users(
    _: UsersListRequest,
    auth=Depends(get_current_auth),
) -> UsersListResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    rows = await pool.fetch(
        """
        SELECT id, email, name, role::text AS role, client_id, is_active, created_at
        FROM users
        WHERE org_id = $1
          AND is_active = TRUE
        ORDER BY created_at DESC
        """,
        auth.org_id,
    )

    return UsersListResponse(
        data=[
            UserListItem(
                id=str(row["id"]),
                email=row["email"],
                name=row["name"],
                role=row["role"],
                client_id=str(row["client_id"]) if row["client_id"] else None,
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )
