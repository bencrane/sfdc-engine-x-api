# CRM Read Endpoints — Implementation Record

**Branch:** `bencrane/check-linear-access`
**Date:** 2026-03-25
**Blocks:** PaidEdge BJC-189, BJC-192 (M4)

---

## Problem

sfdc-engine-x had 35 endpoints covering connect, deploy, push, and topology — but zero CRM read capability. PaidEdge needs to pull contacts, opportunities, pipeline stages, campaign membership, and object associations from clients' Salesforce instances for attribution and audience building. Without these endpoints, PaidEdge cannot query a client's live CRM data through the sfdc-engine-x API.

---

## What Was Built

11 new API endpoints across two routers, a shared HTTP client module, a new permission, Pydantic request/response models, three new Salesforce service functions, and 53 passing unit tests.

### Endpoint Summary

| # | Endpoint | Method | Router | Purpose |
|---|----------|--------|--------|---------|
| 1 | `/api/query/soql` | POST | crm | Raw SOQL proxy with DML keyword rejection |
| 2 | `/api/query/more` | POST | crm | Follow Salesforce pagination cursor |
| 3 | `/api/crm/search` | POST | crm | Structured object search with safe SOQL builder |
| 4 | `/api/crm/count` | POST | crm | Aggregate `SELECT COUNT()` with filters |
| 5 | `/api/crm/associations` | POST | crm | Relationship subquery (Contact↔Opportunity) with ID chunking |
| 6 | `/api/crm/contact-roles` | POST | crm | OpportunityContactRole lookup with ID chunking |
| 7 | `/api/crm/campaign-members` | POST | crm | CampaignMember records by campaign |
| 8 | `/api/crm/lead-conversions` | POST | crm | Converted leads with conversion metadata |
| 9 | `/api/crm/pipelines` | POST | crm | Picklist values via live Salesforce describe call |
| 10 | `/api/topology/picklist` | POST | topology | Picklist values from stored topology snapshot |
| 11 | `/api/topology/diff` | POST | topology | Compare two topology snapshot versions |

---

## Files Created

### `app/services/sfdc_client.py`

Shared `httpx.AsyncClient` lifecycle module. Follows the same `init/close/get` pattern as `app/db.py` for the asyncpg connection pool.

- `init_sfdc_client()` — Creates a shared `httpx.AsyncClient(timeout=30.0)` during app lifespan startup
- `close_sfdc_client()` — Closes the client during shutdown
- `get_sfdc_client()` — Returns the client; raises `RuntimeError` if not initialized

New CRM service functions use this shared client. Existing salesforce.py functions still create per-call clients (tracked in TODOS.md for future migration).

### `app/models/crm.py`

Pydantic v2 request and response models for all 9 CRM endpoints:

| Model | Fields | Used By |
|-------|--------|---------|
| `SOQLRequest` | `client_id: UUID`, `soql: str` | `/query/soql` |
| `SOQLResponse` | `total_size`, `done`, `records[]`, `next_records_path?` | Multiple endpoints |
| `QueryMoreRequest` | `client_id: UUID`, `next_records_path: str` | `/query/more` |
| `SearchFilter` | `field`, `op: Literal[eq,neq,gt,gte,lt,lte,like,in,not_in]`, `value: str\|list[str]` | `/crm/search`, `/crm/count`, `/crm/lead-conversions` |
| `SearchRequest` | `client_id`, `object_name`, `filters[]`, `fields[]`, `limit?`, `offset?` | `/crm/search` |
| `CountRequest` | `client_id`, `object_name`, `filters[]` | `/crm/count` |
| `CountResponse` | `count: int` | `/crm/count` |
| `AssociationRequest` | `client_id`, `source_object: Literal["Contact","Opportunity"]`, `source_ids[]`, `related_object`, `related_fields[]` | `/crm/associations` |
| `ContactRolesRequest` | `client_id`, `opportunity_ids[]` | `/crm/contact-roles` |
| `CampaignMembersRequest` | `client_id`, `campaign_id`, `fields?[]` | `/crm/campaign-members` |
| `LeadConversionsRequest` | `client_id`, `filters?[]`, `fields?[]` | `/crm/lead-conversions` |
| `PipelineRequest` | `client_id`, `object_name="Opportunity"`, `field_name="StageName"` | `/crm/pipelines` |
| `PipelineResponse` | `object_name`, `field_name`, `stages[]` | `/crm/pipelines` |

