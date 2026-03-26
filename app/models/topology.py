from uuid import UUID

from pydantic import BaseModel


class TopologyPullRequest(BaseModel):
    client_id: UUID


class TopologyPullResponse(BaseModel):
    id: str
    client_id: str
    version: int
    objects_count: int
    custom_objects_count: int
    pulled_at: str


class TopologyGetRequest(BaseModel):
    client_id: UUID
    version: int | None = None


class TopologyGetResponse(BaseModel):
    id: str
    client_id: str
    version: int
    objects_count: int
    custom_objects_count: int
    snapshot: dict
    pulled_at: str


class TopologyHistoryRequest(BaseModel):
    client_id: UUID


class TopologyHistoryItem(BaseModel):
    id: str
    version: int
    objects_count: int
    custom_objects_count: int
    pulled_at: str


class TopologyHistoryResponse(BaseModel):
    data: list[TopologyHistoryItem]


class PicklistRequest(BaseModel):
    client_id: UUID
    object_name: str
    field_name: str
    version: int | None = None


class PicklistResponse(BaseModel):
    object_name: str
    field_name: str
    values: list[dict]


class TopologyDiffRequest(BaseModel):
    client_id: UUID
    version_a: int
    version_b: int
    object_names: list[str] | None = None


class FieldChange(BaseModel):
    name: str
    change_type: str  # "added", "removed", "modified"


class ObjectChange(BaseModel):
    name: str
    added_fields: list[str]
    removed_fields: list[str]
    changed_fields: list[FieldChange]


class TopologyDiffResponse(BaseModel):
    added_objects: list[str]
    removed_objects: list[str]
    changed_objects: list[ObjectChange]
