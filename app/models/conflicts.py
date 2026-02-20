from uuid import UUID

from pydantic import BaseModel


class ConflictCheckRequest(BaseModel):
    client_id: UUID
    deployment_plan: dict


class ConflictFinding(BaseModel):
    severity: str
    category: str
    message: str


class ConflictCheckResponse(BaseModel):
    id: str
    overall_severity: str
    green_count: int
    yellow_count: int
    red_count: int
    findings: list[ConflictFinding]


class ConflictGetRequest(BaseModel):
    id: UUID


class ConflictGetResponse(BaseModel):
    id: str
    overall_severity: str
    green_count: int
    yellow_count: int
    red_count: int
    findings: list[ConflictFinding]
