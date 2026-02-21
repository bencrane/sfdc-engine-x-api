from fastapi import HTTPException

from app.services import salesforce


def _strip_custom_suffix(api_name: str) -> str:
    return api_name[:-3] if api_name.endswith("__c") else api_name


def _soql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _normalize_error(error: object) -> dict:
    if isinstance(error, dict):
        return {
            "code": str(error.get("code") or error.get("errorCode") or "unknown_error"),
            "message": str(error.get("message") or "Unknown Salesforce error"),
        }
    return {"code": "unknown_error", "message": str(error)}


def _extract_tooling_error(response: dict) -> dict:
    errors = response.get("errors")
    if isinstance(errors, list) and errors:
        return _normalize_error(errors[0])
    return {"code": "salesforce_request_failed", "message": "Salesforce request failed"}


def _derive_relationship_name(field_api_name: str) -> str:
    base = _strip_custom_suffix(field_api_name)
    if base.endswith("_Id"):
        base = base[:-3]
    return base


def _build_picklist_values(values: list) -> list[dict]:
    normalized: list[dict] = []
    for index, value in enumerate(values):
        if isinstance(value, str):
            normalized.append(
                {
                    "fullName": value,
                    "default": index == 0,
                    "label": value,
                    "isActive": True,
                }
            )
            continue
        if isinstance(value, dict):
            full_name = str(
                value.get("fullName")
                or value.get("value")
                or value.get("label")
                or f"Value_{index + 1}"
            )
            normalized.append(
                {
                    "fullName": full_name,
                    "default": bool(value.get("default", index == 0)),
                    "label": str(value.get("label") or full_name),
                    "isActive": bool(value.get("isActive", True)),
                }
            )
    return normalized


def _build_field_metadata(field: dict) -> dict:
    field_type = str(field.get("type", "")).strip()
    label = str(field.get("label") or field.get("api_name") or "Field")
    metadata: dict = {"type": field_type, "label": label}

    if "required" in field:
        metadata["required"] = bool(field["required"])

    if field_type == "Text":
        metadata["length"] = int(field.get("length", 255))
    elif field_type in {"Number", "Currency", "Percent"}:
        metadata["precision"] = int(field.get("precision", 18))
        metadata["scale"] = int(field.get("scale", 2))
    elif field_type == "Checkbox":
        metadata["defaultValue"] = bool(field.get("default", field.get("default_value", False)))
    elif field_type == "Picklist":
        values = field.get("values") if isinstance(field.get("values"), list) else []
        metadata["valueSet"] = {
            "restricted": bool(field.get("restricted", True)),
            "valueSetDefinition": {
                "sorted": bool(field.get("sorted", False)),
                "value": _build_picklist_values(values),
            },
        }
    elif field_type == "LongTextArea":
        metadata["length"] = int(field.get("length", 32768))
        metadata["visibleLines"] = int(field.get("visible_lines", field.get("visibleLines", 3)))
    elif field_type == "Lookup":
        metadata["referenceTo"] = str(field.get("related_to") or field.get("referenceTo") or "")
        metadata["relationshipName"] = str(
            field.get("relationship_name")
            or field.get("relationshipName")
            or _derive_relationship_name(str(field.get("api_name", "")))
        )
        metadata["deleteConstraint"] = str(field.get("delete_constraint") or field.get("deleteConstraint") or "SetNull")
    elif field_type == "MasterDetail":
        metadata["referenceTo"] = str(field.get("related_to") or field.get("referenceTo") or "")
        metadata["relationshipName"] = str(
            field.get("relationship_name")
            or field.get("relationshipName")
            or _derive_relationship_name(str(field.get("api_name", "")))
        )

    return metadata


def _resolve_deployment_status(total: int, succeeded: int) -> str:
    if total == 0 or succeeded == 0:
        return "failed"
    if succeeded == total:
        return "succeeded"
    return "partial"


