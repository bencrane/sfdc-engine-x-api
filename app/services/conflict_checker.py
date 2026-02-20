PLAN_TYPE_TO_SFDC_TYPE = {
    "Text": "string",
    "Number": "double",
    "Currency": "currency",
    "Date": "date",
    "DateTime": "datetime",
    "Checkbox": "boolean",
    "Picklist": "picklist",
    "MultiPicklist": "multipicklist",
    "Phone": "phone",
    "Email": "email",
    "Url": "url",
    "Percent": "percent",
    "TextArea": "textarea",
    "LongTextArea": "textarea",
    "Lookup": "reference",
    "MasterDetail": "reference",
}


def _normalize_type(plan_type: str | None) -> str | None:
    if not plan_type:
        return None
    mapped = PLAN_TYPE_TO_SFDC_TYPE.get(plan_type, plan_type)
    return mapped.lower()


def _build_field_map(object_payload: dict) -> dict[str, dict]:
    fields = object_payload.get("fields", [])
    if not isinstance(fields, list):
        return {}

    field_map: dict[str, dict] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        field_name = field.get("name")
        if isinstance(field_name, str) and field_name:
            field_map[field_name] = field
    return field_map


def _is_required_field(field: dict) -> bool:
    return field.get("nillable") is False and field.get("defaultValue") is None


def _has_active_validation_rules(object_payload: dict) -> bool:
    validation_rules = object_payload.get("validationRules")

    if isinstance(validation_rules, list):
        for rule in validation_rules:
            if isinstance(rule, dict):
                if rule.get("active") is True or rule.get("isActive") is True:
                    return True
            elif rule:
                return True
    elif isinstance(validation_rules, dict):
        for key in ("rules", "records", "items"):
            rules = validation_rules.get(key)
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict):
                        if rule.get("active") is True or rule.get("isActive") is True:
                            return True
                    elif rule:
                        return True

    fields = object_payload.get("fields", [])
    if isinstance(fields, list):
        for field in fields:
            if not isinstance(field, dict):
                continue
            for key, value in field.items():
                if "validation" in str(key).lower() and value:
                    return True

    return False


def _append_finding(findings: list[dict], severity: str, category: str, message: str) -> None:
    findings.append(
        {
            "severity": severity,
            "category": category,
            "message": message,
        }
    )


