# CLAUDE.md

Authoritative context for AI agents working in `sfdc-engine-x`.

---

## What This Is

sfdc-engine-x is a multi-tenant API service that provides programmatic Salesforce administration for client organizations. It is a remote control for clients' Salesforce instances — connect, read, deploy, push, and remove — all through API, without ever logging into a client's Salesforce org.

This is **not** a Salesforce app or plugin. It is infrastructure that organizations (RevOps firms, agencies, service providers) use to manage their clients' Salesforce instances via API contracts.

## Who Uses It

- **Organizations (orgs):** RevOps firms, staffing agencies, service providers. Each org is a tenant.
- **Clients:** The org's customers whose Salesforce instances are being managed.
- **Users:** People at the org who interact with the system (org admins, company admins, operators).

Revenue Activation is the first org. Staffing Activation is a use case within RA. Other RevOps firms can onboard as separate orgs in the future.

## What It Does

| Capability | Description |
|-----------|-------------|
| **Connect** | OAuth flow via Nango — client authorizes, Nango stores and manages tokens |
| **Read** | Pull full CRM topology — objects, fields, relationships, picklists |
| **Deploy** | Create/update custom objects, fields, layouts, workflows, assignment rules in client's Salesforce |
| **Push** | Upsert records, update statuses, link relationships |
| **Remove** | Clean up deployed objects/fields/workflows on client churn |

All operations are scoped by org_id and client_id. An org never sees another org's data. A client's connection is never accessible by another client.

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| API Framework | FastAPI (Python 3.13) | Async, Pydantic models, dependency injection for AuthContext |
| Deployment | Railway (Dockerfile) | Docker build, SSL, auto-deploy on push to main |
| Database | Supabase Postgres via asyncpg | Direct connection, async, no ORM overhead |
| Secrets | Doppler | Centralized secrets management, injected at runtime |
| Auth | API tokens (SHA-256 hash) + JWT (HS256) | Machine-to-machine (tokens) and user sessions (JWT) |
| OAuth | Nango | Manages Salesforce OAuth flow, token storage, automatic refresh |
| Password Hashing | bcrypt (direct) | No passlib — direct bcrypt library |
| HTTP Client | httpx | Async HTTP for Salesforce and Nango API calls |
| External API | Salesforce REST + Tooling + Metadata APIs | All CRM operations via stored OAuth tokens in Nango |

**No Modal.** This service handles straightforward request/response operations. No serverless compute needed.

---

## Multi-Tenancy Model

### Three Tiers

```
Tier 1: Organization    — The business (RA, future RevOps firms)
Tier 2: Client           — Customer of that org (Acme Corp, etc.)
Tier 3: User             — Person at the org
```

### Key Rule

> **Every database query must filter by `org_id`.** No exceptions.

Company-level resources additionally filter by `client_id` after validating the client belongs to the org.

### Denormalization

Child tables include `org_id` even when they reference a parent that already has it. This avoids joins for tenant filtering and provides defense in depth. Tenant integrity triggers enforce that `client_id` belongs to `org_id` on insert/update.

---

## Auth Model

### Three Auth Methods

**Super-Admin** (bootstrap only):
- Bearer token matches `SUPER_ADMIN_JWT_SECRET` (constant-time comparison via `hmac.compare_digest`)
- Used only for: org creation, first user creation
- No JWT, no DB lookup — shared secret IS the token

**API Tokens** (machine-to-machine):
- SHA-256 hashed and stored in `api_tokens` table
- Looked up on each request → returns org_id, user_id, role
- Query enforces both `t.is_active = TRUE` and `u.is_active = TRUE`
- Used by: data-engine-x, trigger.dev tasks, external integrations

**JWT Sessions** (user login):
- Issued on login, signed with `JWT_SECRET` (HS256)
- Contains: `org_id`, `user_id`, `role`, `client_id`, `exp`
- `exp` claim is required — tokens without expiry are rejected
- Required claims validated: `org_id`, `user_id`, `role` must all be present
- Unknown roles (not in ROLE_PERMISSIONS) are rejected
- Used by: admin frontend, user-facing interfaces

