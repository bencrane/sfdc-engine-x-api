from uuid import UUID

from pydantic import BaseModel


class DeployRequest(BaseModel):
    client_id: UUID
    plan: dict
    conflict_report_id: UUID | None = None


class DeployResponse(BaseModel):
    id: str
    status: str
    deployment_type: str
    deployed_at: str | None
    result: dict | None


class DeployStatusRequest(BaseModel):
    id: UUID


class DeployStatusResponse(BaseModel):
    id: str
    status: str
    deployment_type: str
    deployed_at: str | None
    result: dict | None
    plan: dict
    error_message: str | None
    rolled_back_at: str | None


class DeployHistoryRequest(BaseModel):
    client_id: UUID


class DeployHistoryItem(BaseModel):
    id: str
    deployment_type: str
    status: str
    deployed_at: str | None
    rolled_back_at: str | None
    created_at: str


class DeployHistoryResponse(BaseModel):
    data: list[DeployHistoryItem]


class RollbackRequest(BaseModel):
    id: UUID


class RollbackResponse(BaseModel):
    id: str
    status: str
    rolled_back_at: str
    result: dict | None
