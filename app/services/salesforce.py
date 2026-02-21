import asyncio
import json
import time

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services import token_manager


def _sfdc_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _sfdc_base_url(instance_url: str) -> str:
    return instance_url.rstrip("/")


def _tooling_error_payload(
    error_code: str,
    error_message: str,
    *,
    status_code: int | None = None,
) -> dict:
    payload: dict[str, str | int | None] = {
        "code": error_code,
        "message": error_message,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    return payload


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


def _parse_tooling_errors(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        raw_errors = payload.get("errors")
        if isinstance(raw_errors, list):
            parsed = [error for error in raw_errors if isinstance(error, dict)]
            if parsed:
                return parsed
    if isinstance(payload, list):
        parsed = [error for error in payload if isinstance(error, dict)]
        if parsed:
            return parsed
    return []


def _metadata_error_payload(response: httpx.Response) -> dict:
    error_code, error_message = _parse_salesforce_error(response)
    detail: dict = {
        "code": error_code,
        "message": error_message,
        "status_code": response.status_code,
    }
    try:
        payload = response.json()
        if isinstance(payload, (dict, list)):
            detail["salesforce_response"] = payload
    except ValueError:
        body = response.text.strip()
        if body:
            detail["salesforce_response"] = body
    return detail


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


async def composite_upsert(
    nango_connection_id: str,
    object_name: str,
    external_id_field: str,
    records: list[dict],
) -> list[dict]:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        f"/composite/sobjects/{object_name}/{external_id_field}"
    )

    enriched_records = []
    for record in records:
        record_payload = dict(record)
        attributes = record_payload.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        attributes["type"] = object_name
        record_payload["attributes"] = attributes
        enriched_records.append(record_payload)

    payload = {"allOrNone": False, "records": enriched_records}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(url, headers=_sfdc_headers(access_token), json=payload)

    if response.status_code != 200:
        error_code, error_message = _parse_salesforce_error(response)
        raise HTTPException(
            status_code=502,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    response_payload = response.json()
    if not isinstance(response_payload, list):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "salesforce_invalid_response",
                "message": "Salesforce composite upsert response was not a list",
            },
        )

    return response_payload


async def tooling_create_custom_object(
    nango_connection_id: str,
    api_name: str,
    label: str,
    plural_label: str | None = None,
) -> dict:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        "/tooling/sobjects/CustomObject"
    )
    developer_name = api_name[:-3] if api_name.endswith("__c") else api_name
    payload = {
        "DeveloperName": developer_name,
        "Metadata": {
            "label": label,
            "pluralLabel": plural_label or label,
            "nameField": {"label": f"{label} Name", "type": "Text"},
            "deploymentStatus": "Deployed",
            "sharingModel": "ReadWrite",
        },
    }
    headers = {**_sfdc_headers(access_token), "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        error_code, error_message = _parse_salesforce_error(response)
        return {
            "id": None,
            "success": False,
            "errors": [
                _tooling_error_payload(
                    error_code,
                    error_message,
                    status_code=response.status_code,
                )
            ],
        }

    body = response.json()
    if not isinstance(body, dict):
        return {
            "id": None,
            "success": False,
            "errors": [
                _tooling_error_payload(
                    "salesforce_invalid_response",
                    "Tooling API custom object response was not an object",
                )
            ],
        }

    return {
        "id": body.get("id"),
        "success": bool(body.get("success", False)),
        "errors": _parse_tooling_errors(body),
    }


async def tooling_create_custom_field(
    nango_connection_id: str,
    object_name: str,
    field_api_name: str,
    metadata: dict,
) -> dict:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        "/tooling/sobjects/CustomField"
    )
    payload = {"FullName": f"{object_name}.{field_api_name}", "Metadata": metadata}
    headers = {**_sfdc_headers(access_token), "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        error_code, error_message = _parse_salesforce_error(response)
        return {
            "id": None,
            "success": False,
            "errors": [
                _tooling_error_payload(
                    error_code,
                    error_message,
                    status_code=response.status_code,
                )
            ],
        }

    body = response.json()
    if not isinstance(body, dict):
        return {
            "id": None,
            "success": False,
            "errors": [
                _tooling_error_payload(
                    "salesforce_invalid_response",
                    "Tooling API custom field response was not an object",
                )
            ],
        }

    return {
        "id": body.get("id"),
        "success": bool(body.get("success", False)),
        "errors": _parse_tooling_errors(body),
    }


async def tooling_query(nango_connection_id: str, soql: str) -> list[dict]:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        "/tooling/query"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url,
            headers=_sfdc_headers(access_token),
            params={"q": soql},
        )

    if response.status_code >= 400:
        error_code, error_message = _parse_salesforce_error(response)
        raise HTTPException(
            status_code=502,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    body = response.json()
    records = body.get("records") if isinstance(body, dict) else None
    if not isinstance(records, list):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "salesforce_invalid_response",
                "message": "Salesforce Tooling query response missing records",
            },
        )
    return [record for record in records if isinstance(record, dict)]