def check_conflicts(deployment_plan: dict, topology_snapshot: dict) -> dict:
    findings: list[dict] = []
    objects = topology_snapshot.get("objects", {})
    if not isinstance(objects, dict):
        objects = {}

    custom_objects = deployment_plan.get("custom_objects", [])
    if isinstance(custom_objects, list):
        for custom_object in custom_objects:
            if not isinstance(custom_object, dict):
                continue

            object_name = custom_object.get("api_name")
            if not isinstance(object_name, str) or not object_name:
                continue

            object_payload = objects.get(object_name)
            object_exists = isinstance(object_payload, dict)

            if object_exists:
                _append_finding(
                    findings,
                    severity="red",
                    category="object_name",
                    message=f"{object_name} already exists in topology snapshot",
                )
            else:
                _append_finding(
                    findings,
                    severity="green",
                    category="object_name",
                    message=f"{object_name} does not exist - safe to create",
                )

            if not object_exists:
                continue

            field_map = _build_field_map(object_payload)
            plan_fields = custom_object.get("fields", [])
            if not isinstance(plan_fields, list):
                continue

            for plan_field in plan_fields:
                if not isinstance(plan_field, dict):
                    continue

                field_name = plan_field.get("api_name")
                if not isinstance(field_name, str) or not field_name:
                    continue

                existing_field = field_map.get(field_name)
                if existing_field is None:
                    _append_finding(
                        findings,
                        severity="green",
                        category="field_name",
                        message=f"{object_name}.{field_name} does not exist - safe to create",
                    )
                    continue

                existing_type = str(existing_field.get("type", "")).lower()
                plan_type = _normalize_type(plan_field.get("type"))
                if plan_type is None:
                    plan_type = str(plan_field.get("type", "")).lower()

                if existing_type == plan_type:
                    _append_finding(
                        findings,
                        severity="yellow",
                        category="field_name",
                        message=(
                            f"{object_name}.{field_name} already exists with same type "
                            f"({existing_type})"
                        ),
                    )
                else:
                    _append_finding(
                        findings,
                        severity="red",
                        category="field_name",
                        message=(
                            f"{object_name}.{field_name} already exists with different type "
                            f"(existing={existing_type}, requested={plan_type})"
                        ),
                    )

    standard_object_fields = deployment_plan.get("standard_object_fields", [])
    if isinstance(standard_object_fields, list):
        for standard_object in standard_object_fields:
            if not isinstance(standard_object, dict):
                continue

            object_name = standard_object.get("object")
            if not isinstance(object_name, str) or not object_name:
                continue

            object_payload = objects.get(object_name)
            if not isinstance(object_payload, dict):
                _append_finding(
                    findings,
                    severity="red",
                    category="standard_object",
                    message=f"{object_name} not found in topology snapshot",
                )
                continue

            _append_finding(
                findings,
                severity="green",
                category="standard_object",
                message=f"{object_name} exists in topology snapshot",
            )

            field_map = _build_field_map(object_payload)
            plan_fields = standard_object.get("fields", [])
            if not isinstance(plan_fields, list):
                plan_fields = []

            planned_field_names: set[str] = set()
            for plan_field in plan_fields:
                if not isinstance(plan_field, dict):
                    continue

                field_name = plan_field.get("api_name")
                if not isinstance(field_name, str) or not field_name:
                    continue

                planned_field_names.add(field_name)

                existing_field = field_map.get(field_name)
                if existing_field is None:
                    _append_finding(
                        findings,
                        severity="green",
                        category="field_name",
                        message=f"{object_name}.{field_name} does not exist - safe to create",
                    )
                    continue

                existing_type = str(existing_field.get("type", "")).lower()
                plan_type = _normalize_type(plan_field.get("type"))
                if plan_type is None:
                    plan_type = str(plan_field.get("type", "")).lower()

                if existing_type == plan_type:
                    _append_finding(
                        findings,
                        severity="yellow",
                        category="field_name",
                        message=(
                            f"{object_name}.{field_name} already exists with same type "
                            f"({existing_type})"
                        ),
                    )
                else:
                    _append_finding(
                        findings,
                        severity="red",
                        category="field_name",
                        message=(
                            f"{object_name}.{field_name} already exists with different type "
                            f"(existing={existing_type}, requested={plan_type})"
                        ),
                    )

            existing_fields = object_payload.get("fields", [])
            if isinstance(existing_fields, list):
                for field in existing_fields:
                    if not isinstance(field, dict):
                        continue
                    field_name = field.get("name")
                    if not isinstance(field_name, str) or not field_name:
                        continue
                    if field_name in planned_field_names:
                        continue
                    if _is_required_field(field):
                        _append_finding(
                            findings,
                            severity="yellow",
                            category="required_field",
                            message=(
                                f"{object_name} has required field '{field_name}' not in "
                                "deployment plan"
                            ),
                        )

            if _has_active_validation_rules(object_payload):
                _append_finding(
                    findings,
                    severity="yellow",
                    category="validation_rule",
                    message=f"{object_name} has active validation rules",
                )

    green_count = sum(1 for finding in findings if finding["severity"] == "green")
    yellow_count = sum(1 for finding in findings if finding["severity"] == "yellow")
    red_count = sum(1 for finding in findings if finding["severity"] == "red")

    if red_count > 0:
        overall_severity = "red"
    elif yellow_count > 0:
        overall_severity = "yellow"
    else:
        overall_severity = "green"

    return {
        "findings": findings,
        "overall_severity": overall_severity,
        "green_count": green_count,
        "yellow_count": yellow_count,
        "red_count": red_count,
    }
