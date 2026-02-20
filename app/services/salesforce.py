import asyncio

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services import token_manager


def _sfdc_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _sfdc_base_url(instance_url: str) -> str:
    return instance_url.rstrip("/")


def _parse_salesforce_error(response: httpx.Response) -> tuple[str, str]:
    fallback_code = "salesforce_request_failed"
    fallback_message = "Salesforce API request failed"

    try:
        payload = response.json()
    except ValueError:
        body = response.text.strip()
        return fallback_code, body or fallback_message

    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return (
                str(first.get("errorCode") or fallback_code),
                str(first.get("message") or fallback_message),
            )

    if isinstance(payload, dict):
        return (
            str(payload.get("errorCode") or payload.get("code") or fallback_code),
            str(payload.get("message") or fallback_message),
        )

    return fallback_code, fallback_message


async def list_sobjects(connection_id: str) -> list[dict]:
    access_token, instance_url = await token_manager.get_valid_token(connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/"
        f"{settings.sfdc_api_version}/sobjects/"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_sfdc_headers(access_token))

    if response.status_code != 200:
        error_code, error_message = _parse_salesforce_error(response)
        raise HTTPException(
            status_code=502,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    body = response.json()
    sobjects = body.get("sobjects")
    if not isinstance(sobjects, list):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "salesforce_invalid_response",
                "message": "Salesforce list sobjects response missing sobjects",
            },
        )
    return sobjects


async def describe_sobject(
    connection_id: str,
    object_name: str,
    client: httpx.AsyncClient,
    access_token: str,
    instance_url: str,
) -> dict:
    _ = connection_id
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/"
        f"{settings.sfdc_api_version}/sobjects/{object_name}/describe/"
    )
    response = await client.get(url, headers=_sfdc_headers(access_token))
    if response.status_code != 200:
        return None
    return response.json()


async def pull_full_topology(connection_id: str) -> dict:
    sobjects = await list_sobjects(connection_id)
    object_names = [
        str(item["name"]) for item in sobjects if isinstance(item, dict) and item.get("name")
    ]
    custom_object_names = [
        object_name for object_name in object_names if object_name.endswith("__c")
    ]

    access_token, instance_url = await token_manager.get_valid_token(connection_id)
    semaphore = asyncio.Semaphore(10)

    async with httpx.AsyncClient(timeout=60.0) as client:
        async def describe_with_limit(object_name: str) -> tuple[str, dict | None]:
            async with semaphore:
                payload = await describe_sobject(
                    connection_id=connection_id,
                    object_name=object_name,
                    client=client,
                    access_token=access_token,
                    instance_url=instance_url,
                )
                return object_name, payload

        results = await asyncio.gather(
            *(describe_with_limit(object_name) for object_name in object_names)
        )

    objects: dict[str, dict] = {}
    for object_name, payload in results:
        if payload is not None:
            objects[object_name] = payload

    return {
        "objects": objects,
        "object_names": object_names,
        "custom_object_names": custom_object_names,
        "objects_count": len(object_names),
        "custom_objects_count": len(custom_object_names),
        "api_version": settings.sfdc_api_version,
    }
