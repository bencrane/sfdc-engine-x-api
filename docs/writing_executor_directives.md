# Writing Executor Directives

How to write directives that executor agents can implement correctly without ambiguity.

---

## Structure

Every directive follows this template:

```
**Directive: [Name]**

**Context:** You are working on `sfdc-engine-x`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** [1-3 sentences on WHY this work matters]

**Existing code to read:** [List specific files]

---

### Deliverable 1: [Name]
[Exact instructions]
Commit standalone.

### Deliverable 2: [Name]
[Exact instructions]
Commit standalone.

[... more deliverables ...]

---

**What is NOT in scope:** [Explicit exclusions]

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) ..., (b) ..., (c) ..., (d) ..., (e) anything to flag.
```

---

## Rules

1. **List every file the agent should read before building.** Include full paths. Don't assume the agent knows where things are.

2. **Be explicit about what NOT to do.** "No deploy commands", "No database migrations", "Do not change existing routers" — state these clearly.

3. **One deliverable = one commit.** This keeps the work reviewable and revertable.

4. **"Do not push"** — the chief agent pushes after review. The executor never pushes.

5. **Include the Salesforce API details** when the work involves new Salesforce interactions. Specify the exact endpoint, HTTP method, request/response shape, and API version. Don't make the agent guess.

6. **Specify file names for new files.** Example: `app/services/topology_service.py`, not "add a topology service somewhere."

7. **Always request a report.** The "When done" section tells the agent what to report so the chief can verify without reading every line of code.

8. **Reference the service layer boundary.** Any directive involving Salesforce API calls must route through `app/services/salesforce.py`. Remind the agent: no `httpx` in routers.

9. **Reference the token manager.** Any directive that calls Salesforce must use `token_manager.py` to get a valid access token. The agent should never assume the stored token is still valid.

---

## Example: New Capability (Most Common Pattern)

```
**Directive: Topology Pull Implementation**

**Context:** You are working on `sfdc-engine-x`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** [standard text]

**Background:** We need to pull a client's full Salesforce schema (objects, fields, relationships, picklists) and store it as a versioned JSONB snapshot. This enables conflict detection before deploying custom objects.

**Salesforce API details:**
- List all objects: GET {instance_url}/services/data/v60.0/sobjects/
- Describe one object: GET {instance_url}/services/data/v60.0/sobjects/{ObjectName}/describe/
- Auth: Bearer {access_token} header
- Rate limits: 100,000 API calls per 24 hours (shared across all our calls to this client's org)

**Existing code to read:**
- `CLAUDE.md`
- `docs/STRATEGIC_DIRECTIVE.md` (rules 1, 3, 7)
- `app/services/salesforce.py` (add methods here)
- `app/services/token_manager.py` (use this for valid tokens)
- `app/routers/topology.py` (wire endpoints here)
- `app/models/topology.py` (define request/response models here)
- `supabase/migrations/001_initial_schema.sql` (understand `crm_topology_snapshots` table)

---

### Deliverable 1: Salesforce Service Methods
Add to `app/services/salesforce.py`:
- `list_sobjects(connection_id)` — calls GET /sobjects/, returns list of object names
- `describe_sobject(connection_id, object_name)` — calls GET /sobjects/{name}/describe/, returns full describe
- `pull_full_topology(connection_id)` — calls list_sobjects, then describe for each, assembles full schema dict
- All methods use `token_manager.get_valid_token(connection_id)` for auth
- Handle rate limit responses (HTTP 429) with exponential backoff
Commit standalone.

### Deliverable 2: Pydantic Models
Add to `app/models/topology.py`:
- `TopologyPullResponse`: snapshot_id, version, object_count, custom_object_count, pulled_at
- `TopologySnapshotResponse`: id, version, object_count, custom_object_count, snapshot (JSONB), pulled_at
- `TopologySnapshotListItem`: id, version, object_count, custom_object_count, pulled_at (no snapshot payload)
Commit standalone.

### Deliverable 3: Router Implementation
Implement in `app/routers/topology.py`:
- `POST /api/topology/{client_id}/pull` — validate client belongs to org, call pull_full_topology, store snapshot with incremented version, return TopologyPullResponse
- `GET /api/topology/{client_id}/latest` — return most recent snapshot
- `GET /api/topology/{client_id}/snapshots` — return list without full payload
- All endpoints require AuthContext, filter by org_id + client_id
Commit standalone.

### Deliverable 4: Tests
Add `tests/test_topology.py`:
- Test pull creates a new snapshot with version 1
- Test second pull increments version to 2
- Test latest returns most recent
- Test client belonging to different org returns 404
Mock all Salesforce API calls.
Commit standalone.

---

**What is NOT in scope:** No topology diff. No conflict checking. No deploy logic. No migrations.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) service methods added, (b) model shapes, (c) router endpoints wired, (d) test count and coverage, (e) anything to flag.
```

---

## Example: Bug Fix Directive

```
**Bug Fix Directive: Token refresh fails silently**

**Context:** You are working on `sfdc-engine-x`. Read `CLAUDE.md` before starting.

**The problem:** When a client's access token expires, `token_manager.py` attempts refresh but swallows the error on 401 response from Salesforce. The connection appears healthy but all subsequent API calls fail with 401.

**Investigation path:**
1. Read `app/services/token_manager.py` — trace the refresh flow
2. The issue is likely in the error handling after the refresh POST
3. Check if the new token is actually being stored after successful refresh

**Fix:** On refresh failure, update `crm_connections.status` to 'expired' and `error_message` with the Salesforce error. On refresh success, ensure the new access token and expiry are persisted before returning.

**Scope:** Fix in `app/services/token_manager.py` only. Do not change routers or other services. Do not deploy.

**One commit. Do not push.**

**When done:** Report back with: (a) what caused the error, (b) what you fixed, (c) how connection status is now updated.
```

---

## Example: Infrastructure Directive

```
**Phase Directive: Conflict Detection Engine**

**Context:** [standard]

**Background:** Before deploying custom objects to a client's Salesforce, we need to check their existing schema for collisions, required field gaps, and automation risks.

**Files to read before starting:** [list]

---

### Deliverable 1: Conflict Check Service
[Implementation details — what to check, how to score, how to structure output]
Commit standalone.

### Deliverable 2: Router Endpoint
[Wire the service into the conflicts router]
Commit standalone.

### Deliverable 3: Tests
[Specific test cases]
Commit standalone.

---

**What is NOT in scope:** [explicit]
**When done:** Report back with: [specific items]
```

---

## Common Mistakes to Avoid

1. **Don't say "clean up whatever looks wrong."** Be specific about what to change.

2. **Don't assume the agent knows the codebase.** Always list files to read. Even if it seems obvious.

3. **Don't combine unrelated work** in one directive. One directive = one coherent piece of work.

4. **Don't forget to specify where new files go.** "Create a service" is ambiguous. "Add methods to `app/services/salesforce.py`" is not.

5. **Don't let the agent call Salesforce from a router.** Every directive involving Salesforce calls must remind the agent about the service layer boundary.

6. **Don't skip the "existing code to read" section.** The agent needs reference patterns. Without them, it invents its own conventions.

7. **Don't forget token management.** Every Salesforce API interaction needs a valid token. The directive should explicitly reference `token_manager.py`.

8. **Don't let the agent store or log tokens.** Remind in directives that touch connection data: tokens never appear in API responses, logs, or error messages.