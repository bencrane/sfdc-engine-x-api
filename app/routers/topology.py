from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.topology import (
    FieldChange,
    ObjectChange,
    PicklistRequest,
    PicklistResponse,
    TopologyDiffRequest,
    TopologyDiffResponse,
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
        SELECT id, nango_connection_id, nango_provider_config_key
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

    snapshot = await salesforce.pull_full_topology(
        nango_connection_id,
        provider_config_key=connection_row["nango_provider_config_key"],
    )

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


@router.post("/picklist", response_model=PicklistResponse)
async def picklist(
    body: PicklistRequest,
    auth=Depends(get_current_auth),
) -> PicklistResponse:
    auth.assert_permission("topology.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    if body.version is None:
        row = await pool.fetchrow(
            """
            SELECT snapshot
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
            SELECT snapshot
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

    snapshot = row["snapshot"]
    objects = snapshot.get("objects", {})
    obj_describe = objects.get(body.object_name)
    if obj_describe is None:
        raise HTTPException(
            status_code=404,
            detail=f"Object {body.object_name} not found in topology snapshot",
        )

    fields = obj_describe.get("fields", [])
    for field in fields:
        if isinstance(field, dict) and field.get("name") == body.field_name:
            return PicklistResponse(
                object_name=body.object_name,
                field_name=body.field_name,
                values=field.get("picklistValues", []),
            )

    raise HTTPException(
        status_code=404,
        detail=f"Field {body.field_name} not found on {body.object_name}",
    )


@router.post("/diff", response_model=TopologyDiffResponse)
async def topology_diff(
    body: TopologyDiffRequest,
    auth=Depends(get_current_auth),
) -> TopologyDiffResponse:
    auth.assert_permission("topology.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    rows = await pool.fetch(
        """
        SELECT version, snapshot
        FROM crm_topology_snapshots
        WHERE org_id = $1
          AND client_id = $2
          AND version IN ($3, $4)
        """,
        auth.org_id,
        db_client_id,
        body.version_a,
        body.version_b,
    )

    snapshots_by_version = {row["version"]: row["snapshot"] for row in rows}

    if body.version_a not in snapshots_by_version:
        raise HTTPException(
            status_code=404, detail=f"Topology snapshot version {body.version_a} not found"
        )
    if body.version_b not in snapshots_by_version:
        raise HTTPException(
            status_code=404, detail=f"Topology snapshot version {body.version_b} not found"
        )

    objects_a = snapshots_by_version[body.version_a].get("objects", {})
    objects_b = snapshots_by_version[body.version_b].get("objects", {})

    # Apply object_names filter if provided
    if body.object_names:
        filter_set = set(body.object_names)
        objects_a = {k: v for k, v in objects_a.items() if k in filter_set}
        objects_b = {k: v for k, v in objects_b.items() if k in filter_set}

    names_a = set(objects_a.keys())
    names_b = set(objects_b.keys())

    added_objects = sorted(names_b - names_a)
    removed_objects = sorted(names_a - names_b)

    changed_objects: list[ObjectChange] = []
    for obj_name in sorted(names_a & names_b):
        desc_a = objects_a[obj_name]
        desc_b = objects_b[obj_name]

        fields_a = {
            f["name"]: f
            for f in desc_a.get("fields", [])
            if isinstance(f, dict) and f.get("name")
        }
        fields_b = {
            f["name"]: f
            for f in desc_b.get("fields", [])
            if isinstance(f, dict) and f.get("name")
        }

        field_names_a = set(fields_a.keys())
        field_names_b = set(fields_b.keys())

        added_fields = sorted(field_names_b - field_names_a)
        removed_fields = sorted(field_names_a - field_names_b)

        changed_fields: list[FieldChange] = []
        for fname in sorted(field_names_a & field_names_b):
            fa = fields_a[fname]
            fb = fields_b[fname]
            if fa.get("type") != fb.get("type") or fa.get("label") != fb.get("label"):
                changed_fields.append(FieldChange(name=fname, change_type="modified"))

        if added_fields or removed_fields or changed_fields:
            changed_objects.append(
                ObjectChange(
                    name=obj_name,
                    added_fields=added_fields,
                    removed_fields=removed_fields,
                    changed_fields=changed_fields,
                )
            )

    return TopologyDiffResponse(
        added_objects=added_objects,
        removed_objects=removed_objects,
        changed_objects=changed_objects,
    )
