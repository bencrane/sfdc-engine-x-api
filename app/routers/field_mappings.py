from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.field_mappings import (
    FieldMappingDeleteRequest,
    FieldMappingDeleteResponse,
    FieldMappingGetRequest,
    FieldMappingListRequest,
    FieldMappingListResponse,
    FieldMappingResponse,
    FieldMappingSetRequest,
)

router = APIRouter(prefix="/api/field-mappings", tags=["field-mappings"])


def _to_field_mapping_response(row) -> FieldMappingResponse:
    return FieldMappingResponse(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        canonical_object=row["canonical_object"],
        sfdc_object=row["sfdc_object"],
        field_mappings=dict(row["field_mappings"]),
        external_id_field=row["external_id_field"],
        is_active=row["is_active"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


@router.post("/set", response_model=FieldMappingResponse)
async def set_field_mapping(
    body: FieldMappingSetRequest,
    auth=Depends(get_current_auth),
) -> FieldMappingResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

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
        ON CONFLICT (org_id, client_id, canonical_object)
        DO UPDATE SET
            sfdc_object = EXCLUDED.sfdc_object,
            field_mappings = EXCLUDED.field_mappings,
            external_id_field = EXCLUDED.external_id_field,
            is_active = TRUE
        RETURNING id, client_id, canonical_object, sfdc_object, field_mappings,
                  external_id_field, is_active, created_at, updated_at
        """,
        auth.org_id,
        db_client_id,
        body.canonical_object,
        body.sfdc_object,
        body.field_mappings,
        body.external_id_field,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to set field mapping")

    return _to_field_mapping_response(row)


@router.post("/list", response_model=FieldMappingListResponse)
async def list_field_mappings(
    body: FieldMappingListRequest,
    auth=Depends(get_current_auth),
) -> FieldMappingListResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    rows = await pool.fetch(
        """
        SELECT id, client_id, canonical_object, sfdc_object, field_mappings,
               external_id_field, is_active, created_at, updated_at
        FROM crm_field_mappings
        WHERE org_id = $1
          AND client_id = $2
          AND is_active = TRUE
        ORDER BY canonical_object ASC
        """,
        auth.org_id,
        db_client_id,
    )

    return FieldMappingListResponse(data=[_to_field_mapping_response(row) for row in rows])


@router.post("/get", response_model=FieldMappingResponse)
async def get_field_mapping(
    body: FieldMappingGetRequest,
    auth=Depends(get_current_auth),
) -> FieldMappingResponse:
    auth.assert_permission("org.manage")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    row = await pool.fetchrow(
        """
        SELECT id, client_id, canonical_object, sfdc_object, field_mappings,
               external_id_field, is_active, created_at, updated_at
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
        raise HTTPException(status_code=404, detail="Field mapping not found")

    return _to_field_mapping_response(row)


@router.post("/delete", response_model=FieldMappingDeleteResponse)
async def delete_field_mapping(
    body: FieldMappingDeleteRequest,
    auth=Depends(get_current_auth),
) -> FieldMappingDeleteResponse:
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
        RETURNING canonical_object, is_active
        """,
        auth.org_id,
        db_client_id,
        body.canonical_object,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Field mapping not found")

    return FieldMappingDeleteResponse(
        canonical_object=row["canonical_object"],
        is_active=row["is_active"],
    )
