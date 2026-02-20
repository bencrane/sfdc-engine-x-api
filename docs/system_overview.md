# System Overview: sfdc-engine-x

Comprehensive documentation of the system. Written for AI agents or human engineers who need full context to continue development.

---

## What This System Is

`sfdc-engine-x` is a multi-tenant API service for programmatic Salesforce administration. It allows organizations (RevOps firms, agencies, internal teams) to manage their clients' Salesforce instances entirely through API — without ever logging into a client's Salesforce org.

One Salesforce connected app serves all tenants. Each client authorizes via OAuth (managed by Nango). From that point on, the owning organization can read schemas, deploy custom objects, create workflows, push records, and clean up — all through sfdc-engine-x endpoints.

This is standalone infrastructure. It is not embedded in any product. Multiple products consume it:
- **Staffing Activation** — deploys job posting objects, pushes enriched leads daily
- **Revenue Activation** — manages client CRM schemas, pushes enriched pipeline data
- **Future RevOps firms** — onboard as new orgs, same API, full isolation

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| API Framework | FastAPI (Python 3.13) | Async, Pydantic models, dependency injection for AuthContext |
| Deployment | Railway (Dockerfile) | Docker build, SSL, auto-deploy on push to main |
| Database | Supabase Postgres via asyncpg | Direct connection, async, no ORM overhead |
| Secrets | Doppler | Centralized secrets management, injected at runtime |
| Auth | API tokens (SHA-256 hash) + JWT (HS256) | Machine-to-machine (tokens) and user sessions (JWT) |
| OAuth | Nango | Manages Salesforce OAuth flow, token storage, automatic refresh |
| Password Hashing | bcrypt (direct) | No passlib — direct bcrypt library |
| HTTP Client | httpx | Async HTTP for Salesforce and Nango API calls |
| External API | Salesforce REST + Tooling + Metadata APIs | All CRM operations via stored OAuth tokens in Nango |

### Why No Modal / Trigger.dev

sfdc-engine-x handles request/response workloads: OAuth flows, schema reads, record pushes, deployment operations. No long-running compute, no batch processing, no orchestration. FastAPI on Railway is sufficient.

Scheduling (e.g., daily pushes) is handled by external orchestrators (Trigger.dev, data-engine-x) that call sfdc-engine-x endpoints. This service does not schedule its own work.

---

## Architecture

### Execution Flow

```
External caller (data-engine-x, Trigger.dev, admin frontend)
  → Authenticates with API token, JWT, or super-admin bearer token
  → Calls sfdc-engine-x endpoint (e.g., POST /api/topology/pull)
    → Auth dependency extracts org_id, validates permissions
    → Router validates request, delegates to service layer
    → Service layer looks up client's connection (nango_connection_id, instance URL)
    → token_manager.py calls Nango API to get a fresh access token
    → Service calls Salesforce API using client's credentials
    → Result persisted (topology snapshot, deployment record, push log)
    → Response returned to caller
```

### Key Architectural Patterns

**One Connected App, Many Connections:** A single Salesforce connected app (one client_id + secret) serves all orgs and all clients. Each client's OAuth produces a unique connection managed by Nango. Our database stores metadata only — not tokens.

**Token Lifecycle via Nango:** Access tokens expire (~1-2 hours). `token_manager.py` calls Nango's API to get a fresh access token before any Salesforce API call. Nango handles token refresh automatically. Tokens never touch our database, logs, or API responses.

**Topology Snapshots:** Full CRM schema captured as versioned JSONB. Enables conflict detection before deploying, diffing over time, and understanding client's CRM structure without manual inspection.

**Deployment Tracking:** Every custom object, field, and workflow deployed by sfdc-engine-x is logged. Enables rollback on churn and audit trail of what was changed.

**Field Mapping Layer:** Canonical data shapes (e.g., `job_posting` with `job_title`, `company_name`) are mapped to client-specific Salesforce field names (e.g., `Job_Title__c`). The push endpoint reads mappings, not hardcoded field names.

**Service Layer Boundary:** No router directly calls Salesforce or Nango. All Salesforce API calls go through `app/services/salesforce.py`. All Nango calls go through `app/services/token_manager.py`. Routers never call external APIs directly.

---

## Multi-Tenancy Model

### Three Tiers

```
Tier 1: Organization   — The business (Revenue Activation, future RevOps firms)
Tier 2: Client          — A customer of that org whose Salesforce is being managed
Tier 3: User            — A person at that org who interacts with the API
```

### Query Scoping

Every query filters by `org_id`. Client-level queries add `client_id` after validating the client belongs to the org:

```sql
-- Org-level: all clients in my org
WHERE org_id = $1

-- Client-level: Acme's connection
WHERE org_id = $1 AND client_id = $2
```

