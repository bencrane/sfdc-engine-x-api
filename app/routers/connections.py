from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.services import token_manager

router = APIRouter(prefix="/api/connections", tags=["connections"])


class ConnectionCreateRequest(BaseModel):
    client_id: UUID


class ConnectionCallbackRequest(BaseModel):
    client_id: UUID


class ConnectionListRequest(BaseModel):
    client_id: UUID | None = None


class ConnectionGetRequest(BaseModel):
    id: UUID


class ConnectionRefreshRequest(BaseModel):
    client_id: UUID


class ConnectionRevokeRequest(BaseModel):
    client_id: UUID


class ConnectSessionResponse(BaseModel):
    token: str
    expires_at: str | None = None


class ConnectionCreateResponse(BaseModel):
    id: str
    client_id: str
    status: str
    connect_session: ConnectSessionResponse


class ConnectionCallbackResponse(BaseModel):
    id: str
    client_id: str
    status: str
    instance_url: str | None


class ConnectionListItem(BaseModel):
    id: str
    client_id: str
    status: str
    instance_url: str | None
    last_used_at: str | None
    created_at: str


class ConnectionListResponse(BaseModel):
    data: list[ConnectionListItem]


class ConnectionGetResponse(BaseModel):
    id: str
    client_id: str
    status: str
    instance_url: str | None
    sfdc_org_id: str | None
    sfdc_user_id: str | None
    last_used_at: str | None
    created_at: str


class ConnectionRefreshResponse(BaseModel):
    status: str
    last_refreshed_at: str


class ConnectionRevokeResponse(BaseModel):
    status: str


def _extract_identity_ids(raw: dict) -> tuple[str | None, str | None]:
    org_id = None
    user_id = None

    if not isinstance(raw, dict):
        return None, None

    identity = raw.get("identity")
    if isinstance(identity, dict):
        org_id = identity.get("organization_id") or identity.get("org_id")
        user_id = identity.get("user_id") or identity.get("id")
    elif isinstance(identity, str):
        parts = [part for part in identity.strip("/").split("/") if part]
        if len(parts) >= 2:
            org_id = parts[-2]
            user_id = parts[-1]

    if org_id is None:
        org_id = raw.get("organization_id") or raw.get("org_id")
    if user_id is None:
        user_id = raw.get("user_id")

    return org_id, user_id


@router.post("/create", response_model=ConnectionCreateResponse)
async def create_connection(
    body: ConnectionCreateRequest,
    auth=Depends(get_current_auth),
) -> ConnectionCreateResponse:
    auth.assert_permission("connections.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    connect_session = await token_manager.create_connect_session(auth.org_id, client_id)

    row = await pool.fetchrow(
        """
        INSERT INTO crm_connections (org_id, client_id, nango_connection_id, status)
        VALUES ($1, $2, $3, 'pending'::connection_status)
        ON CONFLICT (org_id, client_id)
        DO UPDATE SET
            nango_connection_id = EXCLUDED.nango_connection_id,
            status = 'pending'::connection_status,
            error_message = NULL
        RETURNING id, client_id, status::text AS status
        """,
        auth.org_id,
        client_id,
        client_id,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create CRM connection")

    token = connect_session.get("token")
    if not token:
        raise HTTPException(status_code=502, detail="Nango connect session missing token")

    return ConnectionCreateResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        status=row["status"],
        connect_session=ConnectSessionResponse(
            token=token,
            expires_at=connect_session.get("expires_at"),
        ),
    )


@router.post("/callback", response_model=ConnectionCallbackResponse)
async def confirm_connection_callback(
    body: ConnectionCallbackRequest,
    auth=Depends(get_current_auth),
) -> ConnectionCallbackResponse:
    auth.assert_permission("connections.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    connection = await token_manager.get_connection_credentials(client_id)

    connection_config = connection.get("connection_config") or {}
    raw = connection.get("raw") or {}
    instance_url = connection_config.get("instance_url")
    sfdc_org_id, sfdc_user_id = _extract_identity_ids(raw if isinstance(raw, dict) else {})

    row = await pool.fetchrow(
        """
        UPDATE crm_connections
        SET status = 'connected'::connection_status,
            nango_connection_id = $3,
            instance_url = $4,
            sfdc_org_id = $5,
            sfdc_user_id = $6,
            error_message = NULL
        WHERE org_id = $1
          AND client_id = $2
        RETURNING id, client_id, status::text AS status, instance_url
        """,
        auth.org_id,
        client_id,
        client_id,
        instance_url,
        sfdc_org_id,
        sfdc_user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    return ConnectionCallbackResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        status=row["status"],
        instance_url=row["instance_url"],
    )


@router.post("/list", response_model=ConnectionListResponse)
async def list_connections(
    body: ConnectionListRequest,
    auth=Depends(get_current_auth),
) -> ConnectionListResponse:
    auth.assert_permission("connections.read")
    pool = get_pool()

    if body.client_id is not None:
        client_id = await validate_client_access(auth, body.client_id, pool=pool)
        rows = await pool.fetch(
            """
            SELECT id, client_id, status::text AS status, instance_url, last_used_at, created_at
            FROM crm_connections
            WHERE org_id = $1
              AND client_id = $2
            ORDER BY created_at DESC
            """,
            auth.org_id,
            client_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, client_id, status::text AS status, instance_url, last_used_at, created_at
            FROM crm_connections
            WHERE org_id = $1
            ORDER BY created_at DESC
            """,
            auth.org_id,
        )

    return ConnectionListResponse(
        data=[
            ConnectionListItem(
                id=str(row["id"]),
                client_id=str(row["client_id"]),
                status=row["status"],
                instance_url=row["instance_url"],
                last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )


@router.post("/get", response_model=ConnectionGetResponse)
async def get_connection(
    body: ConnectionGetRequest,
    auth=Depends(get_current_auth),
) -> ConnectionGetResponse:
    auth.assert_permission("connections.read")
    pool = get_pool()

    row = await pool.fetchrow(
        """
        SELECT id, client_id, status::text AS status, instance_url, sfdc_org_id, sfdc_user_id,
               last_used_at, created_at
        FROM crm_connections
        WHERE id = $1
          AND org_id = $2
        """,
        body.id,
        auth.org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    await validate_client_access(auth, row["client_id"], pool=pool)

    return ConnectionGetResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        status=row["status"],
        instance_url=row["instance_url"],
        sfdc_org_id=row["sfdc_org_id"],
        sfdc_user_id=row["sfdc_user_id"],
        last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
        created_at=row["created_at"].isoformat(),
    )


@router.post("/refresh", response_model=ConnectionRefreshResponse)
async def refresh_connection(
    body: ConnectionRefreshRequest,
    auth=Depends(get_current_auth),
) -> ConnectionRefreshResponse:
    auth.assert_permission("connections.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    try:
        await token_manager.get_connection_credentials(client_id)
    except HTTPException as exc:
        if exc.status_code == 424:
            await pool.execute(
                """
                UPDATE crm_connections
                SET status = 'expired'::connection_status
                WHERE org_id = $1
                  AND client_id = $2
                """,
                auth.org_id,
                client_id,
            )
        raise

    row = await pool.fetchrow(
        """
        UPDATE crm_connections
        SET status = 'connected'::connection_status,
            nango_connection_id = $3,
            last_refreshed_at = NOW(),
            error_message = NULL
        WHERE org_id = $1
          AND client_id = $2
        RETURNING status::text AS status, last_refreshed_at
        """,
        auth.org_id,
        client_id,
        client_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    return ConnectionRefreshResponse(
        status=row["status"],
        last_refreshed_at=row["last_refreshed_at"].isoformat(),
    )


@router.post("/revoke", response_model=ConnectionRevokeResponse)
async def revoke_connection(
    body: ConnectionRevokeRequest,
    auth=Depends(get_current_auth),
) -> ConnectionRevokeResponse:
    auth.assert_permission("connections.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    await token_manager.delete_connection(client_id)

    command_status = await pool.execute(
        """
        UPDATE crm_connections
        SET status = 'revoked'::connection_status,
            error_message = NULL
        WHERE org_id = $1
          AND client_id = $2
        """,
        auth.org_id,
        client_id,
    )
    if command_status.endswith("0"):
        raise HTTPException(status_code=404, detail="Connection not found")

    return ConnectionRevokeResponse(status="revoked")
