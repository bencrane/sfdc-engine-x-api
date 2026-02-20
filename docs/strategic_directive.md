# Strategic Directive — sfdc-engine-x

Non-negotiable build rules. Every agent working in this repo must follow these.

---

## 1. Service Layer Boundary

All Salesforce API calls go through `app/services/salesforce.py`. All Nango API calls go through `app/services/token_manager.py`. No router imports `httpx`. No router calls Salesforce or Nango directly.

**Why:** One place to debug external API issues. One place to handle token refresh. One place to add rate limit retry logic.

---

## 2. Every Query Filters by org_id

No exceptions. SELECT, UPDATE, DELETE — all include `WHERE org_id = $N`. INSERT operations set `org_id` from `AuthContext`, never from request body (exception: super-admin endpoints which accept `org_id` explicitly).

Client-level operations additionally filter by `client_id` and validate the client belongs to the org via `validate_client_access`.

**Why:** A query without tenant scoping is a data breach.

---

## 3. Tokens Never Leave the Service Layer

OAuth access tokens exist only in memory within `token_manager.py` and `salesforce.py` for the duration of a single API call. They are never stored in our database, never returned in API responses, never logged, never included in error messages.

Nango holds all OAuth credentials. Our `crm_connections` table stores metadata only: status, instance_url, nango_connection_id.

**Why:** Tokens are the keys to client Salesforce orgs. Leaking one is a security incident.

---

## 4. One Commit Per Deliverable

Each deliverable in a directive gets its own commit. No multi-deliverable commits. No "cleanup" commits that mix concerns.

**Why:** Reviewable. Revertable. Traceable.

---

## 5. No Deploy Without Review

Executor agents never push to `main` or run deploy commands. They commit locally. The chief agent reviews and pushes.

**Why:** Production deploy is a one-way door. Review catches scope creep and bugs.

---

## 6. Surface Prerequisites Before Errors

If work requires env vars, migrations, config, or external setup — say so in the directive BEFORE the executor hits a runtime error. List every prerequisite explicitly.

**Why:** Debugging missing env vars wastes time and burns AI credits.

---

## 7. Salesforce API Version Pinning

Use a specific Salesforce API version (e.g., `v60.0`), set in `config.py`. Do not hardcode version strings in service functions. All service calls reference `settings.sfdc_api_version`.

**Why:** Salesforce deprecates API versions. One config change upgrades everything.

---

## 8. Deployment Plans Are Data

Deployment plans (what objects/fields/workflows to create) are JSONB payloads, not code. They are stored, diffed, and rolled back as data. The deploy service interprets them — it does not generate them.

**Why:** Separates "what to deploy" from "how to deploy." Enables conflict checking, audit trails, and rollback from stored records.

---

## 9. Field Mappings Are Per-Client

Never hardcode Salesforce field names in service logic. The push service reads `crm_field_mappings` for the target client and maps canonical fields to SFDC fields at runtime.

**Why:** Different clients may have different field names, different custom objects, or different picklist values. Hardcoding breaks the second client.

---

## 10. Errors Preserve Salesforce Context

When Salesforce returns an error (e.g., `DUPLICATE_VALUE`, `FIELD_CUSTOM_VALIDATION_EXCEPTION`), the original error code and message are preserved in the API response and in the relevant log table (push_logs, deployments). Do not swallow or generalize Salesforce errors.

**Why:** Debugging CRM issues requires the original Salesforce error. Generic "502 provider error" is useless.

---

## 11. No Business Logic

sfdc-engine-x does not decide what to push, when to push, or which clients to process. It receives instructions and executes them. Business logic lives in the calling system (data-engine-x, Trigger.dev, admin frontend).

**Why:** This service is infrastructure. Mixing business logic with CRM plumbing creates coupling that breaks when products change.

---

## 12. Soft Delete Everything

Use `is_active = FALSE` or `deleted_at` timestamps. Never hard-delete tenant data. Financial and audit records (deployments, push logs) are never deleted.

**Why:** Client data at $25K/year engagements is not disposable. Recovery matters.

---

## 13. Topology Before Deploy

The conflict check endpoint (`POST /api/conflicts/check`) should always be called before deploying. The deploy endpoint accepts an optional `conflict_report_id` linking the deployment to a prior check. A database trigger enforces that the conflict report belongs to the same org.

This is a convention, not an enforcement — the deploy endpoint does not block without a conflict check. But directives should always include the check step.

**Why:** Deploying blind into a client's Salesforce at $25K/year is unacceptable risk.

---

## 14. UUID Validation at the API Boundary

All ID fields in Pydantic request models use the `UUID` type, not `str`. This ensures invalid or empty UUIDs are caught as 422 validation errors before reaching the database. Never pass unvalidated string IDs to asyncpg queries.

**Why:** Learned the hard way — empty or malformed UUID strings cause asyncpg DataError (500) instead of a clean client error.

---

## 15. No Abandoned Dependencies

Do not use abandoned libraries. If a dependency hasn't been maintained in 2+ years, use the underlying library directly. Example: use `bcrypt` directly instead of `passlib` (abandoned 2020, incompatible with bcrypt 5.x).

**Why:** Abandoned dependencies cause runtime compatibility failures that are hard to diagnose.