### Denormalization

All child tables carry `org_id` for direct filtering without joins. Tenant integrity triggers enforce that `client_id` always belongs to the `org_id` on the same row.

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
|---|---|
| `org_admin` | Full access — manage connections, deploy, push, manage users/clients |
| `company_admin` | Client-scoped — view connections, topology, workflows |
| `company_member` | Client-scoped — read-only |

### Permissions Matrix

| Permission | org_admin | company_admin | company_member |
|---|---|---|---|
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

1. Our API creates a Nango connect session → returns a session token for the frontend
2. Frontend uses the token with Nango's Connect UI → user authorizes in Salesforce
3. Nango exchanges the authorization code for tokens, stores them, handles refresh automatically
4. Our `POST /api/connections/callback` endpoint confirms the connection and stores metadata (status, instance_url, sfdc_org_id, nango_connection_id)
5. On every Salesforce API call, `token_manager.py` calls Nango to get a fresh access token

**Tokens never touch our database.** Nango holds all OAuth credentials. Our `crm_connections` table stores metadata only: status, instance_url, sfdc_org_id, nango_connection_id.

The `client_id` (UUID) is used as the Nango `connectionId`.

---

## API Conventions

- **All endpoints use POST** (except `GET /health` and `GET /api/auth/me`) — parameters in request body as JSON
- **UUID fields in request bodies use Pydantic `UUID` type** — invalid UUIDs get 422 before reaching the database
- **AuthContext injected on every endpoint** via dependency
- **Every query scoped by org_id** at minimum
- **Thin endpoints** — validate, call Salesforce or DB, return
- **Salesforce errors surfaced as 502** with original SFDC error code and message preserved

---

## API Endpoints

### Super-Admin (bootstrap) — ✅ Implemented
- `POST /api/super-admin/orgs` — create an organization
- `POST /api/super-admin/users` — create a user in any org

### Auth — ✅ Implemented
- `POST /api/auth/login` — issue JWT session token
- `GET /api/auth/me` — return current auth context with role and permissions

### Clients — ✅ Implemented
- `POST /api/clients/create` — create a client for the org
- `POST /api/clients/list` — list clients for the org
- `POST /api/clients/get` — get client details

### Users — ✅ Implemented
- `POST /api/users/create` — create a user in the org
- `POST /api/users/list` — list users in the org

### API Tokens — ✅ Implemented
- `POST /api/tokens/create` — create API token (raw token returned once, never again)
- `POST /api/tokens/list` — list tokens (never exposes token value)
- `POST /api/tokens/revoke` — soft-deactivate a token

### Connections — ✅ Implemented
- `POST /api/connections/create` — initiate OAuth via Nango connect session
- `POST /api/connections/callback` — confirm connection after OAuth completes
- `POST /api/connections/list` — list connections for org (or specific client)
- `POST /api/connections/get` — get connection details and status
- `POST /api/connections/refresh` — force token refresh via Nango
- `POST /api/connections/revoke` — disconnect a client's Salesforce

### Topology — ✅ Implemented
- `POST /api/topology/pull` — pull and store client's full CRM schema
- `POST /api/topology/get` — retrieve latest (or specific version) stored snapshot
- `POST /api/topology/history` — list snapshot versions (no JSONB payload)

### Conflicts — 🔲 Not Yet Implemented (Phase 5)
- `POST /api/conflicts/check` — run pre-deploy conflict analysis
- `POST /api/conflicts/get` — retrieve a specific conflict report

### Deploy — 🔲 Not Yet Implemented (Phase 5)
- `POST /api/deploy/custom-objects` — create/update custom objects and fields
- `POST /api/deploy/workflows` — create/update Flows, assignment rules
- `POST /api/deploy/status` — check deployment status
- `POST /api/deploy/rollback` — remove deployed objects/fields/workflows

### Push — 🔲 Not Yet Implemented (Phase 6)
- `POST /api/push/records` — upsert records into client's Salesforce
- `POST /api/push/status-update` — update field values on existing records
- `POST /api/push/link` — create relationships between records

### Workflows — 🔲 Not Yet Implemented (Phase 7)
- `POST /api/workflows/list` — list active automations
- `POST /api/workflows/deploy` — create/update automation rules
- `POST /api/workflows/remove` — delete deployed automations

### Internal
- `GET /health` — health check (no auth)

---

## Database Schema

### Tables

