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
