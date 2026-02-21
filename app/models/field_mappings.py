from uuid import UUID

from pydantic import BaseModel


class FieldMappingSetRequest(BaseModel):
    client_id: UUID
    canonical_object: str
    sfdc_object: str
    field_mappings: dict
    external_id_field: str | None = None


class FieldMappingResponse(BaseModel):
    id: str
    client_id: str
    canonical_object: str
    sfdc_object: str
    field_mappings: dict
    external_id_field: str | None
    is_active: bool
    created_at: str
    updated_at: str


class FieldMappingListRequest(BaseModel):
    client_id: UUID


class FieldMappingListResponse(BaseModel):
    data: list[FieldMappingResponse]


class FieldMappingGetRequest(BaseModel):
    client_id: UUID
    canonical_object: str


class FieldMappingDeleteRequest(BaseModel):
    client_id: UUID
    canonical_object: str


class FieldMappingDeleteResponse(BaseModel):
    canonical_object: str
    is_active: bool