async def execute_deployment(nango_connection_id: str, plan: dict) -> dict:
    components: list[dict] = []
    objects_created = 0
    fields_created = 0
    relationships_created = 0

    custom_objects = plan.get("custom_objects")
    if not isinstance(custom_objects, list):
        custom_objects = []

    for custom_object in custom_objects:
        if not isinstance(custom_object, dict):
            continue

        object_api_name = str(custom_object.get("api_name") or "").strip()
        object_label = str(custom_object.get("label") or object_api_name)
        object_plural_label = custom_object.get("plural_label")
        if not object_api_name:
            components.append(
                {
                    "type": "custom_object",
                    "api_name": "",
                    "success": False,
                    "error": {
                        "code": "invalid_plan",
                        "message": "Custom object entry is missing api_name",
                    },
                }
            )
            continue

        object_response = await salesforce.tooling_create_custom_object(
            nango_connection_id=nango_connection_id,
            api_name=object_api_name,
            label=object_label,
            plural_label=str(object_plural_label) if object_plural_label is not None else None,
        )
        object_success = bool(object_response.get("success"))
        object_component: dict = {
            "type": "custom_object",
            "api_name": object_api_name,
            "success": object_success,
            "sfdc_id": object_response.get("id"),
        }
        if not object_success:
            object_component["error"] = _extract_tooling_error(object_response)
        components.append(object_component)

        if not object_success:
            continue

        objects_created += 1

        fields = custom_object.get("fields")
        if isinstance(fields, list):
            for field in fields:
                if not isinstance(field, dict):
                    continue
                field_api_name = str(field.get("api_name") or "").strip()
                if not field_api_name:
                    components.append(
                        {
                            "type": "custom_field",
                            "api_name": f"{object_api_name}.",
                            "success": False,
                            "error": {
                                "code": "invalid_plan",
                                "message": f"Field entry for {object_api_name} is missing api_name",
                            },
                        }
                    )
                    continue

                field_response = await salesforce.tooling_create_custom_field(
                    nango_connection_id=nango_connection_id,
                    object_name=object_api_name,
                    field_api_name=field_api_name,
                    metadata=_build_field_metadata(field),
                )
                field_success = bool(field_response.get("success"))
                field_component: dict = {
                    "type": "custom_field",
                    "api_name": f"{object_api_name}.{field_api_name}",
                    "success": field_success,
                    "sfdc_id": field_response.get("id"),
                }
                if not field_success:
                    field_component["error"] = _extract_tooling_error(field_response)
                else:
                    fields_created += 1
                components.append(field_component)

        relationships = custom_object.get("relationships")
        if isinstance(relationships, list):
            for relationship in relationships:
                if not isinstance(relationship, dict):
                    continue
                relationship_api_name = str(relationship.get("api_name") or "").strip()
                if not relationship_api_name:
                    components.append(
                        {
                            "type": "relationship",
                            "api_name": f"{object_api_name}.",
                            "success": False,
                            "error": {
                                "code": "invalid_plan",
                                "message": f"Relationship entry for {object_api_name} is missing api_name",
                            },
                        }
                    )
                    continue

                relationship_response = await salesforce.tooling_create_custom_field(
                    nango_connection_id=nango_connection_id,
                    object_name=object_api_name,
                    field_api_name=relationship_api_name,
                    metadata=_build_field_metadata(relationship),
                )
                relationship_success = bool(relationship_response.get("success"))
                relationship_component: dict = {
                    "type": "relationship",
                    "api_name": f"{object_api_name}.{relationship_api_name}",
                    "success": relationship_success,
                    "sfdc_id": relationship_response.get("id"),
                }
                if not relationship_success:
                    relationship_component["error"] = _extract_tooling_error(relationship_response)
                else:
                    relationships_created += 1
                components.append(relationship_component)

    standard_object_fields = plan.get("standard_object_fields")
    if not isinstance(standard_object_fields, list):
        standard_object_fields = []

    for entry in standard_object_fields:
        if not isinstance(entry, dict):
            continue
        object_name = str(entry.get("object") or "").strip()
        if not object_name:
            continue
        fields = entry.get("fields")
        if not isinstance(fields, list):
            continue

        for field in fields:
            if not isinstance(field, dict):
                continue
            field_api_name = str(field.get("api_name") or "").strip()
            if not field_api_name:
                components.append(
                    {
                        "type": "custom_field",
                        "api_name": f"{object_name}.",
                        "success": False,
                        "error": {
                            "code": "invalid_plan",
                            "message": f"Field entry for {object_name} is missing api_name",
                        },
                    }
                )
                continue

            field_response = await salesforce.tooling_create_custom_field(
                nango_connection_id=nango_connection_id,
                object_name=object_name,
                field_api_name=field_api_name,
                metadata=_build_field_metadata(field),
            )
            field_success = bool(field_response.get("success"))
            field_component: dict = {
                "type": "custom_field",
                "api_name": f"{object_name}.{field_api_name}",
                "success": field_success,
                "sfdc_id": field_response.get("id"),
            }
            if not field_success:
                field_component["error"] = _extract_tooling_error(field_response)
            else:
                fields_created += 1
            components.append(field_component)

    total_components = len(components)
    successful_components = sum(1 for component in components if component.get("success"))
    return {
        "status": _resolve_deployment_status(total_components, successful_components),
        "objects_created": objects_created,
        "fields_created": fields_created,
        "relationships_created": relationships_created,
        "components": components,
    }