All `client_id` fields use Pydantic `UUID` type — invalid UUIDs get 422 before reaching any business logic.

### `app/routers/crm.py`

The CRM router (`APIRouter(prefix="/api", tags=["crm"])`) with 9 endpoints and supporting private functions.

**Private helpers:**

- `_get_active_connection(auth, client_id, pool)` — Queries `crm_connections` for a connected Salesforce connection scoped by `org_id` and `client_id`. Returns `nango_connection_id` and `nango_provider_config_key`. Raises 404 if no connection or no Nango ID.

- `_validate_soql(soql)` — Rejects empty/whitespace-only SOQL, semicolons, and DML keywords (`INSERT`, `UPDATE`, `DELETE`, `UPSERT`, `MERGE`, `UNDELETE`) via case-insensitive word-boundary regex. Returns 400 on violation.

- `_escape_soql_value(value)` — Escapes single quotes for SOQL string literals (`O'Brien` → `O\'Brien`).

- `_validate_field_name(field)` — Validates field names match `^[a-zA-Z_][a-zA-Z0-9_.]*$` to prevent SOQL injection via field names.

- `_build_where_clause(filters)` — Converts a list of `SearchFilter` objects into a SOQL `WHERE` clause. Maps operator enums to SOQL operators (`eq`→`=`, `in`→`IN`, etc.). Validates field names, escapes values, formats IN/NOT IN as `('val1','val2',...)`.

- `_build_soql(object_name, filters, fields, limit, offset)` — Composes a complete `SELECT ... FROM ... WHERE ... LIMIT ... OFFSET ...` query from validated components.

**Auth pattern (all 9 endpoints):**
1. `auth.assert_permission("crm.read")` — permission check
2. `validate_client_access(auth, body.client_id, pool)` — tenant isolation
3. `_get_active_connection(auth, client_id, pool)` — connection lookup
4. Salesforce API call via `salesforce.query_soql()`, `salesforce.query_more()`, or `salesforce.describe_sobject_direct()`

**ID chunking (associations and contact-roles):**

When more than 2,000 IDs are passed in `source_ids` or `opportunity_ids`, the endpoint splits them into batches of 2,000, executes sequential SOQL queries, and concatenates the results. The 2,000 limit is based on SOQL character limits — 18-char Salesforce IDs × ~22 chars with quotes/commas stays well within the 100k character limit per query.

### `tests/test_crm.py`

45 unit tests organized into 10 test classes:

| Class | Count | Coverage |
|-------|-------|----------|
| `TestSOQLValidation` | 11 | Empty, whitespace, semicolons, all 6 DML keywords, case insensitivity |
| `TestSOQLBuilder` | 9 | Simple select, eq/in/like/not_in filters, escaping, limit/offset, invalid field names, multi-filter AND |
| `TestConnectionHelper` | 3 | No connection (404), no Nango ID (404), happy path |
| `TestPermissions` | 3 | `crm.read` on all three roles |
| `TestQuerySOQL` | 3 | Happy path, pagination with `nextRecordsUrl` and `Sforce-Limit-Info`, SFDC error → 502 |
| `TestQueryMore` | 2 | Happy path, expired cursor → 502 |
| `TestDescribeSobjectDirect` | 2 | Happy path, SFDC error |
| `TestWhereClause` | 4 | Empty filters, eq clause, IN requires list, quote escaping |
| `TestSFDCClient` | 3 | Init+get, get before init (RuntimeError), close sets None |
| `TestModelValidation` | 5 | UUID validation, operator validation, source_object Literal, defaults |

### `tests/test_topology_new.py`

8 unit tests for the new topology endpoints:

| Class | Count | Coverage |
|-------|-------|----------|
| `TestTopologyDiff` | 5 | Added objects, removed objects, changed fields (type + label), `object_names` filter, no changes |
| `TestPicklist` | 3 | Picklist value extraction, missing object, missing field |

---

## Files Modified

### `app/auth/context.py`

Added `crm.read` permission to all three roles in `ROLE_PERMISSIONS`:

