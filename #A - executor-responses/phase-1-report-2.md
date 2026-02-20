Implemented all 4 deliverables with standalone commits and no out-of-scope changes.
6fc5284 — Harden API token auth tenant and user checks.
fbe505e — Harden JWT claim and role validation.
809c85b — Handle invalid client UUIDs as not found.
7648009 — Enforce tenant integrity for deployment conflict reports.
(a) Exact SQL query changes in Deliverable 1
In app/auth/dependencies.py (_try_api_token), the WHERE clause now includes:
AND u.is_active = TRUEAND t.org_id = u.org_id
Final query section:
WHERE t.token_hash = $1  AND t.is_active = TRUE  AND u.is_active = TRUE  AND t.org_id = u.org_id  AND (t.expires_at IS NULL OR t.expires_at > NOW())
(b) JWT validation logic added in Deliverable 2
In app/auth/dependencies.py (_try_jwt):
Added required exp claim in decode:
options={"require": ["exp"]}
Switched to safe claim extraction:
org_id = payload.get("org_id")
user_id = payload.get("user_id")
role = payload.get("role")
Added explicit validation gates:
return None if any required claim is missing/falsey
return None if role is not in ROLE_PERMISSIONS
Only build AuthContext after passing those checks.
(c) UUID error handling approach in Deliverable 3
In app/auth/dependencies.py (validate_client_access):
Wrapped UUID conversions in try/except ValueError:
db_client_id = UUID(cid) if isinstance(client_id, str) else client_id
db_org_id = UUID(auth.org_id)
On parse failure, raises:
HTTPException(status_code=404, detail="Client not found")
Reused parsed values in the query, avoiding uncaught conversion exceptions and preventing error-detail leakage.
(d) Trigger function SQL in Deliverable 4
Created supabase/migrations/003_conflict_report_tenant_check.sql with:
Function: check_deployment_conflict_report_org_integrity()
Behavior:
if NEW.conflict_report_id IS NOT NULL, verifies matching row exists in crm_conflict_reports with:
id = NEW.conflict_report_id
org_id = NEW.org_id
raises exception if mismatch
allows NULL conflict_report_id
Trigger:
trg_crm_deployments_conflict_report_org_integrity
BEFORE INSERT OR UPDATE ON crm_deployments
(e) Anything to flag
ReadLints run for app/auth/dependencies.py: no linter errors.
One hardening gap remains outside this directive’s requested edits: _try_api_token still maps permissions with ROLE_PERMISSIONS.get(role, []), so an unexpected DB role would authenticate with empty permissions instead of hard-failing. Not changed because you explicitly scoped Deliverable 1 to SQL conditions only.