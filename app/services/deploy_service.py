import logging

from fastapi import HTTPException

from app.services import metadata_builder, salesforce
from app.services.deploy_validators import (
    validate_analytics_plan,
    validate_custom_object_plan,
    validate_workflow_plan,
)

logger = logging.getLogger(__name__)


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


def _as_dict_list(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _metadata_status(metadata_result: dict) -> str:
    deploy_result = metadata_result.get("deployResult")
    if isinstance(deploy_result, dict):
        status = deploy_result.get("status")
        if status:
            return str(status)
    status = metadata_result.get("status")
    return str(status) if status else "Unknown"


def _metadata_component_maps(metadata_result: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    deploy_result = metadata_result.get("deployResult")
    if not isinstance(deploy_result, dict):
        return {}, {}
    details = deploy_result.get("details")
    if not isinstance(details, dict):
        return {}, {}

    success_map: dict[str, dict] = {}
    failure_map: dict[str, dict] = {}

    for component in _as_dict_list(details.get("componentSuccesses")):
        full_name = str(component.get("fullName") or "").strip()
        if full_name:
            success_map[full_name] = component

    for component in _as_dict_list(details.get("componentFailures")):
        full_name = str(component.get("fullName") or "").strip()
        if full_name:
            failure_map[full_name] = component

    return success_map, failure_map


def _metadata_failure_to_error(failure: dict) -> dict:
    code = str(failure.get("problemType") or failure.get("errorCode") or "metadata_deploy_failed")
    message = str(
        failure.get("problem")
        or failure.get("errorMessage")
        or failure.get("message")
        or "Metadata deploy failed"
    )
    return {"code": code, "message": message}


def _metadata_failure_component(
    component_type: str,
    api_name: str,
    detail: object,
) -> dict:
    error = _normalize_error(detail if isinstance(detail, dict) else {"message": str(detail)})
    return {
        "type": component_type,
        "api_name": api_name,
        "success": False,
        "error": error,
    }


def _workflow_metadata_components(
    plan: dict,
) -> tuple[list[dict], list[dict], list[dict]]:
    components: list[dict] = []

    raw_flows = plan.get("flows")
    if not isinstance(raw_flows, list):
        raw_flows = []

    raw_assignment_rules = plan.get("assignment_rules")
    if not isinstance(raw_assignment_rules, list):
        raw_assignment_rules = []

    valid_flows: list[dict] = []
    for flow in raw_flows:
        if not isinstance(flow, dict):
            continue
        flow_api_name = str(flow.get("api_name") or "").strip()
        if not flow_api_name:
            components.append(
                {
                    "type": "flow",
                    "api_name": "",
                    "success": False,
                    "error": {
                        "code": "invalid_plan",
                        "message": "Flow entry is missing api_name",
                    },
                }
            )
            continue
        valid_flows.append(flow)

    valid_assignment_rules: list[dict] = []
    for assignment_rule in raw_assignment_rules:
        if not isinstance(assignment_rule, dict):
            continue
        object_name = str(
            assignment_rule.get("object")
            or assignment_rule.get("object_api_name")
            or assignment_rule.get("api_name")
            or ""
        ).strip()
        if not object_name:
            components.append(
                {
                    "type": "assignment_rule",
                    "api_name": "",
                    "success": False,
                    "error": {
                        "code": "invalid_plan",
                        "message": "Assignment rule entry is missing object/object_api_name",
                    },
                }
            )
            continue
        valid_assignment_rules.append(assignment_rule)

    return components, valid_flows, valid_assignment_rules


async def execute_workflow_deployment(
    nango_connection_id: str,
    plan: dict,
    provider_config_key: str | None = None,
) -> dict:
    validation_errors = validate_workflow_plan(plan)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_deploy_plan", "errors": validation_errors},
        )

    components, valid_flows, valid_assignment_rules = _workflow_metadata_components(plan)

    planned_components: list[tuple[str, str]] = []
    for flow in valid_flows:
        planned_components.append(("flow", str(flow.get("api_name")).strip()))
    for assignment_rule in valid_assignment_rules:
        object_name = str(
            assignment_rule.get("object")
            or assignment_rule.get("object_api_name")
            or assignment_rule.get("api_name")
            or ""
        ).strip()
        planned_components.append(("assignment_rule", object_name))

    flows_deployed = 0
    assignment_rules_deployed = 0

    if valid_flows or valid_assignment_rules:
        try:
            zip_bytes = metadata_builder.build_workflow_deploy_zip(
                flows=valid_flows,
                assignment_rules=valid_assignment_rules,
            )
            metadata_result = await salesforce.metadata_deploy_and_poll(
                nango_connection_id=nango_connection_id,
                zip_bytes=zip_bytes,
                provider_config_key=provider_config_key,
            )
            deploy_status = _metadata_status(metadata_result)
            success_map, failure_map = _metadata_component_maps(metadata_result)

            for component_type, api_name in planned_components:
                failed_component = failure_map.get(api_name)
                successful_component = success_map.get(api_name)
                success = bool(successful_component) and not bool(failed_component)
                if not success and not failed_component and deploy_status == "Succeeded":
                    success = True

                component_result: dict = {
                    "type": component_type,
                    "api_name": api_name,
                    "success": success,
                    "sfdc_id": (
                        (successful_component or {}).get("id")
                        or (successful_component or {}).get("componentId")
                    ),
                }
                if not success:
                    if failed_component:
                        component_result["error"] = _metadata_failure_to_error(failed_component)
                    else:
                        component_result["error"] = {
                            "code": "metadata_deploy_failed",
                            "message": f"Metadata deploy ended with status {deploy_status}",
                        }
                else:
                    if component_type == "flow":
                        flows_deployed += 1
                    elif component_type == "assignment_rule":
                        assignment_rules_deployed += 1

                components.append(component_result)
        except HTTPException as exc:
            for component_type, api_name in planned_components:
                components.append(
                    _metadata_failure_component(
                        component_type=component_type,
                        api_name=api_name,
                        detail=exc.detail,
                    )
                )

    total_components = len(components)
    successful_components = sum(1 for component in components if component.get("success"))
    return {
        "status": _resolve_deployment_status(total_components, successful_components),
        "flows_deployed": flows_deployed,
        "assignment_rules_deployed": assignment_rules_deployed,
        "components": components,
    }


async def execute_workflow_removal(
    nango_connection_id: str,
    flow_api_names: list[str],
    assignment_rule_objects: list[str],
    provider_config_key: str | None = None,
) -> dict:
    normalized_flow_names = [str(name).strip() for name in flow_api_names if str(name).strip()]
    normalized_assignment_objects = [
        str(name).strip() for name in assignment_rule_objects if str(name).strip()
    ]

    planned_components: list[tuple[str, str]] = []
    planned_components.extend(("flow", name) for name in normalized_flow_names)
    planned_components.extend(("assignment_rule", name) for name in normalized_assignment_objects)

    components: list[dict] = []
    flows_removed = 0
    assignment_rules_removed = 0

    if planned_components:
        try:
            zip_bytes = metadata_builder.build_workflow_destructive_deploy_zip(
                flow_api_names=normalized_flow_names,
                assignment_rule_objects=normalized_assignment_objects,
            )
            metadata_result = await salesforce.metadata_deploy_and_poll(
                nango_connection_id=nango_connection_id,
                zip_bytes=zip_bytes,
                provider_config_key=provider_config_key,
            )
            deploy_status = _metadata_status(metadata_result)
            success_map, failure_map = _metadata_component_maps(metadata_result)

            for component_type, api_name in planned_components:
                failed_component = failure_map.get(api_name)
                successful_component = success_map.get(api_name)
                success = bool(successful_component) and not bool(failed_component)
                if not success and not failed_component and deploy_status == "Succeeded":
                    success = True

                component_result: dict = {
                    "type": component_type,
                    "api_name": api_name,
                    "success": success,
                    "sfdc_id": (
                        (successful_component or {}).get("id")
                        or (successful_component or {}).get("componentId")
                    ),
                }
                if not success:
                    if failed_component:
                        component_result["error"] = _metadata_failure_to_error(failed_component)
                    else:
                        component_result["error"] = {
                            "code": "metadata_deploy_failed",
                            "message": f"Destructive deploy ended with status {deploy_status}",
                        }
                else:
                    if component_type == "flow":
                        flows_removed += 1
                    elif component_type == "assignment_rule":
                        assignment_rules_removed += 1

                components.append(component_result)
        except HTTPException as exc:
            for component_type, api_name in planned_components:
                components.append(
                    _metadata_failure_component(
                        component_type=component_type,
                        api_name=api_name,
                        detail=exc.detail,
                    )
                )

    total_components = len(components)
    successful_components = sum(1 for component in components if component.get("success"))
    return {
        "status": _resolve_deployment_status(total_components, successful_components),
        "flows_removed": flows_removed,
        "assignment_rules_removed": assignment_rules_removed,
        "components": components,
    }


async def execute_analytics_deployment(
    nango_connection_id: str,
    plan: dict,
    provider_config_key: str | None = None,
) -> dict:
    validation_errors = validate_analytics_plan(plan)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_deploy_plan", "errors": validation_errors},
        )

    report_folders_raw = plan.get("report_folders")
    if not isinstance(report_folders_raw, list):
        report_folders_raw = []
    dashboard_folders_raw = plan.get("dashboard_folders")
    if not isinstance(dashboard_folders_raw, list):
        dashboard_folders_raw = []
    reports_raw = plan.get("reports")
    if not isinstance(reports_raw, list):
        reports_raw = []
    dashboards_raw = plan.get("dashboards")
    if not isinstance(dashboards_raw, list):
        dashboards_raw = []

    report_folders = [
        folder
        for folder in report_folders_raw
        if isinstance(folder, dict) and str(folder.get("api_name") or "").strip()
    ]
    dashboard_folders = [
        folder
        for folder in dashboard_folders_raw
        if isinstance(folder, dict) and str(folder.get("api_name") or "").strip()
    ]
    reports = [
        report
        for report in reports_raw
        if isinstance(report, dict)
        and str(report.get("api_name") or "").strip()
        and str(report.get("folder") or "").strip()
    ]
    dashboards = [
        dashboard
        for dashboard in dashboards_raw
        if isinstance(dashboard, dict)
        and str(dashboard.get("api_name") or "").strip()
        and str(dashboard.get("folder") or "").strip()
    ]

    planned_components: list[tuple[str, str]] = []
    planned_components.extend(
        ("report_folder", str(folder.get("api_name") or "").strip())
        for folder in report_folders
    )
    planned_components.extend(
        ("dashboard_folder", str(folder.get("api_name") or "").strip())
        for folder in dashboard_folders
    )
    planned_components.extend(
        (
            "report",
            f"{str(report.get('folder') or '').strip()}/{str(report.get('api_name') or '').strip()}",
        )
        for report in reports
    )
    planned_components.extend(
        (
            "dashboard",
            f"{str(dashboard.get('folder') or '').strip()}/{str(dashboard.get('api_name') or '').strip()}",
        )
        for dashboard in dashboards
    )

    components: list[dict] = []
    reports_deployed = 0
    dashboards_deployed = 0
    folders_created = 0

    if planned_components:
        try:
            zip_bytes = metadata_builder.build_analytics_deploy_zip(plan)
            metadata_result = await salesforce.metadata_deploy_and_poll(
                nango_connection_id=nango_connection_id,
                zip_bytes=zip_bytes,
                provider_config_key=provider_config_key,
            )
            deploy_status = _metadata_status(metadata_result)
            success_map, failure_map = _metadata_component_maps(metadata_result)

            for component_type, full_name in planned_components:
                failed_component = failure_map.get(full_name)
                successful_component = success_map.get(full_name)
                success = bool(successful_component) and not bool(failed_component)
                if not success and not failed_component and deploy_status == "Succeeded":
                    success = True

                component_result: dict = {
                    "type": component_type,
                    "api_name": full_name,
                    "success": success,
                    "sfdc_id": (
                        (successful_component or {}).get("id")
                        or (successful_component or {}).get("componentId")
                    ),
                }
                if not success:
                    if failed_component:
                        component_result["error"] = _metadata_failure_to_error(failed_component)
                    else:
                        component_result["error"] = {
                            "code": "metadata_deploy_failed",
                            "message": f"Metadata deploy ended with status {deploy_status}",
                        }
                else:
                    if component_type == "report":
                        reports_deployed += 1
                    elif component_type == "dashboard":
                        dashboards_deployed += 1
                    elif component_type in {"report_folder", "dashboard_folder"}:
                        folders_created += 1

                components.append(component_result)
        except HTTPException as exc:
            for component_type, full_name in planned_components:
                components.append(
                    _metadata_failure_component(
                        component_type=component_type,
                        api_name=full_name,
                        detail=exc.detail,
                    )
                )

    total_components = len(components)
    successful_components = sum(1 for component in components if component.get("success"))
    return {
        "status": _resolve_deployment_status(total_components, successful_components),
        "reports_deployed": reports_deployed,
        "dashboards_deployed": dashboards_deployed,
        "folders_created": folders_created,
        "components": components,
    }