| Role | New Permission |
|------|---------------|
| `org_admin` | `crm.read` (added) |
| `company_admin` | `crm.read` (added) |
| `company_member` | `crm.read` (added) |

All three roles can read CRM data. The permission is separate from `topology.read` so it can be revoked independently in the future if needed.

### `app/services/salesforce.py`

Added 3 new functions at the top of the file (before existing functions). All use the shared httpx client via `get_sfdc_client()`:

**`query_soql(connection_id, soql, provider_config_key, batch_size=2000)`**
- Calls `GET /services/data/v60.0/query/?q={soql}` with `Sforce-Query-Options: batchSize=2000` header
- Fetches token via `token_manager.get_valid_token()`
- Extracts `nextRecordsUrl` from response and returns it as `next_records_path`
- Captures `Sforce-Limit-Info` response header for observability
- Returns `{total_size, done, records[], next_records_path?, sforce_limit_info?}`
- SFDC errors → `HTTPException(502)` with original error code/message

**`query_more(connection_id, next_records_path, provider_config_key)`**
- Calls `GET {instance_url}{next_records_path}` to follow pagination
- Same return format as `query_soql`
- Expired cursors (~15 min) return SFDC 404 → surfaced as 502

**`describe_sobject_direct(connection_id, object_name, provider_config_key)`**
- Calls `GET /services/data/v60.0/sobjects/{object_name}/describe/`
- Returns the full Salesforce describe payload
- Used by the `/crm/pipelines` endpoint to extract picklist values from a live describe

### `app/routers/topology.py`

Added 2 new endpoints to the existing topology router. No new router registration needed in `main.py`.

**`POST /api/topology/picklist`**
- Reads a stored JSONB topology snapshot from `crm_topology_snapshots`
- Navigates to the specified object and field within the snapshot
- Returns the `picklistValues` array from the field describe
- Supports optional `version` parameter (defaults to latest snapshot)
- Uses `topology.read` permission (not `crm.read` — this reads DB, not Salesforce)

**`POST /api/topology/diff`**
- Loads two topology snapshots by version number in a single query
- Computes set differences on object names (added/removed objects)
- For objects present in both versions: computes field-level diffs (added/removed/modified fields)
- Field modification detected by comparing `type` and `label` properties
- Optional `object_names[]` filter reduces the response payload to specified objects
- Returns `{added_objects[], removed_objects[], changed_objects[{name, added_fields[], removed_fields[], changed_fields[]}]}`

### `app/models/topology.py`

Added 6 new Pydantic models for the topology endpoints:

- `PicklistRequest` — `client_id`, `object_name`, `field_name`, optional `version`
- `PicklistResponse` — `object_name`, `field_name`, `values[]`
- `TopologyDiffRequest` — `client_id`, `version_a`, `version_b`, optional `object_names[]`
- `FieldChange` — `name`, `change_type` (added/removed/modified)
- `ObjectChange` — `name`, `added_fields[]`, `removed_fields[]`, `changed_fields[]`
- `TopologyDiffResponse` — `added_objects[]`, `removed_objects[]`, `changed_objects[]`

### `app/main.py`

Two changes:

1. **Router registration:** Imported and registered `crm_router` from `app.routers.crm`
2. **Lifespan:** Added `init_sfdc_client()` on startup and `close_sfdc_client()` on shutdown, alongside the existing `init_pool`/`close_pool` for asyncpg

### `requirements.txt`

Added:
- `pytest==8.3.0`
- `pytest-asyncio==0.24.0`

---

## Architecture

```
Client Request
     │
     ▼
FastAPI Router
     │
     ├── CRM Router (app/routers/crm.py)
     │   │
     │   ├── get_current_auth() → AuthContext
     │   ├── auth.assert_permission("crm.read")
     │   ├── validate_client_access(auth, client_id)
     │   ├── _get_active_connection(auth, client_id)
     │   │       └── DB: SELECT nango_connection_id, nango_provider_config_key
     │   │              FROM crm_connections WHERE org_id=$1 AND client_id=$2
     │   │
     │   └── salesforce.query_soql() / query_more() / describe_sobject_direct()
     │           │
     │           ├── token_manager.get_valid_token(connection_id)
     │           │       └── Nango API → access_token + instance_url
     │           │
     │           └── get_sfdc_client() → shared httpx.AsyncClient
     │                   └── Salesforce REST API → Response
     │
     └── Topology Router (app/routers/topology.py)
         │
         ├── get_current_auth() → AuthContext
         ├── auth.assert_permission("topology.read")
         ├── validate_client_access(auth, client_id)
         │
         └── DB: SELECT snapshot FROM crm_topology_snapshots
                 └── Python diff/extract → Response
```