async def tooling_delete(
    nango_connection_id: str,
    sobject_type: str,
    record_id: str,
) -> dict:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        f"/tooling/sobjects/{sobject_type}/{record_id}"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(url, headers=_sfdc_headers(access_token))

    if response.status_code >= 400:
        error_code, error_message = _parse_salesforce_error(response)
        return {
            "id": record_id,
            "success": False,
            "errors": [
                _tooling_error_payload(
                    error_code,
                    error_message,
                    status_code=response.status_code,
                )
            ],
        }

    if response.status_code == 204:
        return {"id": record_id, "success": True, "errors": []}

    body = response.json()
    if isinstance(body, dict):
        return {
            "id": body.get("id", record_id),
            "success": bool(body.get("success", True)),
            "errors": _parse_tooling_errors(body),
        }

    return {"id": record_id, "success": True, "errors": []}


async def metadata_deploy(nango_connection_id: str, zip_bytes: bytes) -> str:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        "/metadata/deployRequest"
    )
    headers = {
        **_sfdc_headers(access_token),
        "Accept": "application/json",
    }
    entity_content = {
        "deployOptions": {
            "rollbackOnError": True,
            "singlePackage": True,
            "testLevel": "NoTestRun",
        }
    }
    files = {
        "entity_content": (None, json.dumps(entity_content), "application/json"),
        "file": ("deploy.zip", zip_bytes, "application/zip"),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, files=files)

    if response.status_code != 201:
        raise HTTPException(status_code=502, detail=_metadata_error_payload(response))

    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("id"):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "salesforce_invalid_response",
                "message": "Metadata deploy response missing deploy ID",
            },
        )

    return str(payload["id"])


async def metadata_deploy_status(nango_connection_id: str, deploy_id: str) -> dict:
    access_token, instance_url = await token_manager.get_valid_token(nango_connection_id)
    url = (
        f"{_sfdc_base_url(instance_url)}/services/data/{settings.sfdc_api_version}"
        f"/metadata/deployRequest/{deploy_id}"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url,
            headers={
                **_sfdc_headers(access_token),
                "Accept": "application/json",
            },
            params={"includeDetails": "true"},
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=_metadata_error_payload(response))

    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "salesforce_invalid_response",
                "message": "Metadata deploy status response was not an object",
            },
        )

    return payload


async def metadata_deploy_and_poll(
    nango_connection_id: str,
    zip_bytes: bytes,
    poll_interval: float = 3.0,
    timeout: float = 120.0,
) -> dict:
    deploy_id = await metadata_deploy(nango_connection_id, zip_bytes)
    deadline = time.monotonic() + timeout
    terminal_states = {"Succeeded", "Failed", "Canceled"}
    last_payload: dict | None = None

    while time.monotonic() < deadline:
        payload = await metadata_deploy_status(nango_connection_id, deploy_id)
        last_payload = payload
        deploy_result = payload.get("deployResult")
        status = (
            str(deploy_result.get("status"))
            if isinstance(deploy_result, dict)
            else str(payload.get("status") or "")
        )
        if status in terminal_states:
            return payload
        await asyncio.sleep(poll_interval)

    raise HTTPException(
        status_code=502,
        detail={
            "code": "metadata_deploy_timeout",
            "message": f"Metadata deploy did not complete within {timeout} seconds",
            "deploy_id": deploy_id,
            "last_status": (
                str(last_payload.get("deployResult", {}).get("status"))
                if isinstance(last_payload, dict)
                and isinstance(last_payload.get("deployResult"), dict)
                else None
            ),
        },
    )
