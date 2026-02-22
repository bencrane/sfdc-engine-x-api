import difflib
import importlib.util
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.metadata_builder import build_custom_object_zip


SPIKE_PATH = ROOT / "scripts" / "metadata_deploy_spike.py"
METADATA_NS = "http://soap.sforce.com/2006/04/metadata"
TEST_OBJECT = "SFDC_Engine_Test__c"


def _load_spike_module():
    spec = importlib.util.spec_from_file_location("metadata_deploy_spike", SPIKE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec from {SPIKE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_builder_xml() -> tuple[str, str]:
    objects = [
        {
            "api_name": "SFDC_Engine_Test__c",
            "label": "SFDC Engine Test",
            "plural_label": "SFDC Engine Tests",
            "fields": [
                {"api_name": "Test_Name__c", "label": "Test Name", "type": "Text", "length": 255},
                {
                    "api_name": "Test_Status__c",
                    "label": "Test Status",
                    "type": "Picklist",
                    "values": ["Pass", "Fail", "Pending"],
                },
                {"api_name": "Test_Date__c", "label": "Test Date", "type": "Date"},
            ],
        }
    ]

    zip_bytes = build_custom_object_zip(objects)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as archive:
        object_xml = archive.read(f"objects/{TEST_OBJECT}.object").decode("utf-8")
        package_xml = archive.read("package.xml").decode("utf-8")
    return object_xml, package_xml


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _attr_map(element: ET.Element) -> dict[str, str]:
    return {k: v for k, v in sorted(element.attrib.items(), key=lambda item: item[0])}


def _xml_structural_diff(spike_xml: str, builder_xml: str, label: str) -> list[str]:
    diffs: list[str] = []
    spike_root = ET.fromstring(spike_xml)
    builder_root = ET.fromstring(builder_xml)

    def compare(path: str, left: ET.Element, right: ET.Element) -> None:
        left_name = _local_name(left.tag)
        right_name = _local_name(right.tag)
        if left.tag != right.tag:
            diffs.append(
                f"{path}: tag mismatch spike={left.tag!r} builder={right.tag!r} "
                f"(local spike={left_name!r}, builder={right_name!r})"
            )

        left_attrs = _attr_map(left)
        right_attrs = _attr_map(right)
        if left_attrs != right_attrs:
            diffs.append(f"{path}: attributes differ spike={left_attrs} builder={right_attrs}")

        left_text = left.text if left.text is not None else ""
        right_text = right.text if right.text is not None else ""
        if left_text != right_text:
            diffs.append(f"{path}: text differs spike={left_text!r} builder={right_text!r}")

        left_children = list(left)
        right_children = list(right)

        if len(left_children) != len(right_children):
            diffs.append(
                f"{path}: child count differs spike={len(left_children)} builder={len(right_children)}"
            )

        min_len = min(len(left_children), len(right_children))
        for index in range(min_len):
            l_child = left_children[index]
            r_child = right_children[index]
            child_path = f"{path}/{_local_name(l_child.tag)}[{index}]"
            if l_child.tag != r_child.tag:
                diffs.append(
                    f"{path}: child order/tag mismatch at index {index} "
                    f"spike={l_child.tag!r} builder={r_child.tag!r}"
                )
            compare(child_path, l_child, r_child)

        if len(left_children) > len(right_children):
            for index in range(min_len, len(left_children)):
                extra = left_children[index]
                diffs.append(
                    f"{path}: spike has extra child at index {index}: tag={extra.tag!r}"
                )
        elif len(right_children) > len(left_children):
            for index in range(min_len, len(right_children)):
                extra = right_children[index]
                diffs.append(
                    f"{path}: builder has extra child at index {index}: tag={extra.tag!r}"
                )

    compare(f"/{label}", spike_root, builder_root)
    return diffs


def _line_diff(spike_xml: str, builder_xml: str, label: str) -> list[str]:
    return list(
        difflib.ndiff(
            spike_xml.splitlines(),
            builder_xml.splitlines(),
            linejunk=None,
            charjunk=None,
        )
    )


def _print_side_by_side(left_title: str, left_text: str, right_title: str, right_text: str) -> None:
    left_lines = left_text.splitlines()
    right_lines = right_text.splitlines()
    width = max(len(left_title), *(len(line) for line in left_lines), 30) + 4
    print(f"{left_title:<{width}}| {right_title}")
    print(f"{'-' * width}+{'-' * max(len(right_title), 30)}")
    max_lines = max(len(left_lines), len(right_lines))
    for i in range(max_lines):
        left_line = left_lines[i] if i < len(left_lines) else ""
        right_line = right_lines[i] if i < len(right_lines) else ""
        print(f"{left_line:<{width}}| {right_line}")


def _report_spec_alignment(spike_object_xml: str, builder_object_xml: str, builder_package_xml: str) -> None:
    def has_namespace(xml_text: str) -> bool:
        return f'xmlns="{METADATA_NS}"' in xml_text

    def has_inline_fields(xml_text: str) -> bool:
        root = ET.fromstring(xml_text)
        return any(_local_name(child.tag) == "fields" for child in list(root))

    print("\n=== SPEC ALIGNMENT (Section 6) ===")
    print(
        f"- Spike object XML has metadata namespace: {has_namespace(spike_object_xml)} "
        f"(expected True)"
    )
    print(
        f"- Builder object XML has metadata namespace: {has_namespace(builder_object_xml)} "
        f"(expected True)"
    )
    print(
        f"- Spike object XML uses inline <fields>: {has_inline_fields(spike_object_xml)} "
        f"(expected True)"
    )
    print(
        f"- Builder object XML uses inline <fields>: {has_inline_fields(builder_object_xml)} "
        f"(expected True)"
    )
    print(
        f"- Builder package.xml contains <name>CustomObject</name>: "
        f"{'<name>CustomObject</name>' in builder_package_xml} (expected True)"
    )
    print(
        f"- Builder package.xml contains member SFDC_Engine_Test__c: "
        f"{'<members>SFDC_Engine_Test__c</members>' in builder_package_xml} (expected True)"
    )


def main() -> None:
    spike = _load_spike_module()
    spike_object_xml = getattr(spike, "CREATE_OBJECT_XML")
    spike_package_xml = getattr(spike, "CREATE_PACKAGE_XML")
    builder_object_xml, builder_package_xml = _extract_builder_xml()

    print("=== OBJECT XML SIDE-BY-SIDE ===")
    _print_side_by_side("SPIKE object XML", spike_object_xml, "BUILDER object XML", builder_object_xml)

    print("\n=== PACKAGE XML SIDE-BY-SIDE ===")
    _print_side_by_side("SPIKE package.xml", spike_package_xml, "BUILDER package.xml", builder_package_xml)

    print("\n=== OBJECT XML LINE DIFF (ndiff) ===")
    for line in _line_diff(spike_object_xml, builder_object_xml, "object.xml"):
        if line.startswith("? "):
            continue
        print(line)

    print("\n=== PACKAGE XML LINE DIFF (ndiff) ===")
    for line in _line_diff(spike_package_xml, builder_package_xml, "package.xml"):
        if line.startswith("? "):
            continue
        print(line)

    print("\n=== OBJECT XML STRUCTURAL DIFF ===")
    object_struct_diffs = _xml_structural_diff(
        spike_object_xml, builder_object_xml, label="CustomObject"
    )
    if object_struct_diffs:
        for diff in object_struct_diffs:
            print(f"- {diff}")
    else:
        print("- No structural differences detected")

    print("\n=== PACKAGE XML STRUCTURAL DIFF ===")
    package_struct_diffs = _xml_structural_diff(
        spike_package_xml, builder_package_xml, label="Package"
    )
    if package_struct_diffs:
        for diff in package_struct_diffs:
            print(f"- {diff}")
    else:
        print("- No structural differences detected")

    _report_spec_alignment(spike_object_xml, builder_object_xml, builder_package_xml)


if __name__ == "__main__":
    main()