**Key architectural decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Permission model | New `crm.read` permission | Separable from `topology.read` — can revoke CRM access without breaking topology |
| SOQL injection prevention | DML keyword regex + semicolon block (raw proxy); operator whitelist + value escaping (structured search) | Defense in depth — Salesforce also rejects DML but we fail fast at 400 |
| Pagination | Single-page passthrough + `/query/more` | Matches Salesforce's native pattern; avoids buffering entire result sets |
| Filter design | Generic `{field, op, value}` model | No field assumptions — works with any Salesforce object |
| ID chunking | 2,000 per batch | Based on SOQL character limit analysis — well within 100k chars |
| Shared HTTP client | `sfdc_client.py` with init/close/get | Connection pooling, matches `db.py` pattern, new functions use it |
| Topology endpoints in topology router | Picklist and diff read from DB, not Salesforce | Different auth (`topology.read`), different data source (stored snapshots) |

---

## SOQL Injection Prevention

### Raw SOQL proxy (`/api/query/soql`)

The `_validate_soql()` function rejects queries before they reach Salesforce:

1. Empty or whitespace-only SOQL → 400
2. Queries containing semicolons → 400
3. Queries containing DML keywords at word boundaries → 400
   - Blocked: `INSERT`, `UPDATE`, `DELETE`, `UPSERT`, `MERGE`, `UNDELETE`
   - Case-insensitive matching via `\b` word boundary regex

### Structured search (`/api/crm/search`)

The `_build_soql()` function constructs SOQL safely:

1. Field names validated against `^[a-zA-Z_][a-zA-Z0-9_.]*$` — prevents injection via field names
2. Operators whitelisted to a fixed map (`eq`→`=`, `neq`→`!=`, etc.) — no arbitrary SQL operators
3. String values escaped: single quotes doubled (`O'Brien` → `O\'Brien`)
4. IN/NOT IN values formatted as `('val1','val2',...)` with each value escaped
5. LIMIT and OFFSET cast to `int()` — no string injection

---

## Error Handling

| Codepath | Error | HTTP Code | User Sees |
|----------|-------|-----------|-----------|
| Raw SOQL with DML keyword | Validation | 400 | "SOQL query cannot contain DML keywords" |
| Empty SOQL string | Validation | 400 | "SOQL query cannot be empty" |
| SOQL with semicolons | Validation | 400 | "SOQL query cannot contain semicolons" |
| Invalid `next_records_path` format | Validation | 400 | "Invalid next_records_path format" |
| Empty `source_ids` or `opportunity_ids` | Validation | 400 | "source_ids cannot be empty" |
| Invalid field name in filter | Validation | 400 | "Invalid field name: {field}" |
| Invalid UUID in `client_id` | Pydantic | 422 | Pydantic validation error |
| No active Salesforce connection | DB lookup | 404 | "No active Salesforce connection" |
| Connection has no Nango ID | DB lookup | 404 | "Connection has no Nango connection ID" |
| Client not in org | Tenant isolation | 404 | "Client not found" |
| Missing `crm.read` permission | Auth | 403 | "Insufficient permissions" |
| Salesforce API error | SFDC response | 502 | Original SFDC error code + message |
| Malformed Salesforce response | Response parse | 502 | "Salesforce query response was not an object" |
| Expired pagination cursor | SFDC 404 | 502 | SFDC error forwarded |
| Field not found on object (pipelines) | Describe result | 404 | "Field {name} not found on {object}" |

---

## Test Results

```
53 passed in 1.40s

tests/test_crm.py             — 45 tests
tests/test_topology_new.py    —  8 tests
```

Run with: `DATABASE_URL=postgresql://test:test@localhost/test JWT_SECRET=test-secret .venv/bin/python -m pytest tests/test_crm.py tests/test_topology_new.py -v`

