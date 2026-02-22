import io
import zipfile
import xml.etree.ElementTree as ET

from app.config import settings


METADATA_NS = "http://soap.sforce.com/2006/04/metadata"
ET.register_namespace("", METADATA_NS)


def _ns(tag: str) -> str:
    return f"{{{METADATA_NS}}}{tag}"


def _version_number() -> str:
    version = str(settings.sfdc_api_version).strip()
    return version[1:] if version.lower().startswith("v") else version


def _bool_text(value: object) -> str:
    return "true" if bool(value) else "false"


def _strip_custom_suffix(api_name: str) -> str:
    return api_name[:-3] if api_name.endswith("__c") else api_name


def _derive_relationship_name(field_api_name: str) -> str:
    base = _strip_custom_suffix(field_api_name)
    if base.endswith("_Id"):
        base = base[:-3]
    return base


def _append_text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    child = ET.SubElement(parent, _ns(tag))
    child.text = str(value)
    return child


def _append_picklist_values(value_set_definition: ET.Element, values: list) -> None:
    _append_text(value_set_definition, "sorted", _bool_text(False))
    if not values:
        values = []

    for index, value in enumerate(values):
        if isinstance(value, str):
            full_name = value
            default = index == 0
            label = value
        elif isinstance(value, dict):
            full_name = str(
                value.get("fullName")
                or value.get("value")
                or value.get("label")
                or f"Value_{index + 1}"
            )
            default = bool(value.get("default", index == 0))
            label = str(value.get("label") or full_name)
        else:
            full_name = f"Value_{index + 1}"
            default = index == 0
            label = full_name

        value_el = ET.SubElement(value_set_definition, _ns("value"))
        _append_text(value_el, "fullName", full_name)
        _append_text(value_el, "default", _bool_text(default))
        _append_text(value_el, "label", label)


def _build_field_xml(custom_object_el: ET.Element, field: dict) -> None:
    field_api_name = str(field.get("api_name") or "").strip()
    if not field_api_name:
        return

    field_type = str(field.get("type") or "").strip()
    label = str(field.get("label") or field_api_name)

    field_el = ET.SubElement(custom_object_el, _ns("fields"))
    _append_text(field_el, "fullName", field_api_name)
    _append_text(field_el, "label", label)
    _append_text(field_el, "type", field_type)

    if "required" in field:
        _append_text(field_el, "required", _bool_text(field.get("required")))

    if field_type == "Text":
        _append_text(field_el, "length", int(field.get("length", 255)))
    elif field_type in {"Number", "Currency", "Percent"}:
        _append_text(field_el, "precision", int(field.get("precision", 18)))
        _append_text(field_el, "scale", int(field.get("scale", 2)))
    elif field_type == "Picklist":
        value_set_el = ET.SubElement(field_el, _ns("valueSet"))
        _append_text(value_set_el, "restricted", _bool_text(field.get("restricted", True)))
        value_set_definition = ET.SubElement(value_set_el, _ns("valueSetDefinition"))
        values = field.get("values") if isinstance(field.get("values"), list) else []
        _append_picklist_values(value_set_definition, values)
    elif field_type in {"Lookup", "MasterDetail"}:
        reference_to = str(field.get("related_to") or field.get("referenceTo") or "").strip()
        if reference_to:
            _append_text(field_el, "referenceTo", reference_to)
        relationship_name = str(
            field.get("relationship_name")
            or field.get("relationshipName")
            or _derive_relationship_name(field_api_name)
        ).strip()
        if relationship_name:
            _append_text(field_el, "relationshipName", relationship_name)
            _append_text(field_el, "relationshipLabel", relationship_name)
        if field_type == "Lookup":
            _append_text(
                field_el,
                "deleteConstraint",
                str(field.get("delete_constraint") or field.get("deleteConstraint") or "SetNull"),
            )
    elif field_type == "Checkbox":
        _append_text(
            field_el,
            "defaultValue",
            _bool_text(field.get("default", field.get("default_value", False))),
        )
    elif field_type == "TextArea":
        _append_text(field_el, "length", int(field.get("length", 255)))
        _append_text(field_el, "visibleLines", int(field.get("visible_lines", 3)))
    elif field_type == "LongTextArea":
        _append_text(field_el, "length", int(field.get("length", 32768)))
        _append_text(
            field_el,
            "visibleLines",
            int(field.get("visible_lines", field.get("visibleLines", 3))),
        )
    elif field_type in {"Date", "DateTime", "Phone", "Email", "Url"}:
        pass