### AuthContext

All auth methods produce the same AuthContext object, injected into every endpoint via FastAPI dependency:

```python
@dataclass
class AuthContext:
    org_id: str
    user_id: str
    role: str              # org_admin, company_admin, company_member
    permissions: list[str] # derived from role via ROLE_PERMISSIONS
    client_id: str | None  # set for company-scoped users
    auth_method: str       # "api_token" or "session"
```

### RBAC

| Role | Scope |
|------|-------|
| `org_admin` | Full access — manage connections, deploy, push, manage users/clients |
| `company_admin` | Client-scoped — view connections, topology, workflows |
| `company_member` | Client-scoped — read-only |

### Permissions Matrix

| Permission | org_admin | company_admin | company_member |
|-----------|-----------|---------------|----------------|
| `connections.read` | ✓ | ✓ | ✓ |
| `connections.write` | ✓ | | |
| `topology.read` | ✓ | ✓ | ✓ |
| `deploy.write` | ✓ | | |
| `push.write` | ✓ | | |
| `workflows.read` | ✓ | ✓ | |
| `workflows.write` | ✓ | | |
| `org.manage` | ✓ | | |

---

## OAuth + Token Management (Nango)

Nango handles the full Salesforce OAuth lifecycle:

1. Our API creates a Nango connect session → returns a token for the frontend
2. Frontend uses the token with Nango's Connect UI → user authorizes in Salesforce
3. Nango exchanges the code for tokens, stores them, handles refresh automatically
4. Our `token_manager.py` calls Nango to get a fresh access token before each Salesforce API call

**Tokens never touch our database.** Nango holds all OAuth credentials. Our `crm_connections` table stores metadata only: status, instance_url, sfdc_org_id, nango_connection_id.

The `client_id` (UUID) is used as the Nango `connectionId`.

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `organizations` | Tenant orgs |
| `clients` | Org's customers (the staffing agencies, etc.) |
| `users` | People at the org with roles and password hashes |
| `api_tokens` | SHA-256 hashed machine-to-machine auth tokens |
| `crm_connections` | Connection metadata — status, instance_url, nango_connection_id per client |
| `crm_topology_snapshots` | Full CRM schema snapshots (JSONB), versioned per client |
| `crm_deployments` | Log of what was deployed — objects, fields, workflows, with optional conflict_report_id |
| `crm_conflict_reports` | Pre-deploy conflict check results (green/yellow/red) |
| `crm_push_logs` | Record push history with success/fail counts |
| `crm_field_mappings` | Canonical-to-SFDC field mapping per client per object |

All tenant-scoped tables have `org_id` with NOT NULL constraint, foreign key, index, and tenant integrity triggers.

---

## API Conventions

- **All endpoints use POST** (except `GET /health` and `GET /api/auth/me`) — parameters in request body as JSON
- **UUID fields in request bodies use Pydantic `UUID` type** — invalid UUIDs get 422 before reaching the database
- **AuthContext injected on every endpoint** via dependency
- **Every query scoped by org_id** at minimum
- **Thin endpoints** — validate, call Salesforce or DB, return
- **Salesforce errors surfaced as 502** with original SFDC error code and message preserved

### Error Codes

| Code | Meaning |
|------|---------|
| 401 | Missing or invalid auth token |
| 403 | Valid token but insufficient permissions |
| 404 | Resource not found or belongs to different org |
| 400 | Invalid request payload |
| 422 | Invalid request format (Pydantic validation, e.g., bad UUID) |
| 502 | Salesforce or Nango API error |

---

## API Endpoints

### Super-Admin (bootstrap)
- `POST /api/super-admin/orgs` — create an organization
- `POST /api/super-admin/users` — create a user in any org

### Auth
- `POST /api/auth/login` — issue JWT session token
- `GET /api/auth/me` — return current auth context with role and permissions

