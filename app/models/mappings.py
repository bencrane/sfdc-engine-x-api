from uuid import UUID

from pydantic import BaseModel


class MappingCreateRequest(BaseModel):
    client_id: UUID
    canonical_object: str
    sfdc_object: str
    field_mappings: dict[str, str]
    external_id_field: str | None = None


class MappingGetRequest(BaseModel):
    client_id: UUID
    canonical_object: str


class MappingListRequest(BaseModel):
    client_id: UUID


class MappingUpdateRequest(BaseModel):
    client_id: UUID
    canonical_object: str
    field_mappings: dict[str, str] | None = None
    sfdc_object: str | None = None
    external_id_field: str | None = None


class MappingDeactivateRequest(BaseModel):
    client_id: UUID
    canonical_object: str


class MappingCreatedResponse(BaseModel):
    id: str
    canonical_object: str
    sfdc_object: str
    field_mappings: dict[str, str]
    external_id_field: str | None
    mapping_version: int
    created_at: str


class MappingResponse(BaseModel):
    id: str
    canonical_object: str
    sfdc_object: str
    field_mappings: dict[str, str]
    external_id_field: str | None
    mapping_version: int
    updated_at: str


class MappingListResponse(BaseModel):
    data: list[MappingResponse]


class MappingDeactivateResponse(BaseModel):
    success: bool
    canonical_object: str
