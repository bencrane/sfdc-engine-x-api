from __future__ import annotations

from typing import Any


ValidationError = dict[str, str]


CUSTOM_FIELD_TYPES = {
    "Text",
    "Number",
    "Currency",
    "Percent",
    "Picklist",
    "Lookup",
    "MasterDetail",
    "Checkbox",
    "TextArea",
    "LongTextArea",
    "Date",
    "DateTime",
    "Phone",
    "Email",
    "Url",
}
RELATIONSHIP_FIELD_TYPES = {"Lookup", "MasterDetail"}

FOLDER_ACCESS_TYPES = {"Public", "PublicInternal", "Shared", "Hidden"}
REPORT_FORMATS = {"Tabular", "Summary", "Matrix", "MultiBlock"}
REPORT_SCOPES = {"organization", "user", "mine", "team", "everything"}
REPORT_CHART_TYPES = {
    "VerticalColumn",
    "HorizontalBar",
    "Bar",
    "BarStacked",
    "BarStacked100",
    "Column",
    "ColumnStacked",
    "ColumnStacked100",
    "Line",
    "LineCumulative",
    "LineGrouped",
    "Pie",
    "Donut",
    "Funnel",
    "Scatter",
    "ScatterGrouped",
}
CHART_AGGREGATES = {"Sum", "Average", "Maximum", "Minimum", "RowCount"}
GROUPING_SORT_ORDERS = {"Asc", "Desc"}
GROUPING_DATE_GRANULARITIES = {
    "None",
    "Day",
    "Week",
    "Month",
    "Quarter",
    "Year",
    "FiscalQuarter",
    "FiscalYear",
}
DASHBOARD_TYPES = {"SpecifiedUser", "LoggedInUser", "MyTeamUser"}
DASHBOARD_COMPONENT_TYPES = {
    "Bar",
    "BarStacked",
    "BarStacked100",
    "Column",
    "ColumnStacked",
    "ColumnStacked100",
    "Line",
    "LineCumulative",
    "LineGrouped",
    "Pie",
    "Donut",
    "Funnel",
    "Gauge",
    "Metric",
    "Table",
    "Scatter",
    "ScatterGrouped",
    "FlexTable",
}


def _add_error(errors: list[ValidationError], field: str, message: str) -> None:
    errors.append({"field": field, "message": message})


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_required_string(
    *,
    errors: list[ValidationError],
    payload: dict[str, Any],
    key: str,
    path: str,
    label: str | None = None,
) -> str:
    value = payload.get(key)
    if _is_non_empty_string(value):
        return str(value).strip()
    _add_error(errors, f"{path}.{key}", f"{label or key} must be a non-empty string")
    return ""


def _validate_positive_int_if_present(
    *,
    errors: list[ValidationError],
    payload: dict[str, Any],
    key: str,
    path: str,
) -> int | None:
    if key not in payload or payload.get(key) is None:
        return None
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _add_error(errors, f"{path}.{key}", f"{key} must be a positive integer")
        return None
    return value


def _validate_pre_existing_flag(
    *,
    errors: list[ValidationError],
    payload: dict[str, Any],
    path: str,
) -> bool:
    if "pre_existing" not in payload:
        return False
    pre_existing = payload.get("pre_existing")
    if isinstance(pre_existing, bool):
        return pre_existing
    _add_error(
        errors,
        f"{path}.pre_existing",
        "pre_existing must be a boolean when provided",
    )
    return False


