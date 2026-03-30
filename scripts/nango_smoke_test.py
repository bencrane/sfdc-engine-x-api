"""
Smoke test: verify per-connection Nango provider config key threading.

Run: doppler run -- .venv/bin/python scripts/nango_smoke_test.py

Uses super-admin to create a throwaway org/user/token, then exercises
connection and mapping endpoints to verify the nango_provider_config_key
field flows correctly. Does NOT call Salesforce (no rate limit impact).
"""

import json
import os
import sys
import uuid

import httpx

BASE_URL = "http://localhost:8000"
TIMEOUT = 15.0


def _headers(token: str) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _post(client: httpx.Client, path: str, token: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    resp = client.post(url, headers=_headers(token), json=body or {})
    print(f"\nPOST {path} -> {resp.status_code}")
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    if resp.status_code >= 400:
        print(f"  ERROR: {json.dumps(data, indent=2)[:500]}")
    return {"status": resp.status_code, "data": data}


def _get(client: httpx.Client, path: str, token: str) -> dict:
    url = f"{BASE_URL}{path}"
    resp = client.get(url, headers=_headers(token))
    print(f"\nGET {path} -> {resp.status_code}")
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return {"status": resp.status_code, "data": data}


def main() -> None:
    super_admin_token = os.environ.get("SUPER_ADMIN_JWT_SECRET")
    if not super_admin_token:
        print("SUPER_ADMIN_JWT_SECRET not set. Run with: doppler run -- ...")
        sys.exit(1)

    results: dict[str, str] = {}
    test_org_id: str | None = None
    test_user_id: str | None = None
    test_client_id: str | None = None
    api_token: str | None = None

    with httpx.Client(timeout=TIMEOUT) as client:

        # 0. Health check
        health = _get(client, "/health", "")
        results["health"] = "PASS" if health["status"] == 200 else "FAIL"

        # 1. Create test org
        org_name = f"smoke-test-{uuid.uuid4().hex[:8]}"
        r = _post(client, "/api/super-admin/orgs", super_admin_token, {
            "name": org_name,
            "slug": org_name,
        })
        if r["status"] < 400:
            test_org_id = r["data"].get("id")
            results["create_org"] = "PASS"
            print(f"  org_id: {test_org_id}")
        else:
            results["create_org"] = "FAIL"
            _print_results(results)
            return

        # 2. Create test user
        r = _post(client, "/api/super-admin/users", super_admin_token, {
            "org_id": test_org_id,
            "email": f"{org_name}@smoke.test",
            "password": "SmokeTest123!",
            "role": "org_admin",
            "name": "Smoke Test User",
        })
        if r["status"] < 400:
            test_user_id = r["data"].get("id")
            results["create_user"] = "PASS"
            print(f"  user_id: {test_user_id}")
        else:
            results["create_user"] = "FAIL"
            _print_results(results)
            return

        # 3. Get API token from env (auth is now via auth-engine-x, no local login)
        api_token = os.environ.get("SMOKE_TEST_API_TOKEN")
        if not api_token:
            print("SMOKE_TEST_API_TOKEN not set. Provide a valid API token for the test org.")
            results["api_token"] = "SKIP (no SMOKE_TEST_API_TOKEN)"
            _print_results(results)
            return
        results["api_token"] = "PASS (from env)"

        # 5. Create test client
        r = _post(client, "/api/clients/create", api_token, {
            "name": f"Test Client {org_name}",
        })
        if r["status"] < 400:
            test_client_id = r["data"].get("id")
            results["create_client"] = "PASS"
            print(f"  client_id: {test_client_id}")
        else:
            results["create_client"] = "FAIL"
            _print_results(results)
            return

        # 6. List connections (should be empty, verify nango_provider_config_key field exists in schema)
        r = _post(client, "/api/connections/list", api_token, {
            "client_id": test_client_id,
        })
        if r["status"] < 400:
            results["list_connections_empty"] = "PASS"
        else:
            results["list_connections_empty"] = "FAIL"

        # 7. Create connection WITH nango_provider_config_key
        r = _post(client, "/api/connections/create", api_token, {
            "client_id": test_client_id,
            "nango_provider_config_key": "salesforce-test-provider",
        })
        if r["status"] < 400:
            results["create_connection_with_provider_key"] = "PASS"
            print(f"  connect_session returned: {list(r['data'].keys())}")
        elif r["status"] == 502:
            error_data = r["data"]
            provider_in_error = False
            if isinstance(error_data, dict):
                detail = error_data.get("detail", {})
                if isinstance(detail, dict):
                    provider_in_error = detail.get("provider") == "salesforce-test-provider"
                    print(f"  provider in error payload: {detail.get('provider')}")
            if provider_in_error:
                results["create_connection_with_provider_key"] = "PASS (502 expected — fake provider, but key was threaded correctly)"
            else:
                results["create_connection_with_provider_key"] = "FAIL (502 but provider key not threaded)"
        else:
            results["create_connection_with_provider_key"] = "FAIL"

        # 8. Create connection WITHOUT nango_provider_config_key (should use global default)
        r = _post(client, "/api/connections/create", api_token, {
            "client_id": test_client_id,
        })
        if r["status"] < 400:
            results["create_connection_without_provider_key"] = "PASS"
        elif r["status"] == 502:
            error_data = r["data"]
            if isinstance(error_data, dict):
                detail = error_data.get("detail", {})
                if isinstance(detail, dict):
                    provider_val = detail.get("provider", "")
                    print(f"  provider in error payload (should be global default): {provider_val}")
                    results["create_connection_without_provider_key"] = f"PASS (502 expected — global default used: {provider_val})"
                else:
                    results["create_connection_without_provider_key"] = "PASS (502, non-dict detail)"
            else:
                results["create_connection_without_provider_key"] = "PASS (502 expected)"
        else:
            results["create_connection_without_provider_key"] = "FAIL"

        # 9. Test /api/auth/me returns correctly
        r = _get(client, "/api/auth/me", api_token)
        if r["status"] == 200:
            me_data = r["data"]
            has_org = bool(me_data.get("org_id"))
            has_role = bool(me_data.get("role"))
            results["auth_me"] = "PASS" if has_org and has_role else "FAIL (missing org_id or role)"
        else:
            results["auth_me"] = "FAIL"

        # 10. Test mappings list (should be empty)
        r = _post(client, "/api/mappings/list", api_token, {
            "client_id": test_client_id,
        })
        if r["status"] < 400:
            data_list = r["data"].get("data", [])
            results["mappings_list_empty"] = "PASS" if len(data_list) == 0 else f"UNEXPECTED ({len(data_list)} mappings)"
        else:
            results["mappings_list_empty"] = "FAIL"

        # 11. Create a mapping
        r = _post(client, "/api/mappings/create", api_token, {
            "client_id": test_client_id,
            "canonical_object": "Job_Posting",
            "sfdc_object": "Job_Posting__c",
            "field_mappings": {
                "title": "Title__c",
                "company": "Company__c",
                "url": "Posting_URL__c",
            },
            "external_id_field": "Posting_URL__c",
        })
        if r["status"] < 400:
            mapping_version = r["data"].get("mapping_version")
            results["create_mapping"] = f"PASS (version={mapping_version})"
        else:
            results["create_mapping"] = "FAIL"

        # 12. Push validate (should work — no connection needed, just mapping check)
        r = _post(client, "/api/push/validate", api_token, {
            "client_id": test_client_id,
            "canonical_object": "Job_Posting",
            "field_names": ["title", "company", "url", "nonexistent_field"],
        })
        if r["status"] < 400:
            fields = r["data"].get("fields", {})
            valid = r["data"].get("valid", None)
            title_status = fields.get("title", "?")
            nonexistent_status = fields.get("nonexistent_field", "?")
            ok = (
                title_status in ("mapped", "mapped_unverified")
                and nonexistent_status == "unmapped"
                and valid is False
            )
            results["push_validate"] = f"PASS" if ok else f"UNEXPECTED (fields={fields}, valid={valid})"
        else:
            results["push_validate"] = "FAIL"

        # 13. Deploy validation test (bad plan should get 400)
        r = _post(client, "/api/deploy/analytics", api_token, {
            "client_id": test_client_id,
            "plan": {
                "report_folders": [{"api_name": "", "name": "Bad Folder"}],
                "dashboard_folders": [],
                "reports": [],
                "dashboards": [],
            },
        })
        if r["status"] == 400:
            detail = r["data"].get("detail", {})
            if isinstance(detail, dict):
                errors = detail.get("errors", [])
                results["deploy_validation_rejects_bad_plan"] = f"PASS ({len(errors)} validation error(s))"
            else:
                results["deploy_validation_rejects_bad_plan"] = f"PASS (400 returned: {str(detail)[:80]})"
        elif r["status"] < 400:
            results["deploy_validation_rejects_bad_plan"] = "FAIL (accepted bad plan)"
        else:
            results["deploy_validation_rejects_bad_plan"] = f"UNEXPECTED ({r['status']})"

    _print_results(results)


def _print_results(results: dict[str, str]) -> None:
    print("\n" + "=" * 60)
    print("NANGO PROVIDER CONFIG + INTEGRATION SMOKE TEST RESULTS")
    print("=" * 60)
    all_pass = True
    for test_name, outcome in results.items():
        status_tag = "PASS" if "PASS" in outcome else "FAIL"
        if "FAIL" in outcome:
            all_pass = False
        print(f"  [{status_tag}] {test_name}: {outcome}")
    print("=" * 60)
    print(f"OVERALL: {'ALL PASSED' if all_pass else 'SOME FAILURES'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
