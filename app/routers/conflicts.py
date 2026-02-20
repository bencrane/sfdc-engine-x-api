from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.conflicts import (
    ConflictCheckRequest,
    ConflictCheckResponse,
    ConflictFinding,
    ConflictGetRequest,
    ConflictGetResponse,
)
from app.services.conflict_checker import check_conflicts

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.post("/check", response_model=ConflictCheckResponse)
async def conflict_check(
    body: ConflictCheckRequest,
    auth=Depends(get_current_auth),
) -> ConflictCheckResponse:
    auth.assert_permission("deploy.write")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    topology_row = await pool.fetchrow(
        """
        SELECT id, snapshot
        FROM crm_topology_snapshots
        WHERE org_id = $1
          AND client_id = $2
        ORDER BY version DESC
        LIMIT 1
        """,
        auth.org_id,
        db_client_id,
    )
    if topology_row is None:
        raise HTTPException(
            status_code=400,
            detail="No topology snapshot found - run a topology pull first.",
        )

    connection_row = await pool.fetchrow(
        """
        SELECT id
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

    result = check_conflicts(
        deployment_plan=body.deployment_plan,
        topology_snapshot=dict(topology_row["snapshot"]),
    )

    row = await pool.fetchrow(
        """
        INSERT INTO crm_conflict_reports (
            org_id,
            client_id,
            connection_id,
            topology_snapshot_id,
            deployment_plan,
            findings,
            overall_severity,
            green_count,
            yellow_count,
            red_count
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::conflict_severity, $8, $9, $10)
        RETURNING id, overall_severity::text, green_count, yellow_count, red_count, findings
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        topology_row["id"],
        body.deployment_plan,
        result["findings"],
        result["overall_severity"],
        result["green_count"],
        result["yellow_count"],
        result["red_count"],
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to store conflict report")

    findings = [
        ConflictFinding(
            severity=str(finding.get("severity", "")),
            category=str(finding.get("category", "")),
            message=str(finding.get("message", "")),
        )
        for finding in row["findings"]
        if isinstance(finding, dict)
    ]

    return ConflictCheckResponse(
        id=str(row["id"]),
        overall_severity=row["overall_severity"],
        green_count=row["green_count"],
        yellow_count=row["yellow_count"],
        red_count=row["red_count"],
        findings=findings,
    )


@router.post("/get", response_model=ConflictGetResponse)
async def conflict_get(
    body: ConflictGetRequest,
    auth=Depends(get_current_auth),
) -> ConflictGetResponse:
    auth.assert_permission("deploy.write")

    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, overall_severity::text, green_count, yellow_count, red_count, findings
        FROM crm_conflict_reports
        WHERE id = $1
          AND org_id = $2
        """,
        body.id,
        auth.org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Conflict report not found")

    findings = [
        ConflictFinding(
            severity=str(finding.get("severity", "")),
            category=str(finding.get("category", "")),
            message=str(finding.get("message", "")),
        )
        for finding in row["findings"]
        if isinstance(finding, dict)
    ]

    return ConflictGetResponse(
        id=str(row["id"]),
        overall_severity=row["overall_severity"],
        green_count=row["green_count"],
        yellow_count=row["yellow_count"],
        red_count=row["red_count"],
        findings=findings,
    )
