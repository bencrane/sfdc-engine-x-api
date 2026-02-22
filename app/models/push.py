from uuid import UUID

from pydantic import BaseModel


class PushRecordsRequest(BaseModel):
    client_id: UUID
    object_type: str
    external_id_field: str
    records: list[dict]
    canonical_object: str | None = None


class PushRecordsResponse(BaseModel):
    id: str
    status: str
    records_total: int
    records_succeeded: int
    records_failed: int
    completed_at: str


class PushStatusRequest(BaseModel):
    id: UUID


class PushStatusResponse(BaseModel):
    id: str
    client_id: str
    status: str
    object_type: str
    records_total: int
    records_succeeded: int
    records_failed: int
    result: dict | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None


class PushHistoryRequest(BaseModel):
    client_id: UUID


class PushHistoryItem(BaseModel):
    id: str
    status: str
    object_type: str
    records_total: int
    records_succeeded: int
    records_failed: int
    started_at: str | None
    completed_at: str | None
    created_at: str


class PushHistoryResponse(BaseModel):
    data: list[PushHistoryItem]


class PushValidateRequest(BaseModel):
    client_id: UUID
    canonical_object: str
    field_names: list[str]


class PushValidateResponse(BaseModel):
    valid: bool
    mapping_version: int | None = None
    sfdc_object: str | None = None
    error: str | None = None
    fields: dict[str, str]
