from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SOQLRequest(BaseModel):
    client_id: UUID
    soql: str


class SOQLResponse(BaseModel):
    total_size: int
    done: bool
    records: list[dict]
    next_records_path: str | None = None


class QueryMoreRequest(BaseModel):
    client_id: UUID
    next_records_path: str


class SearchFilter(BaseModel):
    field: str
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "like", "in", "not_in"]
    value: str | list[str]


class SearchRequest(BaseModel):
    client_id: UUID
    object_name: str
    filters: list[SearchFilter] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=lambda: ["Id", "Name"])
    limit: int | None = None
    offset: int | None = None


class CountRequest(BaseModel):
    client_id: UUID
    object_name: str
    filters: list[SearchFilter] = Field(default_factory=list)


class CountResponse(BaseModel):
    count: int


class AssociationRequest(BaseModel):
    client_id: UUID
    source_object: Literal["Contact", "Opportunity"]
    source_ids: list[str]
    related_object: str
    related_fields: list[str]


class ContactRolesRequest(BaseModel):
    client_id: UUID
    opportunity_ids: list[str]


class CampaignMembersRequest(BaseModel):
    client_id: UUID
    campaign_id: str
    fields: list[str] | None = None


class LeadConversionsRequest(BaseModel):
    client_id: UUID
    filters: list[SearchFilter] = Field(default_factory=list)
    fields: list[str] | None = None


class PipelineRequest(BaseModel):
    client_id: UUID
    object_name: str = "Opportunity"
    field_name: str = "StageName"


class PipelineResponse(BaseModel):
    object_name: str
    field_name: str
    stages: list[dict]