Or with Doppler: `doppler run -- pytest tests/test_crm.py tests/test_topology_new.py -v`

---

## Request/Response Examples

### SOQL Proxy

```json
// POST /api/query/soql
{
  "client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "soql": "SELECT Id, Name, Email FROM Contact WHERE AccountId = '001xx000003GHPN' LIMIT 10"
}

// Response
{
  "total_size": 3,
  "done": true,
  "records": [
    {"Id": "003xx000004ABCD", "Name": "Jane Doe", "Email": "jane@acme.com"},
    {"Id": "003xx000004EFGH", "Name": "John Smith", "Email": "john@acme.com"},
    {"Id": "003xx000004IJKL", "Name": "Bob Jones", "Email": "bob@acme.com"}
  ],
  "next_records_path": null
}
```

### Structured Search

```json
// POST /api/crm/search
{
  "client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "object_name": "Contact",
  "filters": [
    {"field": "AccountId", "op": "eq", "value": "001xx000003GHPN"},
    {"field": "Email", "op": "like", "value": "%@acme.com"}
  ],
  "fields": ["Id", "Name", "Email", "Title"],
  "limit": 50
}
```

### Count

```json
// POST /api/crm/count
{
  "client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "object_name": "Contact",
  "filters": [
    {"field": "MailingState", "op": "eq", "value": "CA"}
  ]
}

// Response
{"count": 1247}
```

### Associations

```json
// POST /api/crm/associations
{
  "client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "source_object": "Contact",
  "source_ids": ["003xx000004ABCD", "003xx000004EFGH"],
  "related_object": "OpportunityContactRole",
  "related_fields": ["Id", "OpportunityId", "Role"]
}
```

### Topology Diff

```json
// POST /api/topology/diff
{
  "client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version_a": 1,
  "version_b": 3,
  "object_names": ["Account", "Contact"]
}

// Response
{
  "added_objects": [],
  "removed_objects": [],
  "changed_objects": [
    {
      "name": "Contact",
      "added_fields": ["Custom_Score__c"],
      "removed_fields": [],
      "changed_fields": [
        {"name": "Phone", "change_type": "modified"}
      ]
    }
  ]
}
```

---

## What Already Existed (Reused)

| Existing Code | How Reused |
|---------------|-----------|
| `salesforce._parse_salesforce_error()` | Direct reuse for SFDC error handling in new functions |
| `salesforce._sfdc_headers()` | Direct reuse for auth headers |
| `salesforce._sfdc_base_url()` | Direct reuse for URL construction |
| `token_manager.get_valid_token()` | Direct reuse for Nango token fetch |
| `validate_client_access()` | Direct reuse for tenant isolation |
| `get_current_auth()` | Direct reuse as FastAPI dependency |
| `db.py` init/close/get pattern | Pattern copied for `sfdc_client.py` |
| `crm_connections` table | Connection lookup query pattern adapted for private helper |
| `crm_topology_snapshots` table | Queried by new topology endpoints |
| `topology.py` router | Extended with 2 new endpoints (no new router needed) |

---

## Known Limitations

1. **Dual HTTP client pattern:** New CRM functions use the shared `httpx.AsyncClient` via `sfdc_client.py`. Existing functions in `salesforce.py` (topology pull, describe, deploy, push) still create per-call clients. Migration is tracked in TODOS.md.

2. **Shutdown race:** If a request is in-flight when the shared httpx client closes during shutdown, it could get an error. Low risk — only occurs during deploy. Accepted.

3. **Topology diff memory:** Loading two full JSONB topology snapshots for large orgs (1,300+ objects) may consume several MB. The `object_names[]` filter reduces the response payload but not server-side memory (full snapshots are still loaded). Acceptable for current traffic volume.

4. **`source_object` constraint:** `AssociationRequest.source_object` is constrained to `Literal["Contact", "Opportunity"]`. Can be relaxed to `str` in a future PR if PaidEdge needs other object relationships.

---

## Deferred Work (in TODOS.md)

| Item | Effort | Depends On |
|------|--------|------------|
| Bulk API 2.0 support for large dataset queries | M | This PR |
| Migrate existing salesforce.py to shared httpx client | M | This PR |
| Activity/Task history pull for attribution | M | This PR |
