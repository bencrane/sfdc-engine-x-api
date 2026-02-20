from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.config import settings


def _nango_url(path: str, query: dict[str, str] | None = None) -> str:
    base = settings.nango_base_url.rstrip("/")
    url = f"{base}{path}"
    if query:
        return f"{url}?{urlencode(query)}"
    return url


def _nango_headers() -> dict[str, str]:
    if not settings.nango_secret_key:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "nango_not_configured",
                "message": "NANGO_SECRET_KEY is not configured",
            },
        )
    return {
        "Authorization": f"Bearer {settings.nango_secret_key}",
        "Content-Type": "application/json",
    }


def _raise_nango_error(status_code: int, payload: dict | str | None) -> None:
    if status_code == 404:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "nango_connection_not_found",
                "message": "Nango connection does not exist",
                "provider": settings.nango_provider_config_key,
                "nango_error": payload,
            },
        )
    if status_code == 424:
        raise HTTPException(
            status_code=424,
            detail={
                "code": "nango_refresh_exhausted",
                "message": "Nango could not refresh credentials",
                "provider": settings.nango_provider_config_key,
                "nango_error": payload,
            },
        )

    raise HTTPException(
        status_code=502,
        detail={
            "code": "nango_request_failed",
            "message": "Nango API request failed",
            "provider": settings.nango_provider_config_key,
            "nango_error": payload,
        },
    )


def _parse_nango_error(response: httpx.Response) -> dict | str | None:
    try:
        return response.json()
    except ValueError:
        body = response.text.strip()
        return body or None


async def create_connect_session(org_id: str, client_id: str) -> dict:
    payload = {
        "allowed_integrations": [settings.nango_provider_config_key],
        "tags": {
            "org_id": org_id,
            "client_id": client_id,
        },
    }
    url = _nango_url("/connect/sessions")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=_nango_headers(), json=payload)

    if response.status_code >= 400:
        _raise_nango_error(response.status_code, _parse_nango_error(response))

    body = response.json()
    data = body.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "nango_invalid_response",
                "message": "Nango connect session response was missing data",
                "provider": settings.nango_provider_config_key,
            },
        )

    return data


async def get_connection_credentials(connection_id: str) -> dict:
    url = _nango_url(
        f"/connections/{connection_id}",
        {"provider_config_key": settings.nango_provider_config_key},
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=_nango_headers())

    if response.status_code >= 400:
        _raise_nango_error(response.status_code, _parse_nango_error(response))

    return response.json()


async def get_valid_token(connection_id: str) -> tuple[str, str]:
    try:
        connection = await get_connection_credentials(connection_id)
    except HTTPException as exc:
        if exc.status_code in (404, 424):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "nango_connection_unavailable",
                    "message": "Salesforce connection is unavailable in Nango",
                    "provider": settings.nango_provider_config_key,
                    "nango_status_code": exc.status_code,
                    "nango_error": exc.detail,
                },
            )
        raise

    credentials = connection.get("credentials") or {}
    connection_config = connection.get("connection_config") or {}

    access_token = credentials.get("access_token")
    instance_url = connection_config.get("instance_url")
    if not access_token or not instance_url:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "nango_invalid_credentials",
                "message": "Nango connection credentials were incomplete",
                "provider": settings.nango_provider_config_key,
            },
        )

    return access_token, instance_url


async def delete_connection(connection_id: str) -> None:
    url = _nango_url(
        f"/connections/{connection_id}",
        {"provider_config_key": settings.nango_provider_config_key},
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.delete(url, headers=_nango_headers())

    if response.status_code >= 400:
        _raise_nango_error(response.status_code, _parse_nango_error(response))