def _validate_custom_field_entry(
    *,
    field_payload: dict[str, Any],
    field_path: str,
    errors: list[ValidationError],
    relationship_only: bool,
) -> None:
    _validate_required_string(
        errors=errors,
        payload=field_payload,
        key="api_name",
        path=field_path,
    )
    _validate_required_string(
        errors=errors,
        payload=field_payload,
        key="label",
        path=field_path,
    )

    field_type = _validate_required_string(
        errors=errors,
        payload=field_payload,
        key="type",
        path=field_path,
    )
    if not field_type:
        return

    valid_types = RELATIONSHIP_FIELD_TYPES if relationship_only else CUSTOM_FIELD_TYPES
    if field_type not in valid_types:
        allowed = ", ".join(sorted(valid_types))
        _add_error(
            errors,
            f"{field_path}.type",
            f"Invalid field type '{field_type}'. Must be one of: {allowed}",
        )
        return

    if field_type == "Text":
        _validate_positive_int_if_present(errors=errors, payload=field_payload, key="length", path=field_path)

    elif field_type in {"Number", "Currency", "Percent"}:
        precision = _validate_positive_int_if_present(
            errors=errors,
            payload=field_payload,
            key="precision",
            path=field_path,
        )
        scale = _validate_positive_int_if_present(
            errors=errors,
            payload=field_payload,
            key="scale",
            path=field_path,
        )
        if precision is not None and scale is not None and precision < scale:
            _add_error(
                errors,
                f"{field_path}.precision",
                f"precision ({precision}) must be greater than or equal to scale ({scale})",
            )

    elif field_type == "Picklist":
        if "values" in field_payload:
            values = field_payload.get("values")
            if not isinstance(values, list) or not values:
                _add_error(
                    errors,
                    f"{field_path}.values",
                    "Picklist values must be a non-empty list when provided",
                )

    elif field_type in RELATIONSHIP_FIELD_TYPES:
        related_to = field_payload.get("related_to")
        reference_to = field_payload.get("referenceTo")
        if not _is_non_empty_string(related_to) and not _is_non_empty_string(reference_to):
            _add_error(
                errors,
                f"{field_path}.related_to",
                "Lookup/MasterDetail fields must include a non-empty related_to or referenceTo",
            )

    elif field_type == "Checkbox":
        for key in ("default", "default_value"):
            if key in field_payload and not isinstance(field_payload.get(key), bool):
                _add_error(errors, f"{field_path}.{key}", f"{key} must be a boolean when provided")

    elif field_type == "LongTextArea":
        _validate_positive_int_if_present(errors=errors, payload=field_payload, key="length", path=field_path)