async def execute_analytics_rollback(
    nango_connection_id: str,
    deployment_result: dict,
    provider_config_key: str | None = None,
) -> dict:
    components = deployment_result.get("components")
    if not isinstance(components, list):
        components = []

    successful_components = [
        component
        for component in components
        if isinstance(component, dict) and bool(component.get("success"))
    ]

    dashboards = list(
        dict.fromkeys(
            str(component.get("api_name") or "").strip()
            for component in successful_components
            if str(component.get("type") or "") == "dashboard"
            and str(component.get("api_name") or "").strip()
        )
    )
    reports = list(
        dict.fromkeys(
            str(component.get("api_name") or "").strip()
            for component in successful_components
            if str(component.get("type") or "") == "report"
            and str(component.get("api_name") or "").strip()
        )
    )
    dashboard_folders = list(
        dict.fromkeys(
            str(component.get("api_name") or "").strip()
            for component in successful_components
            if str(component.get("type") or "") == "dashboard_folder"
            and str(component.get("api_name") or "").strip()
        )
    )
    report_folders = list(
        dict.fromkeys(
            str(component.get("api_name") or "").strip()
            for component in successful_components
            if str(component.get("type") or "") == "report_folder"
            and str(component.get("api_name") or "").strip()
        )
    )

    planned_components: list[tuple[str, str]] = []
    planned_components.extend(("dashboard", full_name) for full_name in dashboards)
    planned_components.extend(("report", full_name) for full_name in reports)
    planned_components.extend(("dashboard_folder", full_name) for full_name in dashboard_folders)
    planned_components.extend(("report_folder", full_name) for full_name in report_folders)

    rollback_components: list[dict] = []
    if planned_components:
        try:
            zip_bytes = metadata_builder.build_analytics_destructive_deploy_zip(
                report_folders=report_folders,
                dashboard_folders=dashboard_folders,
                reports=reports,
                dashboards=dashboards,
            )
            metadata_result = await salesforce.metadata_deploy_and_poll(
                nango_connection_id=nango_connection_id,
                zip_bytes=zip_bytes,
                provider_config_key=provider_config_key,
            )
            deploy_status = _metadata_status(metadata_result)
            success_map, failure_map = _metadata_component_maps(metadata_result)

            for component_type, full_name in planned_components:
                failed_component = failure_map.get(full_name)
                successful_component = success_map.get(full_name)
                success = bool(successful_component) and not bool(failed_component)
                if not success and not failed_component and deploy_status == "Succeeded":
                    success = True

                rollback_result: dict = {
                    "type": component_type,
                    "api_name": full_name,
                    "success": success,
                    "sfdc_id": (
                        (successful_component or {}).get("id")
                        or (successful_component or {}).get("componentId")
                    ),
                }
                if not success:
                    if failed_component:
                        rollback_result["error"] = _metadata_failure_to_error(failed_component)
                    else:
                        rollback_result["error"] = {
                            "code": "metadata_deploy_failed",
                            "message": f"Destructive deploy ended with status {deploy_status}",
                        }
                rollback_components.append(rollback_result)
        except HTTPException as exc:
            for component_type, full_name in planned_components:
                rollback_components.append(
                    _metadata_failure_component(
                        component_type=component_type,
                        api_name=full_name,
                        detail=exc.detail,
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


async def _best_effort_auto_map_custom_objects(
    *,
    pool,
    org_id: str,
    client_id,
    components: list[dict],
) -> None:
    object_to_fields: dict[str, set[str]] = {}
    successful_objects: set[str] = set()

    for component in components:
        if not isinstance(component, dict) or not component.get("success"):
            continue

        component_type = str(component.get("type") or "")
        api_name = str(component.get("api_name") or "").strip()
        if not api_name:
            continue

        if component_type == "custom_object":
            successful_objects.add(api_name)
            object_to_fields.setdefault(api_name, set())
            continue

        if component_type in {"custom_field", "relationship"} and "." in api_name:
            object_api_name, field_api_name = api_name.split(".", 1)
            if object_api_name in successful_objects and field_api_name:
                object_to_fields.setdefault(object_api_name, set()).add(field_api_name)

    for object_api_name in successful_objects:
        field_names = sorted(object_to_fields.get(object_api_name, set()))
        identity_mapping = {field_name: field_name for field_name in field_names}
        await pool.execute(
            """
            INSERT INTO crm_field_mappings (
                org_id,
                client_id,
                canonical_object,
                sfdc_object,
                field_mappings,
                external_id_field,
                is_active
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, NULL, TRUE)
            ON CONFLICT (org_id, client_id, canonical_object)
            DO UPDATE SET
                sfdc_object = EXCLUDED.sfdc_object,
                -- Existing DB mappings on right side win on key conflict — preserves human-defined mappings over auto-generated identity mappings.
                field_mappings = EXCLUDED.field_mappings || crm_field_mappings.field_mappings,
                is_active = TRUE
            """,
            org_id,
            client_id,
            object_api_name,
            object_api_name,
            identity_mapping,
        )


async def execute_deployment(
    nango_connection_id: str,
    plan: dict,
    *,
    pool,
    org_id: str,
    client_id,
    provider_config_key: str | None = None,
) -> dict:
    validation_errors = validate_custom_object_plan(plan)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_deploy_plan", "errors": validation_errors},
        )

    components: list[dict] = []
    objects_created = 0
    fields_created = 0
    relationships_created = 0

    custom_objects = plan.get("custom_objects")
    if not isinstance(custom_objects, list):
        custom_objects = []

    metadata_custom_objects: list[dict] = []
    for custom_object in custom_objects:
        if not isinstance(custom_object, dict):
            continue

        object_api_name = str(custom_object.get("api_name") or "").strip()
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

        metadata_custom_objects.append(custom_object)

    if metadata_custom_objects:
        planned_custom_components: list[tuple[str, str]] = []
        planned_field_specs: dict[str, dict] = {}
        for custom_object in metadata_custom_objects:
            object_api_name = str(custom_object.get("api_name") or "").strip()
            planned_custom_components.append(("custom_object", object_api_name))

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
                    full_name = f"{object_api_name}.{field_api_name}"
                    planned_custom_components.append(
                        ("custom_field", full_name)
                    )
                    planned_field_specs[full_name] = {
                        "object_name": object_api_name,
                        "field_api_name": field_api_name,
                        "metadata": _build_field_metadata(field),
                    }

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
                    full_name = f"{object_api_name}.{relationship_api_name}"
                    planned_custom_components.append(
                        ("relationship", full_name)
                    )
                    planned_field_specs[full_name] = {
                        "object_name": object_api_name,
                        "field_api_name": relationship_api_name,
                        "metadata": _build_field_metadata(relationship),
                    }

        try:
            zip_bytes = metadata_builder.build_custom_object_zip(metadata_custom_objects)
            metadata_result = await salesforce.metadata_deploy_and_poll(
                nango_connection_id=nango_connection_id,
                zip_bytes=zip_bytes,
                provider_config_key=provider_config_key,
            )
            deploy_status = _metadata_status(metadata_result)
            success_map, failure_map = _metadata_component_maps(metadata_result)

            for component_type, api_name in planned_custom_components:
                failed_component = failure_map.get(api_name)
                successful_component = success_map.get(api_name)

                success = bool(successful_component) and not bool(failed_component)
                if not success and not failed_component and deploy_status == "Succeeded":
                    success = True

                component_result: dict = {
                    "type": component_type,
                    "api_name": api_name,
                    "success": success,
                    "sfdc_id": (
                        (successful_component or {}).get("id")
                        or (successful_component or {}).get("componentId")
                    ),
                }

                if not success:
                    if failed_component:
                        component_result["error"] = _metadata_failure_to_error(failed_component)
                    else:
                        component_result["error"] = {
                            "code": "metadata_deploy_failed",
                            "message": f"Metadata deploy ended with status {deploy_status}",
                        }
                else:
                    # Metadata deploy can report "Succeeded" without returning per-field successes.
                    # Verify custom fields exist and backfill via Tooling API if missing.
                    if component_type in {"custom_field", "relationship"}:
                        resolved_field_id = await _resolve_field_id(
                            nango_connection_id=nango_connection_id,
                            full_name=api_name,
                            provider_config_key=provider_config_key,
                        )
                        if resolved_field_id:
                            component_result["sfdc_id"] = resolved_field_id
                        else:
                            field_spec = planned_field_specs.get(api_name)
                            if field_spec:
                                create_response = await salesforce.tooling_create_custom_field(
                                    nango_connection_id=nango_connection_id,
                                    object_name=str(field_spec["object_name"]),
                                    field_api_name=str(field_spec["field_api_name"]),
                                    metadata=dict(field_spec["metadata"]),
                                    provider_config_key=provider_config_key,
                                )
                                create_success = bool(create_response.get("success"))
                                component_result["success"] = create_success
                                component_result["sfdc_id"] = create_response.get("id")
                                if not create_success:
                                    component_result["error"] = _extract_tooling_error(create_response)
                                else:
                                    component_result.pop("error", None)
                            else:
                                component_result["success"] = False
                                component_result["error"] = {
                                    "code": "field_verification_failed",
                                    "message": f"Could not verify or create field {api_name}",
                                }

                    if not component_result.get("success"):
                        components.append(component_result)
                        continue

                    if component_type == "custom_object":
                        objects_created += 1
                    elif component_type == "custom_field":
                        fields_created += 1
                    elif component_type == "relationship":
                        relationships_created += 1

                components.append(component_result)

            try:
                await _best_effort_auto_map_custom_objects(
                    pool=pool,
                    org_id=org_id,
                    client_id=client_id,
                    components=components,
                )
            except Exception:
                logger.exception(
                    "Auto-mapping upsert failed after deployment",
                    extra={
                        "org_id": org_id,
                        "client_id": str(client_id),
                    },
                )
        except HTTPException as exc:
            for component_type, api_name in planned_custom_components:
                components.append(
                    _metadata_failure_component(
                        component_type=component_type,
                        api_name=api_name,
                        detail=exc.detail,
                    )
                )

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
                provider_config_key=provider_config_key,
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


async def _resolve_field_id(
    nango_connection_id: str,
    full_name: str,
    provider_config_key: str | None = None,
) -> str | None:
    if "." not in full_name:
        return None
    object_name, field_api_name = full_name.split(".", 1)
    developer_name = _strip_custom_suffix(field_api_name)
    table_enum_or_id = object_name
    if object_name.endswith("__c"):
        object_id = await _resolve_object_id(
            nango_connection_id,
            object_name,
            provider_config_key=provider_config_key,
        )
        if object_id:
            table_enum_or_id = object_id
    soql = (
        "SELECT Id FROM CustomField "
        f"WHERE DeveloperName = '{_soql_escape(developer_name)}' "
        f"AND TableEnumOrId = '{_soql_escape(table_enum_or_id)}' "
        "ORDER BY CreatedDate DESC LIMIT 1"
    )
    records = await salesforce.tooling_query(
        nango_connection_id,
        soql,
        provider_config_key=provider_config_key,
    )
    if not records:
        return None
    record_id = records[0].get("Id")
    return str(record_id) if record_id else None


async def _resolve_object_id(
    nango_connection_id: str,
    object_api_name: str,
    provider_config_key: str | None = None,
) -> str | None:
    developer_name = _strip_custom_suffix(object_api_name)
    soql = (
        "SELECT Id FROM CustomObject "
        f"WHERE DeveloperName = '{_soql_escape(developer_name)}' "
        "ORDER BY CreatedDate DESC LIMIT 1"
    )
    records = await salesforce.tooling_query(
        nango_connection_id,
        soql,
        provider_config_key=provider_config_key,
    )
    if not records:
        return None
    record_id = records[0].get("Id")
    return str(record_id) if record_id else None


async def _rollback_component(
    nango_connection_id: str,
    component: dict,
    provider_config_key: str | None = None,
) -> dict:
    component_type = str(component.get("type", ""))
    api_name = str(component.get("api_name") or "")
    resolved_id = component.get("sfdc_id")

    try:
        if component_type in {"custom_field", "relationship"}:
            if api_name:
                resolved_id = await _resolve_field_id(
                    nango_connection_id,
                    api_name,
                    provider_config_key=provider_config_key,
                )
            if not resolved_id and component.get("sfdc_id"):
                resolved_id = str(component.get("sfdc_id"))
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
                provider_config_key=provider_config_key,
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


async def execute_rollback(
    nango_connection_id: str,
    deployment_result: dict,
    provider_config_key: str | None = None,
) -> dict:
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
    object_names_for_delete = {
        str(component.get("api_name") or "").strip()
        for component in object_components
        if str(component.get("api_name") or "").strip()
    }

    for component in reversed(field_like_components):
        api_name = str(component.get("api_name") or "").strip()
        object_name = api_name.split(".", 1)[0] if "." in api_name else ""
        if object_name and object_name in object_names_for_delete:
            rollback_components.append(
                {
                    "type": str(component.get("type") or "custom_field"),
                    "api_name": api_name,
                    "success": True,
                    "sfdc_id": component.get("sfdc_id"),
                    "skipped": True,
                    "reason": "Deleted with parent custom object",
                }
            )
            continue

        rollback_components.append(
            await _rollback_component(
                nango_connection_id=nango_connection_id,
                component=component,
                provider_config_key=provider_config_key,
            )
        )

    if object_components:
        object_names_in_order = [
            str(component.get("api_name") or "").strip()
            for component in reversed(object_components)
            if str(component.get("api_name") or "").strip()
        ]
        object_names_for_deploy = list(dict.fromkeys(object_names_in_order))
        try:
            zip_bytes = metadata_builder.build_destructive_deploy_zip(object_names_for_deploy)
            metadata_result = await salesforce.metadata_deploy_and_poll(
                nango_connection_id=nango_connection_id,
                zip_bytes=zip_bytes,
                provider_config_key=provider_config_key,
            )
            deploy_status = _metadata_status(metadata_result)
            success_map, failure_map = _metadata_component_maps(metadata_result)

            for component in reversed(object_components):
                api_name = str(component.get("api_name") or "").strip()
                if not api_name:
                    continue
                failed_component = failure_map.get(api_name)
                successful_component = success_map.get(api_name)

                success = bool(successful_component) and not bool(failed_component)
                if not success and not failed_component and deploy_status == "Succeeded":
                    success = True

                result: dict = {
                    "type": "custom_object",
                    "api_name": api_name,
                    "success": success,
                    "sfdc_id": str(
                        component.get("sfdc_id")
                        or (successful_component or {}).get("id")
                        or (successful_component or {}).get("componentId")
                        or ""
                    )
                    or None,
                }
                if not success:
                    if failed_component:
                        result["error"] = _metadata_failure_to_error(failed_component)
                    else:
                        result["error"] = {
                            "code": "metadata_deploy_failed",
                            "message": f"Destructive deploy ended with status {deploy_status}",
                        }
                rollback_components.append(result)
        except HTTPException as exc:
            for component in reversed(object_components):
                api_name = str(component.get("api_name") or "").strip()
                if not api_name:
                    continue
                rollback_components.append(
                    {
                        "type": "custom_object",
                        "api_name": api_name,
                        "success": False,
                        "sfdc_id": component.get("sfdc_id"),
                        "error": _normalize_error(
                            exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                        ),
                    }
                )

    total_components = len(rollback_components)
    successful_count = sum(1 for component in rollback_components if component.get("success"))
    return {
        "status": _resolve_deployment_status(total_components, successful_count),
        "components": rollback_components,
        "rolled_back_components": successful_count,
        "failed_components": total_components - successful_count,
    }
