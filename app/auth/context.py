from dataclasses import dataclass, field

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "org_admin": [
        "connections.read",
        "connections.write",
        "topology.read",
        "deploy.write",
        "push.write",
        "workflows.read",
        "workflows.write",
        "org.manage",
    ],
    "company_admin": [
        "connections.read",
        "topology.read",
        "workflows.read",
    ],
    "company_member": [
        "connections.read",
        "topology.read",
    ],
}


@dataclass
class AuthContext:
    org_id: str
    user_id: str
    role: str
    permissions: list[str] = field(default_factory=list)
    client_id: str | None = None
    auth_method: str = "api_token"

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def assert_permission(self, permission: str) -> None:
        from fastapi import HTTPException

        if permission not in self.permissions:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    def assert_client_access(self, client_id: str) -> None:
        """Company-scoped users can only access their assigned client."""
        from fastapi import HTTPException

        if self.client_id is not None and self.client_id != client_id:
            raise HTTPException(status_code=404, detail="Client not found")