def validate_custom_object_plan(plan: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(plan, dict):
        return [{"field": "plan", "message": "Plan must be an object"}]

    custom_objects = plan.get("custom_objects")
    if custom_objects is None:
        custom_objects = []
    if not isinstance(custom_objects, list):
        _add_error(errors, "custom_objects", "custom_objects must be a list")
        return errors

    for object_index, custom_object in enumerate(custom_objects):
        object_path = f"custom_objects[{object_index}]"
        if not isinstance(custom_object, dict):
            _add_error(errors, object_path, "custom_object entry must be an object")
            continue

        object_api_name = _validate_required_string(
            errors=errors,
            payload=custom_object,
            key="api_name",
            path=object_path,
        )
        if object_api_name and not object_api_name.endswith("__c"):
            _add_error(
                errors,
                f"{object_path}.api_name",
                "Custom object api_name must end with '__c'",
            )
        _validate_required_string(
            errors=errors,
            payload=custom_object,
            key="label",
            path=object_path,
        )

        fields = custom_object.get("fields")
        if fields is not None and not isinstance(fields, list):
            _add_error(errors, f"{object_path}.fields", "fields must be a list when provided")
        if isinstance(fields, list):
            for field_index, field_payload in enumerate(fields):
                field_path = f"{object_path}.fields[{field_index}]"
                if not isinstance(field_payload, dict):
                    _add_error(errors, field_path, "field entry must be an object")
                    continue
                _validate_custom_field_entry(
                    field_payload=field_payload,
                    field_path=field_path,
                    errors=errors,
                    relationship_only=False,
                )

        relationships = custom_object.get("relationships")
        if relationships is not None and not isinstance(relationships, list):
            _add_error(
                errors,
                f"{object_path}.relationships",
                "relationships must be a list when provided",
            )
        if isinstance(relationships, list):
            for relationship_index, relationship_payload in enumerate(relationships):
                relationship_path = f"{object_path}.relationships[{relationship_index}]"
                if not isinstance(relationship_payload, dict):
                    _add_error(errors, relationship_path, "relationship entry must be an object")
                    continue
                _validate_custom_field_entry(
                    field_payload=relationship_payload,
                    field_path=relationship_path,
                    errors=errors,
                    relationship_only=True,
                )

    return errors


def validate_workflow_plan(plan: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(plan, dict):
        return [{"field": "plan", "message": "Plan must be an object"}]

    flows = plan.get("flows")
    if flows is not None and not isinstance(flows, list):
        _add_error(errors, "flows", "flows must be a list when provided")
    if isinstance(flows, list):
        for index, flow in enumerate(flows):
            path = f"flows[{index}]"
            if not isinstance(flow, dict):
                _add_error(errors, path, "flow entry must be an object")
                continue
            _validate_required_string(errors=errors, payload=flow, key="api_name", path=path)
            _validate_required_string(errors=errors, payload=flow, key="xml_content", path=path)

    assignment_rules = plan.get("assignment_rules")
    if assignment_rules is not None and not isinstance(assignment_rules, list):
        _add_error(
            errors,
            "assignment_rules",
            "assignment_rules must be a list when provided",
        )
    if isinstance(assignment_rules, list):
        for index, assignment_rule in enumerate(assignment_rules):
            path = f"assignment_rules[{index}]"
            if not isinstance(assignment_rule, dict):
                _add_error(errors, path, "assignment_rule entry must be an object")
                continue
            _validate_required_string(errors=errors, payload=assignment_rule, key="object", path=path)
            _validate_required_string(errors=errors, payload=assignment_rule, key="xml_content", path=path)

    return errors


def validate_analytics_plan(plan: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(plan, dict):
        return [{"field": "plan", "message": "Plan must be an object"}]

    report_folders_in_plan: set[str] = set()
    dashboard_folders_in_plan: set[str] = set()
    reports_in_plan: set[str] = set()

    report_folders = plan.get("report_folders")
    if report_folders is not None and not isinstance(report_folders, list):
        _add_error(errors, "report_folders", "report_folders must be a list when provided")
    if isinstance(report_folders, list):
        for index, folder in enumerate(report_folders):
            path = f"report_folders[{index}]"
            if not isinstance(folder, dict):
                _add_error(errors, path, "report_folder entry must be an object")
                continue
            api_name = _validate_required_string(errors=errors, payload=folder, key="api_name", path=path)
            if api_name:
                report_folders_in_plan.add(api_name)
            _validate_required_string(errors=errors, payload=folder, key="name", path=path)
            if "accessType" in folder:
                access_type = folder.get("accessType")
                if not _is_non_empty_string(access_type) or str(access_type) not in FOLDER_ACCESS_TYPES:
                    allowed = ", ".join(sorted(FOLDER_ACCESS_TYPES))
                    _add_error(
                        errors,
                        f"{path}.accessType",
                        f"Invalid accessType '{access_type}'. Must be one of: {allowed}",
                    )

    dashboard_folders = plan.get("dashboard_folders")
    if dashboard_folders is not None and not isinstance(dashboard_folders, list):
        _add_error(
            errors,
            "dashboard_folders",
            "dashboard_folders must be a list when provided",
        )
    if isinstance(dashboard_folders, list):
        for index, folder in enumerate(dashboard_folders):
            path = f"dashboard_folders[{index}]"
            if not isinstance(folder, dict):
                _add_error(errors, path, "dashboard_folder entry must be an object")
                continue
            api_name = _validate_required_string(errors=errors, payload=folder, key="api_name", path=path)
            if api_name:
                dashboard_folders_in_plan.add(api_name)
            _validate_required_string(errors=errors, payload=folder, key="name", path=path)
            if "accessType" in folder:
                access_type = folder.get("accessType")
                if not _is_non_empty_string(access_type) or str(access_type) not in FOLDER_ACCESS_TYPES:
                    allowed = ", ".join(sorted(FOLDER_ACCESS_TYPES))
                    _add_error(
                        errors,
                        f"{path}.accessType",
                        f"Invalid accessType '{access_type}'. Must be one of: {allowed}",
                    )

    reports = plan.get("reports")
    if reports is not None and not isinstance(reports, list):
        _add_error(errors, "reports", "reports must be a list when provided")
    if isinstance(reports, list):
        for report_index, report in enumerate(reports):
            report_path = f"reports[{report_index}]"
            if not isinstance(report, dict):
                _add_error(errors, report_path, "report entry must be an object")
                continue

            report_api_name = _validate_required_string(
                errors=errors,
                payload=report,
                key="api_name",
                path=report_path,
            )
            report_folder = _validate_required_string(
                errors=errors,
                payload=report,
                key="folder",
                path=report_path,
            )
            if report_api_name and report_folder:
                reports_in_plan.add(f"{report_folder}/{report_api_name}")

            _validate_required_string(errors=errors, payload=report, key="name", path=report_path)
            _validate_required_string(errors=errors, payload=report, key="reportType", path=report_path)

            if "format" in report:
                report_format = report.get("format")
                if not _is_non_empty_string(report_format) or str(report_format) not in REPORT_FORMATS:
                    allowed = ", ".join(sorted(REPORT_FORMATS))
                    _add_error(
                        errors,
                        f"{report_path}.format",
                        f"Invalid format '{report_format}'. Must be one of: {allowed}",
                    )

            if "scope" in report:
                scope = report.get("scope")
                if not _is_non_empty_string(scope) or str(scope) not in REPORT_SCOPES:
                    allowed = ", ".join(sorted(REPORT_SCOPES))
                    _add_error(
                        errors,
                        f"{report_path}.scope",
                        f"Invalid scope '{scope}'. Must be one of: {allowed}",
                    )

            chart = report.get("chart")
            if chart is not None:
                if not isinstance(chart, dict):
                    _add_error(errors, f"{report_path}.chart", "chart must be an object when provided")
                else:
                    chart_type = chart.get("chartType")
                    if not _is_non_empty_string(chart_type) or str(chart_type) not in REPORT_CHART_TYPES:
                        allowed = ", ".join(sorted(REPORT_CHART_TYPES))
                        _add_error(
                            errors,
                            f"{report_path}.chart.chartType",
                            f"Invalid chartType '{chart_type}'. Must be one of: {allowed}",
                        )

                    chart_summaries = chart.get("chartSummaries")
                    if not isinstance(chart_summaries, list) or not chart_summaries:
                        _add_error(
                            errors,
                            f"{report_path}.chart.chartSummaries",
                            "chartSummaries must be a non-empty list when chart is provided",
                        )
                    else:
                        for summary_index, summary in enumerate(chart_summaries):
                            summary_path = f"{report_path}.chart.chartSummaries[{summary_index}]"
                            if not isinstance(summary, dict):
                                _add_error(errors, summary_path, "chart summary must be an object")
                                continue
                            aggregate = _validate_required_string(
                                errors=errors,
                                payload=summary,
                                key="aggregate",
                                path=summary_path,
                            )
                            if aggregate and aggregate not in CHART_AGGREGATES:
                                allowed = ", ".join(sorted(CHART_AGGREGATES))
                                _add_error(
                                    errors,
                                    f"{summary_path}.aggregate",
                                    f"Invalid aggregate '{aggregate}'. Must be one of: {allowed}",
                                )
                            _validate_required_string(
                                errors=errors,
                                payload=summary,
                                key="column",
                                path=summary_path,
                            )

            for grouping_key in ("groupingsDown", "groupingsAcross"):
                groupings = report.get(grouping_key)
                if groupings is None:
                    continue
                if not isinstance(groupings, list):
                    _add_error(
                        errors,
                        f"{report_path}.{grouping_key}",
                        f"{grouping_key} must be a list when provided",
                    )
                    continue
                for grouping_index, grouping in enumerate(groupings):
                    grouping_path = f"{report_path}.{grouping_key}[{grouping_index}]"
                    if not isinstance(grouping, dict):
                        _add_error(errors, grouping_path, "grouping entry must be an object")
                        continue
                    _validate_required_string(errors=errors, payload=grouping, key="field", path=grouping_path)
                    if "sortOrder" in grouping:
                        sort_order = grouping.get("sortOrder")
                        if not _is_non_empty_string(sort_order) or str(sort_order) not in GROUPING_SORT_ORDERS:
                            allowed = ", ".join(sorted(GROUPING_SORT_ORDERS))
                            _add_error(
                                errors,
                                f"{grouping_path}.sortOrder",
                                f"Invalid sortOrder '{sort_order}'. Must be one of: {allowed}",
                            )
                    if "dateGranularity" in grouping:
                        date_granularity = grouping.get("dateGranularity")
                        if (
                            not _is_non_empty_string(date_granularity)
                            or str(date_granularity) not in GROUPING_DATE_GRANULARITIES
                        ):
                            allowed = ", ".join(sorted(GROUPING_DATE_GRANULARITIES))
                            _add_error(
                                errors,
                                f"{grouping_path}.dateGranularity",
                                (
                                    f"Invalid dateGranularity '{date_granularity}'. "
                                    f"Must be one of: {allowed}"
                                ),
                            )

            report_filter = report.get("filter")
            if report_filter is not None:
                if not isinstance(report_filter, dict):
                    _add_error(errors, f"{report_path}.filter", "filter must be an object when provided")
                else:
                    criteria_items = report_filter.get("criteriaItems")
                    if criteria_items is not None:
                        if not isinstance(criteria_items, list):
                            _add_error(
                                errors,
                                f"{report_path}.filter.criteriaItems",
                                "criteriaItems must be a list when provided",
                            )
                        else:
                            for criteria_index, criteria in enumerate(criteria_items):
                                criteria_path = f"{report_path}.filter.criteriaItems[{criteria_index}]"
                                if not isinstance(criteria, dict):
                                    _add_error(errors, criteria_path, "criteria item must be an object")
                                    continue
                                _validate_required_string(
                                    errors=errors,
                                    payload=criteria,
                                    key="column",
                                    path=criteria_path,
                                )
                                _validate_required_string(
                                    errors=errors,
                                    payload=criteria,
                                    key="operator",
                                    path=criteria_path,
                                )
                                _validate_required_string(
                                    errors=errors,
                                    payload=criteria,
                                    key="value",
                                    path=criteria_path,
                                )

            report_pre_existing = _validate_pre_existing_flag(
                errors=errors,
                payload=report,
                path=report_path,
            )
            if (
                report_folder
                and not report_pre_existing
                and report_folder not in report_folders_in_plan
            ):
                _add_error(
                    errors,
                    f"{report_path}.folder",
                    (
                        f"Report folder '{report_folder}' not found in plan report_folders "
                        "and not marked as pre_existing"
                    ),
                )

    dashboards = plan.get("dashboards")
    if dashboards is not None and not isinstance(dashboards, list):
        _add_error(errors, "dashboards", "dashboards must be a list when provided")
    if isinstance(dashboards, list):
        for dashboard_index, dashboard in enumerate(dashboards):
            dashboard_path = f"dashboards[{dashboard_index}]"
            if not isinstance(dashboard, dict):
                _add_error(errors, dashboard_path, "dashboard entry must be an object")
                continue

            _validate_required_string(
                errors=errors,
                payload=dashboard,
                key="api_name",
                path=dashboard_path,
            )
            dashboard_folder = _validate_required_string(
                errors=errors,
                payload=dashboard,
                key="folder",
                path=dashboard_path,
            )
            _validate_required_string(
                errors=errors,
                payload=dashboard,
                key="title",
                path=dashboard_path,
            )

            dashboard_type = dashboard.get("dashboardType")
            if dashboard_type is not None:
                if not _is_non_empty_string(dashboard_type) or str(dashboard_type) not in DASHBOARD_TYPES:
                    allowed = ", ".join(sorted(DASHBOARD_TYPES))
                    _add_error(
                        errors,
                        f"{dashboard_path}.dashboardType",
                        f"Invalid dashboardType '{dashboard_type}'. Must be one of: {allowed}",
                    )
                    dashboard_type = None
                else:
                    dashboard_type = str(dashboard_type)
            else:
                dashboard_type = "SpecifiedUser"

            running_user = dashboard.get("runningUser")
            if dashboard_type == "SpecifiedUser" and not _is_non_empty_string(running_user):
                _add_error(
                    errors,
                    f"{dashboard_path}.runningUser",
                    "runningUser is required when dashboardType is SpecifiedUser",
                )

            dashboard_pre_existing = _validate_pre_existing_flag(
                errors=errors,
                payload=dashboard,
                path=dashboard_path,
            )
            if (
                dashboard_folder
                and not dashboard_pre_existing
                and dashboard_folder not in dashboard_folders_in_plan
            ):
                _add_error(
                    errors,
                    f"{dashboard_path}.folder",
                    (
                        f"Dashboard folder '{dashboard_folder}' not found in plan dashboard_folders "
                        "and not marked as pre_existing"
                    ),
                )

            for section_name in ("leftSection", "middleSection", "rightSection"):
                section = dashboard.get(section_name)
                if section is None:
                    continue
                if not isinstance(section, list):
                    _add_error(
                        errors,
                        f"{dashboard_path}.{section_name}",
                        f"{section_name} must be a list when provided",
                    )
                    continue
                for component_index, component in enumerate(section):
                    component_path = f"{dashboard_path}.{section_name}[{component_index}]"
                    if not isinstance(component, dict):
                        _add_error(errors, component_path, "dashboard component must be an object")
                        continue

                    component_type = component.get("componentType")
                    if component_type is not None:
                        if not _is_non_empty_string(component_type) or str(component_type) not in DASHBOARD_COMPONENT_TYPES:
                            allowed = ", ".join(sorted(DASHBOARD_COMPONENT_TYPES))
                            _add_error(
                                errors,
                                f"{component_path}.componentType",
                                (
                                    f"Invalid componentType '{component_type}'. "
                                    f"Must be one of: {allowed}"
                                ),
                            )

                    component_report = component.get("report")
                    if component_report is not None and not _is_non_empty_string(component_report):
                        _add_error(
                            errors,
                            f"{component_path}.report",
                            "report must be a non-empty string when provided",
                        )

                    component_pre_existing = _validate_pre_existing_flag(
                        errors=errors,
                        payload=component,
                        path=component_path,
                    )
                    if (
                        _is_non_empty_string(component_report)
                        and not component_pre_existing
                        and str(component_report).strip() not in reports_in_plan
                    ):
                        _add_error(
                            errors,
                            f"{component_path}.report",
                            (
                                f"Dashboard component report '{str(component_report).strip()}' "
                                "not found in plan reports and not marked as pre_existing"
                            ),
                        )

    return errors