### Clients
- `POST /api/clients/create` — create a client for the org
- `POST /api/clients/list` — list clients for the org
- `POST /api/clients/get` — get client details

### Users
- `POST /api/users/create` — create a user in the org
- `POST /api/users/list` — list users in the org

### API Tokens
- `POST /api/tokens/create` — create API token (raw token returned once, never again)
- `POST /api/tokens/list` — list tokens (never exposes token value)
- `POST /api/tokens/revoke` — soft-deactivate a token

### Connections
- `POST /api/connections/create` — initiate OAuth via Nango connect session
- `POST /api/connections/callback` — confirm connection after OAuth completes
- `POST /api/connections/list` — list connections for org (or specific client)
- `POST /api/connections/get` — get connection details and status
- `POST /api/connections/refresh` — force token refresh via Nango
- `POST /api/connections/revoke` — disconnect a client's Salesforce

### Topology
- `POST /api/topology/pull` — pull and store client's full CRM schema
- `POST /api/topology/get` — retrieve latest (or specific version) stored snapshot
- `POST /api/topology/history` — list snapshot versions (no JSONB payload)

### Conflicts (not yet implemented)
- `POST /api/conflicts/check` — run pre-deploy conflict analysis
- `POST /api/conflicts/get` — retrieve a specific conflict report

### Deploy (not yet implemented)
- `POST /api/deploy/custom-objects` — create/update custom objects and fields
- `POST /api/deploy/workflows` — create/update Flows, assignment rules
- `POST /api/deploy/status` — check deployment status
- `POST /api/deploy/rollback` — remove deployed objects/fields/workflows

### Push (not yet implemented)
- `POST /api/push/records` — upsert records into client's Salesforce
- `POST /api/push/validate` — preflight mapping validation for push payloads
- `POST /api/push/status-update` — update field values on existing records
- `POST /api/push/link` — create relationships between records

### Mappings
- `POST /api/mappings/create` — create canonical-to-SFDC mapping for a client/object
- `POST /api/mappings/get` — get one active mapping for a canonical object
- `POST /api/mappings/list` — list active mappings for a client
- `POST /api/mappings/update` — update active mapping fields/object/external ID
- `POST /api/mappings/deactivate` — deactivate an active mapping

### Workflows (not yet implemented)
- `POST /api/workflows/list` — list active automations
- `POST /api/workflows/deploy` — create/update automation rules
- `POST /api/workflows/remove` — delete deployed automations

### Internal
- `GET /health` — health check (no auth)

---

## Directory Structure

```
sfdc-engine-x/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, lifespan (db pool), mount routers
│   ├── config.py                # Pydantic Settings from env vars
│   ├── db.py                    # asyncpg connection pool (init/close/get)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── context.py           # AuthContext dataclass, ROLE_PERMISSIONS
│   │   └── dependencies.py      # get_current_auth, validate_client_access
│   ├── models/
│   │   ├── __init__.py
│   │   ├── connections.py       # (empty — models inline in router)
│   │   ├── mappings.py          # Pydantic models for mapping endpoints
│   │   ├── topology.py          # Pydantic models for topology endpoints
│   │   └── deployments.py       # (empty — future)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── admin.py             # Super-admin: org + user creation
│   │   ├── auth.py              # Login + /me
│   │   ├── clients.py           # Client CRUD
│   │   ├── users.py             # User management
│   │   ├── tokens.py            # API token lifecycle
│   │   ├── connections.py       # OAuth connections via Nango
│   │   ├── mappings.py          # Mapping CRUD endpoints
│   │   ├── topology.py          # Topology pull + snapshots
│   │   ├── conflicts.py         # (empty — Phase 5)
│   │   ├── deploy.py            # (empty — Phase 5)
│   │   ├── push.py              # (empty — Phase 6)
│   │   └── workflows.py         # (empty — Phase 7)
│   └── services/
│       ├── __init__.py
│       ├── salesforce.py        # Salesforce REST API calls (list/describe objects)
│       └── token_manager.py     # Nango client (get token, create session, delete)
├── supabase/
│   └── migrations/
│       ├── 001_initial_schema.sql
│       ├── 002_field_mappings_and_fixes.sql
│       ├── 003_conflict_report_tenant_check.sql
│       ├── 004_nango_connection_id.sql
│       └── 005_mapping_version.sql
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── system_overview.md
│   ├── strategic_directive.md
│   ├── chief_agent_directive.md
│   └── writing_executor_directives.md
├── tests/
│   └── __init__.py
├── .env.example
├── .gitignore
├── Dockerfile
├── railway.toml
├── requirements.txt
├── README.md
└── CLAUDE.md
```

