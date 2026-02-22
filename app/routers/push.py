from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.push import (
    PushHistoryItem,
    PushHistoryRequest,
    PushHistoryResponse,
    PushRecordsRequest,
    PushRecordsResponse,
    PushStatusRequest,
    PushStatusResponse,
    PushValidateRequest,
    PushValidateResponse,
)
from app.services import push_service

router = APIRouter(prefix="/api/push", tags=["push"])


def _format_push_error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, dict):
            code = str(detail.get("code", "push_failed"))
            message = str(detail.get("message", "Push failed"))
            return f"{code}: {message}"
        return str(detail) if detail is not None else "Push failed"
    return str(error)


def _snapshot_field_names(snapshot: object, sfdc_object: str) -> set[str]:
    if not isinstance(snapshot, dict):
        return set()
    objects = snapshot.get("objects")
    if not isinstance(objects, dict):
        return set()
    object_payload = objects.get(sfdc_object)
    if not isinstance(object_payload, dict):
        return set()
    raw_fields = object_payload.get("fields")
    if not isinstance(raw_fields, list):
        return set()

    names: set[str] = set()
    for field in raw_fields:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return names


@router.post("/records", response_model=PushRecordsResponse)
async def push_records(
    body: PushRecordsRequest,
    auth=Depends(get_current_auth),
) -> PushRecordsResponse:
    auth.assert_permission("push.write")
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

    resolved_object_type = body.object_type
    resolved_external_id_field = body.external_id_field
    field_mapping = None

    if body.canonical_object is not None:
        mapping_row = await pool.fetchrow(
            """
            SELECT field_mappings, sfdc_object, external_id_field, mapping_version
            FROM crm_field_mappings
            WHERE org_id = $1
              AND client_id = $2
              AND canonical_object = $3
              AND is_active = TRUE
            """,
            auth.org_id,
            db_client_id,
            body.canonical_object,
        )
        if mapping_row is not None:
            if (
                body.mapping_version is not None
                and int(mapping_row["mapping_version"]) != body.mapping_version
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Mapping version mismatch "
                        f"\u2014 expected {body.mapping_version}, current is "
                        f"{int(mapping_row['mapping_version'])}. "
                        "Re-fetch mapping before pushing."
                    ),
                )
            mapping_payload = mapping_row["field_mappings"]
            if isinstance(mapping_payload, dict):
                field_mapping = mapping_payload
            if not resolved_object_type:
                resolved_object_type = mapping_row["sfdc_object"]
            if not resolved_external_id_field and mapping_row["external_id_field"]:
                resolved_external_id_field = mapping_row["external_id_field"]

    if not resolved_object_type:
        raise HTTPException(status_code=400, detail="object_type is required")
    if not resolved_external_id_field:
        raise HTTPException(status_code=400, detail="external_id_field is required")

    push_row = await pool.fetchrow(
        """
        INSERT INTO crm_push_logs (
            org_id,
            client_id,
            connection_id,
            pushed_by,
            status,
            object_type,
            records_total,
            payload,
            started_at
        )
        VALUES ($1, $2, $3, $4, 'in_progress'::push_status, $5, $6, $7, NOW())
        RETURNING id, started_at
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        UUID(auth.user_id),
        resolved_object_type,
        len(body.records),
        {
            "object_type": resolved_object_type,
            "external_id_field": resolved_external_id_field,
            "canonical_object": body.canonical_object,
            "records": body.records,
        },
    )
    if push_row is None:
        raise HTTPException(status_code=500, detail="Failed to create push log")

    push_log_id = push_row["id"]

    try:
        push_result = await push_service.push_records(
            nango_connection_id=nango_connection_id,
            object_type=resolved_object_type,
            external_id_field=resolved_external_id_field,
            records=body.records,
            field_mapping=field_mapping,
            provider_config_key=connection_row["nango_provider_config_key"],
        )

        updated_row = await pool.fetchrow(
            """
            UPDATE crm_push_logs
            SET status = $1::push_status,
                records_succeeded = $2,
                records_failed = $3,
                result = $4,
                error_message = NULL,
                completed_at = NOW()
            WHERE id = $5
              AND org_id = $6
            RETURNING id, status::text AS status, records_total, records_succeeded, records_failed, completed_at
            """,
            push_result["status"],
            push_result["records_succeeded"],
            push_result["records_failed"],
            {
                "results": push_result["results"],
                "errors": push_result["errors"],
            },
            push_log_id,
            auth.org_id,
        )
    except Exception as error:
        error_message = _format_push_error_message(error)
        await pool.execute(
            """
            UPDATE crm_push_logs
            SET status = 'failed'::push_status,
                records_succeeded = 0,
                records_failed = records_total,
                error_message = $1,
                completed_at = NOW()
            WHERE id = $2
              AND org_id = $3
            """,
            error_message,
            push_log_id,
            auth.org_id,
        )
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Failed to push records") from error
    finally:
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

    if updated_row is None:
        raise HTTPException(status_code=500, detail="Failed to finalize push log")

    return PushRecordsResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        records_total=updated_row["records_total"],
        records_succeeded=updated_row["records_succeeded"],
        records_failed=updated_row["records_failed"],
        completed_at=updated_row["completed_at"].isoformat(),
    )


@router.post("/validate", response_model=PushValidateResponse)
async def push_validate(
    body: PushValidateRequest,
    auth=Depends(get_current_auth),
) -> PushValidateResponse:
    auth.assert_permission("push.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    mapping_row = await pool.fetchrow(
        """
        SELECT field_mappings, sfdc_object, mapping_version
        FROM crm_field_mappings
        WHERE org_id = $1
          AND client_id = $2
          AND canonical_object = $3
          AND is_active = TRUE
        """,
        auth.org_id,
        db_client_id,
        body.canonical_object,
    )
    if mapping_row is None:
        return PushValidateResponse(
            valid=False,
            error="No active mapping found for this canonical object",
            fields={},
        )

    mapping_payload = mapping_row["field_mappings"]
    field_mappings = mapping_payload if isinstance(mapping_payload, dict) else {}
    sfdc_object = str(mapping_row["sfdc_object"])
    topology_row = await pool.fetchrow(
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

    topology_field_names: set[str] | None = None
    if topology_row is not None:
        topology_field_names = _snapshot_field_names(topology_row["snapshot"], sfdc_object)

    field_statuses: dict[str, str] = {}
    valid = True
    for field_name in body.field_names:
        mapped_field = field_mappings.get(field_name)
        if not isinstance(mapped_field, str) or not mapped_field:
            field_statuses[field_name] = "unmapped"
            valid = False
            continue

        if topology_field_names is None:
            field_statuses[field_name] = "mapped_unverified"
            continue

        field_statuses[field_name] = (
            "mapped" if mapped_field in topology_field_names else "mapped_unverified"
        )

    return PushValidateResponse(
        valid=valid,
        mapping_version=int(mapping_row["mapping_version"]),
        sfdc_object=sfdc_object,
        fields=field_statuses,
    )


@router.post("/status", response_model=PushStatusResponse)
async def push_status(
    body: PushStatusRequest,
    auth=Depends(get_current_auth),
) -> PushStatusResponse:
    auth.assert_permission("push.write")
    pool = get_pool()

    row = await pool.fetchrow(
        """
        SELECT id, client_id, status::text AS status, object_type, records_total, records_succeeded,
               records_failed, result, error_message, started_at, completed_at
        FROM crm_push_logs
        WHERE id = $1
          AND org_id = $2
        """,
        body.id,
        auth.org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Push log not found")

    return PushStatusResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        status=row["status"],
        object_type=row["object_type"],
        records_total=row["records_total"],
        records_succeeded=row["records_succeeded"],
        records_failed=row["records_failed"],
        result=dict(row["result"]) if isinstance(row["result"], dict) else row["result"],
        error_message=row["error_message"],
        started_at=row["started_at"].isoformat() if row["started_at"] else None,
        completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
    )


@router.post("/history", response_model=PushHistoryResponse)
async def push_history(
    body: PushHistoryRequest,
    auth=Depends(get_current_auth),
) -> PushHistoryResponse:
    auth.assert_permission("push.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    rows = await pool.fetch(
        """
        SELECT id, status::text AS status, object_type, records_total, records_succeeded,
               records_failed, started_at, completed_at, created_at
        FROM crm_push_logs
        WHERE org_id = $1
          AND client_id = $2
        ORDER BY created_at DESC
        """,
        auth.org_id,
        db_client_id,
    )

    return PushHistoryResponse(
        data=[
            PushHistoryItem(
                id=str(row["id"]),
                status=row["status"],
                object_type=row["object_type"],
                records_total=row["records_total"],
                records_succeeded=row["records_succeeded"],
                records_failed=row["records_failed"],
                started_at=row["started_at"].isoformat() if row["started_at"] else None,
                completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )
