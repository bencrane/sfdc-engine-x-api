from uuid import UUID

from asyncpg.exceptions import UniqueViolationError
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.mappings import (
    MappingCreateRequest,
    MappingCreatedResponse,
    MappingDeactivateRequest,
    MappingDeactivateResponse,
    MappingGetRequest,
    MappingListRequest,
    MappingListResponse,
    MappingResponse,
    MappingUpdateRequest,
)

router = APIRouter(prefix="/api/mappings", tags=["mappings"])


def _to_mapping_response(row) -> MappingResponse:
    field_mappings = row["field_mappings"]
    normalized_field_mappings = dict(field_mappings) if isinstance(field_mappings, dict) else {}
    return MappingResponse(
        id=str(row["id"]),
        canonical_object=row["canonical_object"],
        sfdc_object=row["sfdc_object"],
        field_mappings=normalized_field_mappings,
        external_id_field=row["external_id_field"],
        mapping_version=int(row["mapping_version"]),
        updated_at=row["updated_at"].isoformat(),
    )


@router.post("/create", response_model=MappingCreatedResponse)
async def create_mapping(
    body: MappingCreateRequest,
    auth=Depends(get_current_auth),
) -> MappingCreatedResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO crm_field_mappings (
                org_id,
                client_id,
                canonical_object,
                sfdc_object,
                field_mappings,
                external_id_field,
                is_active
            )
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            RETURNING id, canonical_object, sfdc_object, field_mappings, external_id_field,
                      mapping_version, created_at
            """,
            auth.org_id,
            db_client_id,
            body.canonical_object,
            body.sfdc_object,
            body.field_mappings,
            body.external_id_field,
        )
    except UniqueViolationError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mapping already exists for this client and canonical object",
        ) from exc

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create mapping")

    field_mappings = row["field_mappings"]
    normalized_field_mappings = dict(field_mappings) if isinstance(field_mappings, dict) else {}
    return MappingCreatedResponse(
        id=str(row["id"]),
        canonical_object=row["canonical_object"],
        sfdc_object=row["sfdc_object"],
        field_mappings=normalized_field_mappings,
        external_id_field=row["external_id_field"],
        mapping_version=int(row["mapping_version"]),
        created_at=row["created_at"].isoformat(),
    )


@router.post("/get", response_model=MappingResponse)
async def get_mapping(
    body: MappingGetRequest,
    auth=Depends(get_current_auth),
) -> MappingResponse:
    auth.assert_permission("push.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    row = await pool.fetchrow(
        """
        SELECT id, canonical_object, sfdc_object, field_mappings, external_id_field,
               mapping_version, updated_at
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
    if row is None:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return _to_mapping_response(row)


@router.post("/list", response_model=MappingListResponse)
async def list_mappings(
    body: MappingListRequest,
    auth=Depends(get_current_auth),
) -> MappingListResponse:
    auth.assert_permission("push.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    rows = await pool.fetch(
        """
        SELECT id, canonical_object, sfdc_object, field_mappings, external_id_field,
               mapping_version, updated_at
        FROM crm_field_mappings
        WHERE org_id = $1
          AND client_id = $2
          AND is_active = TRUE
        ORDER BY canonical_object ASC
        """,
        auth.org_id,
        db_client_id,
    )

    return MappingListResponse(data=[_to_mapping_response(row) for row in rows])


@router.post("/update", response_model=MappingResponse)
async def update_mapping(
    body: MappingUpdateRequest,
    auth=Depends(get_current_auth),
) -> MappingResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    updates: list[str] = []
    args: list[object] = [auth.org_id, db_client_id, body.canonical_object]
    arg_index = 4

    if body.field_mappings is not None:
        updates.append(f"field_mappings = ${arg_index}")
        args.append(body.field_mappings)
        arg_index += 1
    if body.sfdc_object is not None:
        updates.append(f"sfdc_object = ${arg_index}")
        args.append(body.sfdc_object)
        arg_index += 1
    if body.external_id_field is not None:
        updates.append(f"external_id_field = ${arg_index}")
        args.append(body.external_id_field)
        arg_index += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    query = f"""
        UPDATE crm_field_mappings
        SET {", ".join(updates)}
        WHERE org_id = $1
          AND client_id = $2
          AND canonical_object = $3
          AND is_active = TRUE
        RETURNING id, canonical_object, sfdc_object, field_mappings, external_id_field,
                  mapping_version, updated_at
    """
    row = await pool.fetchrow(query, *args)
    if row is None:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return _to_mapping_response(row)


@router.post("/deactivate", response_model=MappingDeactivateResponse)
async def deactivate_mapping(
    body: MappingDeactivateRequest,
    auth=Depends(get_current_auth),
) -> MappingDeactivateResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    row = await pool.fetchrow(
        """
        UPDATE crm_field_mappings
        SET is_active = FALSE
        WHERE org_id = $1
          AND client_id = $2
          AND canonical_object = $3
          AND is_active = TRUE
        RETURNING canonical_object
        """,
        auth.org_id,
        db_client_id,
        body.canonical_object,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return MappingDeactivateResponse(success=True, canonical_object=row["canonical_object"])
