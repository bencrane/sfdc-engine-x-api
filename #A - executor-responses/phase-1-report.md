I’m doing a read-only foundation audit focused on auth boundaries, RBAC correctness, and migration integrity. First step is to read the specified files and cross-check implementation against the architecture permission matrix.
I’ve finished the read-only inspection and cross-checked auth/RBAC against the architecture matrix. I’m now compiling findings by severity with concrete file/function references and expected correct behavior.## Critical Findings (must fix before Phase 2)
app/auth/dependencies.py → _try_api_token(): inactive users can still authenticate via active API tokens.
Query filters t.is_active and token expiry, but does not enforce u.is_active = TRUE. A deactivated user can retain API access if their token remains active.
Correct behavior: token auth must require both active token and active user.
app/auth/dependencies.py → _try_jwt(): JWTs without exp are accepted (no required-claims enforcement).
jwt.decode(..., algorithms=["HS256"]) verifies expiry only if exp exists; missing exp is currently not rejected. That permits non-expiring session tokens if issuance ever omits exp.
Correct behavior: require exp, org_id, user_id, and role claims at decode/validation time; reject token if any are missing.
supabase/migrations/002_field_mappings_and_fixes.sql → crm_deployments.conflict_report_id: cross-tenant linkage possible.
FK references only crm_conflict_reports(id), so a deployment row could reference a conflict report from another org/client if an ID is supplied. This is a tenant-integrity boundary issue at relational level.
Correct behavior: enforce org/client consistency for this link (composite key strategy or trigger validation on insert/update).
Important Findings (fix soon)
app/auth/dependencies.py → _try_jwt(): missing required claims can throw unhandled exception (500).
Code uses payload["org_id"] and payload["user_id"] directly. If token is otherwise decodable but missing claim(s), this raises KeyError and returns 500 instead of 401.
Correct behavior: treat missing claims as authentication failure and return 401 consistently.
app/auth/dependencies.py → validate_client_access(): invalid UUID input can raise uncaught ValueError (500).
UUID(cid) and UUID(auth.org_id) are not guarded. Malformed values produce server error instead of controlled 400/401/404.
Correct behavior: normalize/validate UUIDs with explicit error handling and return deterministic HTTP errors.
app/auth/dependencies.py → _try_jwt(): unknown roles are accepted with empty permissions.
ROLE_PERMISSIONS.get(role, []) allows authentication to succeed for unsupported role values. This may not bypass authorization directly, but it allows invalid principal states into request handling.
Correct behavior: reject JWTs with roles outside allowed enum.
Minor Findings (can defer)
app/auth/dependencies.py → _try_api_token(): last_used_at updated on every request adds write amplification.
This is functionally correct but can become hot-write overhead under load.
Correct behavior: optionally throttle/batch (e.g., update if older than N minutes) if performance pressure appears.
app/auth/context.py → assert_client_access(): string comparison on client_id may false-deny non-canonical UUID formatting.
If IDs vary in representation (case/hyphen formatting), strict string compare can reject legitimate access.
Correct behavior: compare normalized UUID values.
app/config.py: several sensitive settings default to empty string (sfdc_client_id, sfdc_client_secret, sfdc_redirect_uri, super_admin_jwt_secret).
This can defer failure to runtime and produce silent misconfiguration in non-auth flows until first use.
Correct behavior: require non-empty values for required runtime paths, or validate strongly at startup per environment mode.
app/db.py: pool sizing (min_size=2, max_size=10) is reasonable baseline; no explicit statement/command timeout controls.
Not a bug, but operational robustness may depend on external defaults.
Correct behavior: consider explicit timeouts when moving to higher-load environments.
Explicit checks requested
JWT algorithm pinning / alg:none bypass: algorithms=["HS256"] is pinned correctly; this part looks safe.
“Could super-admin JWT accidentally pass?” Not if it is signed with a distinct secret from jwt_secret. Current decode path uses only settings.jwt_secret, so a token signed with SUPER_ADMIN_JWT_SECRET should fail unless secrets are misconfigured equal.
SHA-256 for API token lookup: appropriate for high-entropy API tokens in lookup context (different threat model than password hashing).
RBAC Matrix Verification
app/auth/context.py ROLE_PERMISSIONS matches docs/ARCHITECTURE.md matrix exactly:
org_admin: all listed permissions
company_admin: connections.read, topology.read, workflows.read
company_member: connections.read, topology.read
assert_client_access() policy intent is correct: company-scoped users restricted to assigned client_id; org admins (client_id=None) can access any client in org.
Migration 002 Focus Check
crm_field_mappings schema is structurally aligned with canonical-object mapping per client:
tenant keys (org_id, client_id), object identity (canonical_object, sfdc_object), JSONB map payload, active flag, uniqueness by (org_id, client_id, canonical_object).
check_user_client_org_integrity() correctly handles NULL client_id for org admins.
conflict_report_id FK exists but needs tenant-consistency enforcement (critical finding above).
Anything else to flag
In app/auth/dependencies.py, token auth query joins api_tokens to users by user_id but does not explicitly enforce t.org_id = u.org_id. If bad data is inserted, auth context could combine token org with user role/client from another org.
This is primarily data-integrity hardening, but worth tightening alongside the critical auth fixes.