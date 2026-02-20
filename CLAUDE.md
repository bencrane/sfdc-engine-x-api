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
| **Connect** | OAuth flow — client authorizes, we store access + refresh tokens |
| **Read** | Pull full CRM topology — objects, fields, relationships, workflows, validation rules |
| **Deploy** | Create/update custom objects, fields, layouts, workflows, assignment rules in client's Salesforce |
| **Push** | Upsert records, update statuses, link relationships |
| **Remove** | Clean up deployed objects/fields/workflows on client churn |

All operations are scoped by org_id and client_id. An org never sees another org's data. A client's connection is never accessible by another client.

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| API Framework | FastAPI | Async, Pydantic models, dependency injection for AuthContext |
| Deployment | Railway | Direct deploy, SSL, custom domain |
| Database | Supabase (Postgres) | Managed Postgres, row-level isolation |
| Auth | API tokens + JWT | Machine-to-machine (tokens) and user sessions (JWT) |
| External API | Salesforce REST + Tooling + Metadata APIs | All CRM operations |

**No Modal.** This service handles straightforward request/response operations (OAuth, API calls to Salesforce, DB reads/writes). No serverless compute needed.

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

Child tables include `org_id` even when they reference a parent that already has it. This avoids joins for tenant filtering and provides defense in depth.

---

## Auth Model

### Two Auth Methods

**API Tokens** (machine-to-machine):
- Hashed and stored in `api_tokens` table
- Looked up on each request → returns org_id, user_id
- Used by: data-engine-x, trigger.dev tasks, external integrations

**JWT Sessions** (user login):
- Issued on login, contains org_id, user_id, role
- Validated without DB call (signature check only)
- Used by: admin frontend, user-facing interfaces

### AuthContext

Both methods produce the same AuthContext object, injected into every endpoint via FastAPI dependency:

```python
@dataclass
class AuthContext:
    org_id: str
    user_id: str
    role: str              # org_admin, company_admin, company_member
    permissions: list[str] # derived from role
    client_id: str | None  # set for company-scoped users
    auth_method: str       # "api_token" or "session"
```

### RBAC

| Role | Scope |
|------|-------|
| `org_admin` | Full access — manage connections, deploy, push, manage users/clients |
| `company_admin` | Client-scoped — view connection status, view topology |
| `company_member` | Client-scoped — read-only |

### Permissions

```
connections.read, connections.write
topology.read
deploy.write
push.write
workflows.read, workflows.write
org.manage
```

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `organizations` | Tenant orgs |
| `clients` | Org's customers (the staffing agencies, etc.) |
| `users` | People at the org |
| `api_tokens` | Machine-to-machine auth tokens |
| `crm_connections` | OAuth tokens, instance_url, token expiry, refresh token, status per client |
| `crm_topology_snapshots` | Full CRM schema snapshots (JSONB), versioned |
| `crm_deployments` | Log of what was deployed — objects, fields, workflows, when, to which client |
| `crm_conflict_reports` | Pre-deploy conflict check results |

All tenant-scoped tables have `org_id` with NOT NULL constraint, foreign key, and index.

---

## API Conventions

- **All endpoints use POST** (except health check) — parameters in request body as JSON
- **AuthContext injected on every endpoint** via dependency
- **Every query scoped by org_id** at minimum
- **Thin endpoints** — validate, call Salesforce or DB, return
- **Salesforce errors surfaced as 502** with provider error details in response body

### Error Codes

| Code | Meaning |
|------|---------|
| 401 | Missing or invalid auth token |
| 403 | Valid token but insufficient permissions |
| 404 | Resource not found or belongs to different org |
| 400 | Invalid request payload |
| 502 | Salesforce API error |

---

## API Endpoints

### Connections
- `POST /api/connections/create` — exchange OAuth code for tokens, store connection
- `POST /api/connections/list` — list connections for org (or specific client)
- `POST /api/connections/get` — get connection details and status
- `POST /api/connections/refresh` — force token refresh
- `POST /api/connections/revoke` — disconnect a client's Salesforce

### Topology
- `POST /api/topology/pull` — pull and store client's full CRM schema
- `POST /api/topology/get` — retrieve latest stored snapshot
- `POST /api/topology/history` — list snapshot versions

### Conflicts
- `POST /api/conflicts/check` — run pre-deploy conflict analysis against a deployment plan
- `POST /api/conflicts/get` — retrieve a specific conflict report

### Deploy
- `POST /api/deploy/custom-objects` — create/update custom objects and fields
- `POST /api/deploy/workflows` — create/update Flows, assignment rules, automations
- `POST /api/deploy/status` — check deployment status
- `POST /api/deploy/rollback` — remove deployed objects/fields/workflows

### Push
- `POST /api/push/records` — upsert records into client's Salesforce
- `POST /api/push/status-update` — update field values on existing records
- `POST /api/push/link` — create relationships between records

### Workflows
- `POST /api/workflows/list` — list active automations in client's Salesforce
- `POST /api/workflows/deploy` — create/update automation rules
- `POST /api/workflows/remove` — delete deployed automations

### Auth
- `POST /api/auth/login` — issue JWT session token
- `GET /api/auth/me` — return current auth context with role and permissions

### Internal
- `GET /health` — health check (no auth)

---

## Directory Structure

```
sfdc-engine-x/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, mount routers
│   ├── config.py             # Settings from env vars
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── context.py        # AuthContext dataclass
│   │   └── dependencies.py   # get_current_auth dependency
│   ├── models/
│   │   ├── __init__.py
│   │   ├── connections.py    # Pydantic models for connection endpoints
│   │   ├── topology.py       # Pydantic models for topology endpoints
│   │   └── deployments.py    # Pydantic models for deploy/push endpoints
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── connections.py
│   │   ├── topology.py
│   │   ├── conflicts.py
│   │   ├── deploy.py
│   │   ├── push.py
│   │   └── workflows.py
│   └── services/
│       ├── __init__.py
│       ├── salesforce.py     # All Salesforce API interactions
│       └── token_manager.py  # Token refresh, expiry handling
├── supabase/
│   └── migrations/
│       └── 001_initial_schema.sql
├── docs/
│   ├── ARCHITECTURE.md
│   └── API.md
├── tests/
│   └── __init__.py
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── CLAUDE.md
```

---

## Environment Variables

```
DATABASE_URL=<supabase-postgres-connection-string>
SFDC_CLIENT_ID=<salesforce-connected-app-client-id>
SFDC_CLIENT_SECRET=<salesforce-connected-app-client-secret>
JWT_SECRET=<random-secret-for-signing-jwts>
SFDC_REDIRECT_URI=<oauth-callback-url>
```

---

## Key Principles

1. **sfdc-engine-x never decides business logic.** It executes what the org tells it to. "Deploy this object," "push these records," "create this workflow." The org decides what and why.
2. **One Salesforce connected app, unlimited client connections.** The app credentials are env vars. Per-client OAuth tokens are stored in the database, scoped by org_id + client_id.
3. **Tokens are managed automatically.** Access tokens are refreshed transparently before expiry. The caller never deals with Salesforce auth.
4. **Everything is logged.** Deployments, pushes, topology pulls — all recorded with timestamps, org_id, client_id, and what was done.
5. **Clean up is a first-class operation.** If a client churns, the org can roll back everything deployed to that client's Salesforce through the API.

---

## Common Commands

```bash
# Run locally
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Deploy to Railway
railway up
```