from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class MeResponse(BaseModel):
    org_id: str
    user_id: str
    role: str
    permissions: list[str]
    client_id: str | None
    auth_method: str


@router.get("/me", response_model=MeResponse)
async def me(auth=Depends(get_current_auth)) -> MeResponse:
    return MeResponse(
        org_id=auth.org_id,
        user_id=auth.user_id,
        role=auth.role,
        permissions=auth.permissions,
        client_id=auth.client_id,
        auth_method=auth.auth_method,
    )