def _object_xml_content(custom_object: dict) -> str:
    api_name = str(custom_object.get("api_name") or "").strip()
    label = str(custom_object.get("label") or api_name)
    plural_label = str(custom_object.get("plural_label") or f"{label}s")

    root = ET.Element(_ns("CustomObject"))
    _append_text(root, "label", label)
    _append_text(root, "pluralLabel", plural_label)

    name_field = ET.SubElement(root, _ns("nameField"))
    _append_text(name_field, "label", f"{label} Name")
    _append_text(name_field, "type", "Text")

    _append_text(root, "deploymentStatus", "Deployed")
    _append_text(root, "sharingModel", "ReadWrite")

    fields = custom_object.get("fields")
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict):
                _build_field_xml(root, field)

    relationships = custom_object.get("relationships")
    if isinstance(relationships, list):
        for relationship in relationships:
            if isinstance(relationship, dict):
                _build_field_xml(root, relationship)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _package_xml_for_objects(object_names: list[str]) -> str:
    root = ET.Element(_ns("Package"))
    types = ET.SubElement(root, _ns("types"))
    for object_name in object_names:
        _append_text(types, "members", object_name)
    _append_text(types, "name", "CustomObject")
    _append_text(root, "version", _version_number())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _empty_package_xml() -> str:
    root = ET.Element(_ns("Package"))
    _append_text(root, "version", _version_number())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _destructive_changes_xml(object_names: list[str]) -> str:
    root = ET.Element(_ns("Package"))
    types = ET.SubElement(root, _ns("types"))
    for object_name in object_names:
        _append_text(types, "members", object_name)
    _append_text(types, "name", "CustomObject")
    _append_text(root, "version", _version_number())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _append_xml_value(parent: ET.Element, tag: str, value: object) -> None:
    if value is None:
        return

    if isinstance(value, list):
        for item in value:
            _append_xml_value(parent, tag, item)
        return

    child = ET.SubElement(parent, _ns(tag))
    if isinstance(value, dict):
        for key, nested_value in value.items():
            _append_xml_value(child, str(key), nested_value)
        return

    if isinstance(value, bool):
        child.text = _bool_text(value)
        return

    child.text = str(value)


