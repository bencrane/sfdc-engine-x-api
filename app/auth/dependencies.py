import hashlib
from uuid import UUID

from fastapi import HTTPException, Request

from app.auth.context import ROLE_PERMISSIONS, AuthContext
from app.config import settings
from app.db import get_pool

try:
    from jose import JWTError, jwt
except ImportError:
    from jose import JWTError, jwt  # type: ignore[no-redef]


async def get_current_auth(request: Request) -> AuthContext:
    token = _extract_bearer_token(request)

    auth = _try_jwt(token)
    if auth is not None:
        return auth

    auth = await _try_api_token(token)
    if auth is not None:
        return auth

    raise HTTPException(status_code=401, detail="Invalid authentication credentials")


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")
    return auth_header[7:]


def _try_jwt(token: str) -> AuthContext | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
    except JWTError:
        return None

    org_id = payload.get("org_id")
    user_id = payload.get("user_id")
    role = payload.get("role")

    if not org_id or not user_id or not role:
        return None
    if role not in ROLE_PERMISSIONS:
        return None

    return AuthContext(
        org_id=org_id,
        user_id=user_id,
        role=role,
        permissions=ROLE_PERMISSIONS[role],
        client_id=payload.get("client_id"),
        auth_method="session",
    )


async def _try_api_token(token: str) -> AuthContext | None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    pool = get_pool()

    row = await pool.fetchrow(
        """
        SELECT t.org_id, t.user_id, u.role::text, u.client_id
        FROM api_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = $1
          AND t.is_active = TRUE
          AND u.is_active = TRUE
          AND t.org_id = u.org_id
          AND (t.expires_at IS NULL OR t.expires_at > NOW())
        """,
        token_hash,
    )
    if row is None:
        return None

    await pool.execute(
        "UPDATE api_tokens SET last_used_at = NOW() WHERE token_hash = $1",
        token_hash,
    )

    role = row["role"]
    return AuthContext(
        org_id=str(row["org_id"]),
        user_id=str(row["user_id"]),
        role=role,
        permissions=ROLE_PERMISSIONS.get(role, []),
        client_id=str(row["client_id"]) if row["client_id"] else None,
        auth_method="api_token",
    )


async def validate_client_access(
    auth: AuthContext, client_id: str | UUID, pool=None
) -> str:
    """Verify client belongs to auth's org and user has access. Returns client_id as str."""
    if pool is None:
        pool = get_pool()

    cid = str(client_id)
    auth.assert_client_access(cid)

    try:
        db_client_id = UUID(cid) if isinstance(client_id, str) else client_id
        db_org_id = UUID(auth.org_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Client not found")

    row = await pool.fetchrow(
        "SELECT id FROM clients WHERE id = $1 AND org_id = $2 AND is_active = TRUE",
        db_client_id,
        db_org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Client not found")

    return cid
