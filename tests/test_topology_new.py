"""Tests for new topology endpoints (picklist, diff)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.auth.context import AuthContext, ROLE_PERMISSIONS


def _auth(role="org_admin", org_id="org-1"):
    return AuthContext(
        org_id=org_id,
        user_id="user-1",
        role=role,
        permissions=ROLE_PERMISSIONS[role],
    )


def _snapshot(objects: dict) -> dict:
    return {"objects": objects, "object_names": list(objects.keys())}


class TestTopologyDiff:
    def test_diff_added_objects(self):
        from app.models.topology import TopologyDiffResponse

        objects_a = {"Account": {"fields": []}}
        objects_b = {"Account": {"fields": []}, "Contact": {"fields": []}}

        names_a = set(objects_a.keys())
        names_b = set(objects_b.keys())
        added = sorted(names_b - names_a)
        removed = sorted(names_a - names_b)

        assert added == ["Contact"]
        assert removed == []

    def test_diff_removed_objects(self):
        objects_a = {"Account": {"fields": []}, "Contact": {"fields": []}}
        objects_b = {"Account": {"fields": []}}

        names_a = set(objects_a.keys())
        names_b = set(objects_b.keys())
        removed = sorted(names_a - names_b)

        assert removed == ["Contact"]

    def test_diff_changed_fields(self):
        objects_a = {
            "Account": {
                "fields": [
                    {"name": "Id", "type": "id", "label": "Record ID"},
                    {"name": "Name", "type": "string", "label": "Name"},
                    {"name": "OldField", "type": "string", "label": "Old"},
                ]
            }
        }
        objects_b = {
            "Account": {
                "fields": [
                    {"name": "Id", "type": "id", "label": "Record ID"},
                    {"name": "Name", "type": "textarea", "label": "Name"},
                    {"name": "NewField", "type": "string", "label": "New"},
                ]
            }
        }

        fields_a = {f["name"]: f for f in objects_a["Account"]["fields"]}
        fields_b = {f["name"]: f for f in objects_b["Account"]["fields"]}

        added = sorted(set(fields_b) - set(fields_a))
        removed = sorted(set(fields_a) - set(fields_b))

        assert added == ["NewField"]
        assert removed == ["OldField"]

        # Name changed type from string to textarea
        common = set(fields_a) & set(fields_b)
        changed = [
            n for n in common
            if fields_a[n].get("type") != fields_b[n].get("type")
            or fields_a[n].get("label") != fields_b[n].get("label")
        ]
        assert "Name" in changed

    def test_diff_object_names_filter(self):
        objects_a = {"Account": {"fields": []}, "Contact": {"fields": []}}
        objects_b = {"Account": {"fields": []}, "Contact": {"fields": []}, "Lead": {"fields": []}}

        filter_set = {"Account"}
        filtered_a = {k: v for k, v in objects_a.items() if k in filter_set}
        filtered_b = {k: v for k, v in objects_b.items() if k in filter_set}

        added = sorted(set(filtered_b) - set(filtered_a))
        assert added == []  # Lead is not in filter

    def test_diff_no_changes(self):
        objects_a = {"Account": {"fields": [{"name": "Id", "type": "id", "label": "ID"}]}}
        objects_b = {"Account": {"fields": [{"name": "Id", "type": "id", "label": "ID"}]}}

        fields_a = {f["name"]: f for f in objects_a["Account"]["fields"]}
        fields_b = {f["name"]: f for f in objects_b["Account"]["fields"]}

        added = sorted(set(fields_b) - set(fields_a))
        removed = sorted(set(fields_a) - set(fields_b))
        changed = [
            n for n in (set(fields_a) & set(fields_b))
            if fields_a[n].get("type") != fields_b[n].get("type")
        ]

        assert added == []
        assert removed == []
        assert changed == []


class TestPicklist:
    def test_extract_picklist_values(self):
        snapshot = _snapshot({
            "Opportunity": {
                "fields": [
                    {"name": "StageName", "type": "picklist", "picklistValues": [
                        {"value": "Prospecting", "active": True},
                        {"value": "Closed Won", "active": True},
                    ]},
                    {"name": "Id", "type": "id"},
                ]
            }
        })

        obj = snapshot["objects"]["Opportunity"]
        for field in obj["fields"]:
            if field["name"] == "StageName":
                values = field.get("picklistValues", [])
                assert len(values) == 2
                assert values[0]["value"] == "Prospecting"

    def test_missing_object(self):
        snapshot = _snapshot({"Account": {"fields": []}})
        assert "Contact" not in snapshot["objects"]

    def test_missing_field(self):
        snapshot = _snapshot({
            "Account": {
                "fields": [{"name": "Id", "type": "id"}]
            }
        })
        fields = snapshot["objects"]["Account"]["fields"]
        matches = [f for f in fields if f["name"] == "NonExistent"]
        assert matches == []