| Table | Purpose |
|---|---|
| `organizations` | Tenant orgs (RA, future firms) |
| `clients` | Org's customers whose Salesforce is managed |
| `users` | Org users with roles and bcrypt password hashes |
| `api_tokens` | SHA-256 hashed machine-to-machine auth tokens |
| `crm_connections` | Connection metadata — status, instance_url, sfdc_org_id, `nango_connection_id` per client (no tokens stored) |
| `crm_topology_snapshots` | Versioned JSONB schema snapshots per client |
| `crm_conflict_reports` | Pre-deploy check results (green/yellow/red) |
| `crm_deployments` | What was deployed, when, result, rollback status — includes optional `conflict_report_id` FK |
| `crm_push_logs` | Record push history with success/fail counts |
| `crm_field_mappings` | Canonical-to-SFDC field mapping per client per object |

All tenant-scoped tables have `org_id` with NOT NULL constraint, foreign key, index, and tenant integrity triggers.

### Enums

| Enum | Values |
|---|---|
| `user_role` | org_admin, company_admin, company_member |
| `connection_status` | pending, connected, expired, revoked, error |
| `deployment_status` | pending, deployed, failed, rolled_back |
| `conflict_severity` | green, yellow, red |
| `push_status` | queued, in_progress, succeeded, partial, failed |

### Migrations

| File | What |
|---|---|
| `001_initial_schema.sql` | Core tables, enums, indexes, tenant integrity triggers |
| `002_field_mappings_and_fixes.sql` | `crm_field_mappings` table and schema fixes |
| `003_conflict_report_tenant_check.sql` | Tenant integrity trigger for `crm_conflict_reports` |
| `004_nango_connection_id.sql` | Added `nango_connection_id` column to `crm_connections` |

---

## Salesforce APIs Used

| API | Purpose |
|---|---|
| REST API (`/services/data/vXX.0/`) | Object describe, record CRUD, composite upserts |
| Tooling API (`/services/data/vXX.0/tooling/`) | Validation rules, Flows, metadata queries |
| Metadata API | Custom object/field creation, layout deployment |
| Composite API | Batch record upserts (up to 200 per call) |

OAuth endpoints are no longer called directly — Nango handles all token exchange and refresh.

---

## Error Handling

| Code | Meaning |
|---|---|
| 401 | Missing or invalid auth token |
| 403 | Valid token, insufficient permissions |
| 404 | Not found OR belongs to different org (prevents enumeration) |
| 400 | Invalid request payload |
| 422 | Invalid request format (Pydantic validation, e.g., bad UUID) |
| 502 | Salesforce or Nango API error — includes original error details in response |

---

## Environment Variables

All secrets managed via Doppler. On Railway, set `DOPPLER_TOKEN` only — Doppler injects the rest at runtime via the Dockerfile CMD.

| Variable | Purpose |
|---|---|
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
│       └── 004_nango_connection_id.sql
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

## Deploy Flow

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

Railway builds from the `Dockerfile`. The Dockerfile CMD uses Doppler to inject all secrets at runtime — only `DOPPLER_TOKEN` is set as a Railway environment variable.

---

## Key Principles

1. **sfdc-engine-x never decides business logic.** It executes what the org tells it to.
2. **One Salesforce connected app, unlimited client connections.** Per-client OAuth managed by Nango.
3. **Tokens are managed by Nango.** Access tokens are refreshed transparently. They never touch our database, logs, or API responses.
4. **Everything is logged.** Deployments, pushes, topology pulls — all recorded with timestamps, org_id, client_id.
5. **Clean up is a first-class operation.** Deployments can be rolled back.
6. **Service layer boundary.** All Salesforce API calls go through `app/services/salesforce.py`. All Nango calls go through `app/services/token_manager.py`. No router calls external APIs directly.

---

## Build Progress

| Phase | Status | What |
|---|---|---|
| 1 | ✅ Complete | Foundation — config, db pool, auth context/dependency, app shell |
| 2 | ✅ Complete | Auth + Clients + Users + API Tokens |
| 3 | ✅ Complete | OAuth Connections via Nango |
| 4 | ✅ Complete | Topology Pull + Snapshots |
| 5 | 🔲 Next | Conflicts + Deploy |
| 6 | 🔲 Pending | Push + Field Mappings |
| 7 | 🔲 Pending | Workflows |

### What's Not Built Yet

- **Conflict checking** — pre-deploy analysis comparing deployment plan against current topology (Phase 5)
- **Deploy operations** — creating custom objects, fields, layouts, workflows in client Salesforce (Phase 5)
- **Rollback logic** — removing deployed objects/fields/workflows on churn (Phase 5)
- **Push operations** — upserting records, updating statuses, linking relationships (Phase 6)
- **Field mapping CRUD endpoints** — table exists, no API yet (Phase 6)
- **Workflow management** — deploying/listing/removing Flows and assignment rules (Phase 7)
- **Topology diff** — comparing two snapshots (future enhancement)
- **RLS policies** — RLS enabled on all tables, no policies defined yet (using app-level tenant filtering with `org_id`)