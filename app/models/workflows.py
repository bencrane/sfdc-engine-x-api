from uuid import UUID

from pydantic import BaseModel, Field


class WorkflowListRequest(BaseModel):
    client_id: UUID


class WorkflowFlowSummary(BaseModel):
    id: str | None
    api_name: str
    active_version_id: str | None
    latest_version_id: str | None


class WorkflowAssignmentRuleSummary(BaseModel):
    id: str | None
    object_name: str | None
    name: str
    active: bool


class WorkflowListResponse(BaseModel):
    flows: list[WorkflowFlowSummary]
    assignment_rules: list[WorkflowAssignmentRuleSummary]


class WorkflowDeployRequest(BaseModel):
    client_id: UUID
    plan: dict
    conflict_report_id: UUID | None = None


class WorkflowDeployResponse(BaseModel):
    id: str
    status: str
    deployment_type: str
    deployed_at: str | None
    result: dict | None


class WorkflowRemoveRequest(BaseModel):
    client_id: UUID
    flow_api_names: list[str] = Field(default_factory=list)
    assignment_rule_objects: list[str] = Field(default_factory=list)


class WorkflowRemoveResponse(BaseModel):
    id: str
    status: str
    deployment_type: str
    deployed_at: str | None
    result: dict | None