def _metadata_xml_content(root_tag: str, metadata: dict) -> str:
    root = ET.Element(_ns(root_tag))
    for key, value in metadata.items():
        _append_xml_value(root, str(key), value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _package_xml_for_workflows(
    flow_api_names: list[str],
    assignment_rule_objects: list[str],
) -> str:
    root = ET.Element(_ns("Package"))

    if flow_api_names:
        flow_types = ET.SubElement(root, _ns("types"))
        for flow_api_name in flow_api_names:
            _append_text(flow_types, "members", flow_api_name)
        _append_text(flow_types, "name", "Flow")

    if assignment_rule_objects:
        assignment_types = ET.SubElement(root, _ns("types"))
        for object_name in assignment_rule_objects:
            _append_text(assignment_types, "members", object_name)
        _append_text(assignment_types, "name", "AssignmentRules")

    _append_text(root, "version", _version_number())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _destructive_changes_workflows_xml(
    flow_api_names: list[str],
    assignment_rule_objects: list[str],
) -> str:
    root = ET.Element(_ns("Package"))

    if flow_api_names:
        flow_types = ET.SubElement(root, _ns("types"))
        for flow_api_name in flow_api_names:
            _append_text(flow_types, "members", flow_api_name)
        _append_text(flow_types, "name", "Flow")

    if assignment_rule_objects:
        assignment_types = ET.SubElement(root, _ns("types"))
        for object_name in assignment_rule_objects:
            _append_text(assignment_types, "members", object_name)
        _append_text(assignment_types, "name", "AssignmentRules")

    _append_text(root, "version", _version_number())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def build_custom_object_zip(objects: list[dict]) -> bytes:
    valid_objects = [
        custom_object
        for custom_object in objects
        if isinstance(custom_object, dict)
        and str(custom_object.get("api_name") or "").strip()
    ]
    object_names = [str(custom_object["api_name"]).strip() for custom_object in valid_objects]

    files: dict[str, str] = {"package.xml": _package_xml_for_objects(object_names)}
    for custom_object in valid_objects:
        api_name = str(custom_object["api_name"]).strip()
        files[f"objects/{api_name}.object"] = _object_xml_content(custom_object)

    return _zip_bytes(files)


def build_destructive_deploy_zip(object_names: list[str]) -> bytes:
    names = [str(name).strip() for name in object_names if str(name).strip()]
    files = {
        "package.xml": _empty_package_xml(),
        "destructiveChanges.xml": _destructive_changes_xml(names),
    }
    return _zip_bytes(files)


def build_workflow_deploy_zip(
    flows: list[dict],
    assignment_rules: list[dict],
) -> bytes:
    valid_flows: list[tuple[str, str]] = []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        flow_api_name = str(flow.get("api_name") or "").strip()
        if not flow_api_name:
            continue
        raw_xml = flow.get("metadata_xml") or flow.get("xml")
        if isinstance(raw_xml, str) and raw_xml.strip():
            xml_content = raw_xml
        else:
            metadata = flow.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            xml_content = _metadata_xml_content("Flow", metadata)
        valid_flows.append((flow_api_name, xml_content))

    valid_assignment_rules: list[tuple[str, str]] = []
    for assignment_rule in assignment_rules:
        if not isinstance(assignment_rule, dict):
            continue
        object_name = str(
            assignment_rule.get("object")
            or assignment_rule.get("object_api_name")
            or assignment_rule.get("api_name")
            or ""
        ).strip()
        if not object_name:
            continue
        raw_xml = assignment_rule.get("metadata_xml") or assignment_rule.get("xml")
        if isinstance(raw_xml, str) and raw_xml.strip():
            xml_content = raw_xml
        else:
            metadata = assignment_rule.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            xml_content = _metadata_xml_content("AssignmentRules", metadata)
        valid_assignment_rules.append((object_name, xml_content))

    files: dict[str, str] = {
        "package.xml": _package_xml_for_workflows(
            flow_api_names=[flow_api_name for flow_api_name, _ in valid_flows],
            assignment_rule_objects=[object_name for object_name, _ in valid_assignment_rules],
        )
    }
    for flow_api_name, xml_content in valid_flows:
        files[f"flows/{flow_api_name}.flow-meta.xml"] = xml_content
    for object_name, xml_content in valid_assignment_rules:
        files[f"assignmentRules/{object_name}.assignmentRules-meta.xml"] = xml_content

    return _zip_bytes(files)


def build_workflow_destructive_deploy_zip(
    flow_api_names: list[str],
    assignment_rule_objects: list[str],
) -> bytes:
    normalized_flow_names = [str(name).strip() for name in flow_api_names if str(name).strip()]
    normalized_assignment_objects = [
        str(name).strip() for name in assignment_rule_objects if str(name).strip()
    ]
    files = {
        "package.xml": _empty_package_xml(),
        "destructiveChanges.xml": _destructive_changes_workflows_xml(
            flow_api_names=normalized_flow_names,
            assignment_rule_objects=normalized_assignment_objects,
        ),
    }
    return _zip_bytes(files)