async def _resolve_field_id(nango_connection_id: str, full_name: str) -> str | None:
    if "." not in full_name:
        return None
    object_name, field_api_name = full_name.split(".", 1)
    developer_name = _strip_custom_suffix(field_api_name)
    soql = (
        "SELECT Id FROM CustomField "
        f"WHERE DeveloperName = '{_soql_escape(developer_name)}' "
        f"AND TableEnumOrId = '{_soql_escape(object_name)}' "
        "ORDER BY CreatedDate DESC LIMIT 1"
    )
    records = await salesforce.tooling_query(nango_connection_id, soql)
    if not records:
        return None
    record_id = records[0].get("Id")
    return str(record_id) if record_id else None


async def _resolve_object_id(nango_connection_id: str, object_api_name: str) -> str | None:
    developer_name = _strip_custom_suffix(object_api_name)
    soql = (
        "SELECT Id FROM CustomObject "
        f"WHERE DeveloperName = '{_soql_escape(developer_name)}' "
        "ORDER BY CreatedDate DESC LIMIT 1"
    )
    records = await salesforce.tooling_query(nango_connection_id, soql)
    if not records:
        return None
    record_id = records[0].get("Id")
    return str(record_id) if record_id else None


async def _rollback_component(nango_connection_id: str, component: dict) -> dict:
    component_type = str(component.get("type", ""))
    api_name = str(component.get("api_name") or "")
    resolved_id = component.get("sfdc_id")

    try:
        if component_type in {"custom_field", "relationship"}:
            if not resolved_id and api_name:
                resolved_id = await _resolve_field_id(nango_connection_id, api_name)
            if not resolved_id:
                return {
                    "type": component_type,
                    "api_name": api_name,
                    "success": False,
                    "error": {
                        "code": "not_found",
                        "message": "Could not resolve Salesforce field ID for rollback",
                    },
                }

            delete_result = await salesforce.tooling_delete(
                nango_connection_id=nango_connection_id,
                sobject_type="CustomField",
                record_id=str(resolved_id),
            )
            rollback_result: dict = {
                "type": component_type,
                "api_name": api_name,
                "success": bool(delete_result.get("success")),
                "sfdc_id": str(resolved_id),
            }
            if not rollback_result["success"]:
                rollback_result["error"] = _extract_tooling_error(delete_result)
            return rollback_result

        if component_type == "custom_object":
            if not resolved_id and api_name:
                resolved_id = await _resolve_object_id(nango_connection_id, api_name)
            if not resolved_id:
                return {
                    "type": component_type,
                    "api_name": api_name,
                    "success": False,
                    "error": {
                        "code": "not_found",
                        "message": "Could not resolve Salesforce object ID for rollback",
                    },
                }

            delete_result = await salesforce.tooling_delete(
                nango_connection_id=nango_connection_id,
                sobject_type="CustomObject",
                record_id=str(resolved_id),
            )
            rollback_result = {
                "type": component_type,
                "api_name": api_name,
                "success": bool(delete_result.get("success")),
                "sfdc_id": str(resolved_id),
            }
            if not rollback_result["success"]:
                rollback_result["error"] = _extract_tooling_error(delete_result)
            return rollback_result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return {
            "type": component_type,
            "api_name": api_name,
            "success": False,
            "error": _normalize_error(detail),
        }

    return {
        "type": component_type,
        "api_name": api_name,
        "success": False,
        "error": {
            "code": "unsupported_component",
            "message": f"Rollback is not supported for component type {component_type}",
        },
    }


async def execute_rollback(nango_connection_id: str, deployment_result: dict) -> dict:
    components = deployment_result.get("components")
    if not isinstance(components, list):
        components = []

    successful_components = [
        component
        for component in components
        if isinstance(component, dict) and bool(component.get("success"))
    ]
    field_like_components = [
        component
        for component in successful_components
        if str(component.get("type")) in {"custom_field", "relationship"}
    ]
    object_components = [
        component
        for component in successful_components
        if str(component.get("type")) == "custom_object"
    ]

    rollback_components: list[dict] = []

    for component in reversed(field_like_components):
        rollback_components.append(
            await _rollback_component(
                nango_connection_id=nango_connection_id,
                component=component,
            )
        )

    for component in reversed(object_components):
        rollback_components.append(
            await _rollback_component(
                nango_connection_id=nango_connection_id,
                component=component,
            )
        )

    total_components = len(rollback_components)
    successful_count = sum(1 for component in rollback_components if component.get("success"))
    return {
        "status": _resolve_deployment_status(total_components, successful_count),
        "components": rollback_components,
        "rolled_back_components": successful_count,
        "failed_components": total_components - successful_count,
    }