---

## Environment Variables

All secrets managed via Doppler. On Railway, set `DOPPLER_TOKEN` only — Doppler injects the rest at runtime via the Dockerfile CMD.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Supabase Postgres direct connection string |
| `JWT_SECRET` | JWT signing secret (HS256) |
| `SUPER_ADMIN_JWT_SECRET` | Separate secret for super-admin bearer auth |
| `SFDC_CLIENT_ID` | Salesforce connected app client ID |
| `SFDC_CLIENT_SECRET` | Salesforce connected app client secret |
| `SFDC_REDIRECT_URI` | OAuth callback URL (points to Nango) |
| `NANGO_SECRET_KEY` | Nango API secret key |
| `NANGO_BASE_URL` | Nango API base URL (default: `https://api.nango.dev`) |
| `NANGO_PROVIDER_CONFIG_KEY` | Nango integration ID (default: `salesforce`) |

---

## Key Principles

1. **sfdc-engine-x never decides business logic.** It executes what the org tells it to.
2. **One Salesforce connected app, unlimited client connections.** Per-client OAuth managed by Nango.
3. **Tokens are managed by Nango.** Access tokens are refreshed transparently. They never touch our database, logs, or API responses.
4. **Everything is logged.** Deployments, pushes, topology pulls — all recorded with timestamps, org_id, client_id.
5. **Clean up is a first-class operation.** Deployments can be rolled back.
6. **Service layer boundary.** All Salesforce API calls go through `app/services/salesforce.py`. All Nango calls go through `app/services/token_manager.py`. No router calls external APIs directly.

---

## Common Commands

```bash
# Run locally (Doppler injects secrets)
doppler run -- .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Run tests
doppler run -- pytest tests/ -v

# Run a migration
psql "$DATABASE_URL" -f supabase/migrations/0XX_*.sql

# Deploy to Railway (auto-deploys on push to main)
git push origin main
```

---

## Build Progress

| Phase | Status | What |
|-------|--------|------|
| 1 | ✅ Verified | Foundation — config, db pool, auth context/dependency, app shell |
| 2 | ✅ Verified | Auth + Clients + Users + API Tokens |
| 3 | ✅ Verified (live) | OAuth Connections via Nango |
| 4 | ✅ Verified (live) | Topology Pull + Snapshots (1,328 objects from real Salesforce) |
| 5A | ✅ Verified (live) | Conflict Detection — green/yellow/red scoring against real topology |
| 5B | ✅ Built | Deploy + Rollback — Metadata API for objects, Tooling API for fields. Object deploy + rollback verified. Field visibility pending API limit reset. |
| 6 | ✅ Verified (live) | Push + Field Mappings — mapping CRUD, preflight validation, version pinning, and composite upserts verified against real Salesforce |
| 7 | 🔲 Next | Workflows — Flow/assignment rule deployment via Metadata API |

### Known Issues
- **Deploy field visibility:** Custom fields deployed via Metadata API were not visible in describe during testing. Likely caused by API rate limit exhaustion (REQUEST_LIMIT_EXCEEDED on Developer Edition). Pending verification after limit reset.
- **Describe error surfacing:** Fixed — describe_sobject now returns structured error payloads instead of silently returning None. Errors are captured in `describe_errors` in topology snapshots.
