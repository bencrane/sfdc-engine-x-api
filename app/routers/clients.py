from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_auth
from app.db import get_pool

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientCreateRequest(BaseModel):
    name: str
    domain: str | None = None


class ClientGetRequest(BaseModel):
    id: UUID


class ClientsListRequest(BaseModel):
    pass


class ClientResponse(BaseModel):
    id: str
    name: str
    domain: str | None
    is_active: bool
    created_at: str


class ClientDetailResponse(ClientResponse):
    updated_at: str


class ClientsListResponse(BaseModel):
    data: list[ClientResponse]


@router.post("/create", response_model=ClientResponse)
async def create_client(
    body: ClientCreateRequest,
    auth=Depends(get_current_auth),
) -> ClientResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    row = await pool.fetchrow(
        """
        INSERT INTO clients (org_id, name, domain)
        VALUES ($1, $2, $3)
        RETURNING id, name, domain, is_active, created_at
        """,
        auth.org_id,
        body.name,
        body.domain,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create client")

    return ClientResponse(
        id=str(row["id"]),
        name=row["name"],
        domain=row["domain"],
        is_active=row["is_active"],
        created_at=row["created_at"].isoformat(),
    )


@router.post("/list", response_model=ClientsListResponse)
async def list_clients(
    _: ClientsListRequest,
    auth=Depends(get_current_auth),
) -> ClientsListResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    rows = await pool.fetch(
        """
        SELECT id, name, domain, is_active, created_at
        FROM clients
        WHERE org_id = $1
          AND is_active = TRUE
        ORDER BY created_at DESC
        """,
        auth.org_id,
    )
    return ClientsListResponse(
        data=[
            ClientResponse(
                id=str(row["id"]),
                name=row["name"],
                domain=row["domain"],
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )


@router.post("/get", response_model=ClientDetailResponse)
async def get_client(
    body: ClientGetRequest,
    auth=Depends(get_current_auth),
) -> ClientDetailResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    row = await pool.fetchrow(
        """
        SELECT id, name, domain, is_active, created_at, updated_at
        FROM clients
        WHERE id = $1
          AND org_id = $2
          AND is_active = TRUE
        """,
        body.id,
        auth.org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Client not found")

    return ClientDetailResponse(
        id=str(row["id"]),
        name=row["name"],
        domain=row["domain"],
        is_active=row["is_active"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )
