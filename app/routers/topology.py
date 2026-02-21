from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.topology import (
    TopologyGetRequest,
    TopologyGetResponse,
    TopologyHistoryItem,
    TopologyHistoryRequest,
    TopologyHistoryResponse,
    TopologyPullRequest,
    TopologyPullResponse,
)
from app.services import salesforce

router = APIRouter(prefix="/api/topology", tags=["topology"])


@router.post("/pull", response_model=TopologyPullResponse)
async def pull_topology(
    body: TopologyPullRequest,
    auth=Depends(get_current_auth),
) -> TopologyPullResponse:
    auth.assert_permission("topology.read")
    auth.assert_permission("connections.write")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    connection_row = await pool.fetchrow(
        """
        SELECT id, nango_connection_id
        FROM crm_connections
        WHERE org_id = $1
          AND client_id = $2
          AND status = 'connected'
        """,
        auth.org_id,
        db_client_id,
    )
    if connection_row is None:
        raise HTTPException(status_code=400, detail="No connected Salesforce connection found")

    nango_connection_id = connection_row["nango_connection_id"]
    if not nango_connection_id:
        raise HTTPException(status_code=400, detail="Connection has no Nango connection ID")

    snapshot = await salesforce.pull_full_topology(nango_connection_id)

    version = await pool.fetchval(
        """
        SELECT COALESCE(MAX(version), 0) + 1
        FROM crm_topology_snapshots
        WHERE org_id = $1
          AND client_id = $2
        """,
        auth.org_id,
        db_client_id,
    )

    row = await pool.fetchrow(
        """
        INSERT INTO crm_topology_snapshots (
            org_id,
            client_id,
            connection_id,
            version,
            snapshot,
            objects_count,
            custom_objects_count
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, client_id, version, objects_count, custom_objects_count, pulled_at
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        version,
        snapshot,
        snapshot["objects_count"],
        snapshot["custom_objects_count"],
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to store topology snapshot")

    await pool.execute(
        """
        UPDATE crm_connections
        SET last_used_at = NOW()
        WHERE id = $1
          AND org_id = $2
        """,
        connection_row["id"],
        auth.org_id,
    )

    return TopologyPullResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        version=row["version"],
        objects_count=row["objects_count"],
        custom_objects_count=row["custom_objects_count"],
        pulled_at=row["pulled_at"].isoformat(),
    )


@router.post("/get", response_model=TopologyGetResponse)
async def get_topology(
    body: TopologyGetRequest,
    auth=Depends(get_current_auth),
) -> TopologyGetResponse:
    auth.assert_permission("topology.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    if body.version is None:
        row = await pool.fetchrow(
            """
            SELECT id, client_id, version, objects_count, custom_objects_count, snapshot, pulled_at
            FROM crm_topology_snapshots
            WHERE org_id = $1
              AND client_id = $2
            ORDER BY version DESC
            LIMIT 1
            """,
            auth.org_id,
            db_client_id,
        )
    else:
        row = await pool.fetchrow(
            """
            SELECT id, client_id, version, objects_count, custom_objects_count, snapshot, pulled_at
            FROM crm_topology_snapshots
            WHERE org_id = $1
              AND client_id = $2
              AND version = $3
            """,
            auth.org_id,
            db_client_id,
            body.version,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Topology snapshot not found")

    return TopologyGetResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        version=row["version"],
        objects_count=row["objects_count"],
        custom_objects_count=row["custom_objects_count"],
        snapshot=dict(row["snapshot"]),
        pulled_at=row["pulled_at"].isoformat(),
    )


@router.post("/history", response_model=TopologyHistoryResponse)
async def topology_history(
    body: TopologyHistoryRequest,
    auth=Depends(get_current_auth),
) -> TopologyHistoryResponse:
    auth.assert_permission("topology.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    rows = await pool.fetch(
        """
        SELECT id, version, objects_count, custom_objects_count, pulled_at
        FROM crm_topology_snapshots
        WHERE org_id = $1
          AND client_id = $2
        ORDER BY version DESC
        """,
        auth.org_id,
        db_client_id,
    )

    return TopologyHistoryResponse(
        data=[
            TopologyHistoryItem(
                id=str(row["id"]),
                version=row["version"],
                objects_count=row["objects_count"],
                custom_objects_count=row["custom_objects_count"],
                pulled_at=row["pulled_at"].isoformat(),
            )
            for row in rows
        ]
    )
