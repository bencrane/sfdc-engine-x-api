# System Overview: sfdc-engine-x

Comprehensive documentation of the system. Written for AI agents or human engineers who need full context to continue development.

---

## What This System Is

`sfdc-engine-x` is a multi-tenant API service for programmatic Salesforce administration. It allows organizations (RevOps firms, agencies, internal teams) to manage their clients' Salesforce instances entirely through API — without ever logging into a client's Salesforce org.

One Salesforce connected app serves all tenants. Each client authorizes via OAuth. From that point on, the owning organization can read schemas, deploy custom objects, create workflows, push records, and clean up — all through sfdc-engine-x endpoints.

This is standalone infrastructure. It is not embedded in any product. Multiple products consume it:
- **Staffing Activation** — deploys job posting objects, pushes enriched leads daily
- **Revenue Activation** — manages client CRM schemas, pushes enriched pipeline data
- **Future RevOps firms** — onboard as new orgs, same API, full isolation

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI (Python) on Railway | Auth, routing, validation, persistence, Salesforce operations |
| Database | Supabase (Postgres) | Tenant data, connections, topology, deployments, push logs, field mappings |
| External API | Salesforce REST + Tooling + Metadata APIs | All CRM operations via stored OAuth tokens |
| Auth | API tokens + JWT | Machine-to-machine (tokens) and user sessions (JWT) |

### Why No Modal / Trigger.dev

sfdc-engine-x handles request/response workloads: OAuth flows, schema reads, record pushes, deployment operations. No long-running compute, no batch processing, no orchestration. FastAPI on Railway is sufficient.

Scheduling (e.g., daily pushes) is handled by external orchestrators (Trigger.dev, data-engine-x) that call sfdc-engine-x endpoints. This service does not schedule its own work.

---

## Architecture

### Execution Flow

```
External caller (data-engine-x, Trigger.dev, admin frontend)
  → Authenticates with API token or JWT
  → Calls sfdc-engine-x endpoint (e.g., POST /api/push/{client_id})
    → Auth dependency extracts org_id, validates permissions
    → Router validates request, delegates to service layer
    → Service layer looks up client's connection (access token, instance URL)
    → Token manager refreshes access token if expired
    → Service calls Salesforce API using client's credentials
    → Result persisted (push log, deployment record, topology snapshot)
    → Response returned to caller
```

### Key Architectural Patterns

**One Connected App, Many Connections:** A single Salesforce connected app (one client_id + secret) serves all orgs and all clients. Each client's OAuth produces a unique token pair stored in `crm_connections`.

**Token Lifecycle Management:** Access tokens expire (~1-2 hours). `token_manager.py` auto-refreshes using the stored refresh token before any API call. Refresh tokens are long-lived (until revoked by client).

**Topology Snapshots:** Full CRM schema captured as versioned JSONB. Enables conflict detection before deploying, diffing over time, and understanding client's CRM structure without manual inspection.

**Deployment Tracking:** Every custom object, field, and workflow deployed by sfdc-engine-x is logged. Enables rollback on churn and audit trail of what was changed.

**Field Mapping Layer:** Canonical data shapes (e.g., `job_posting` with `job_title`, `company_name`) are mapped to client-specific Salesforce field names (e.g., `Job_Title__c`). The push endpoint reads mappings, not hardcoded field names.

**Service Layer Boundary:** No router directly calls Salesforce. All external API calls go through `app/services/salesforce.py`, which handles token refresh, rate limits, error translation, and instance URL resolution per client.

---

## Multi-Tenancy Model

### Three Tiers

```
Tier 1: Organization   — The business (Revenue Activation, Staffing Activation, future RevOps firm)
Tier 2: Client          — A customer of that org whose Salesforce is being managed
Tier 3: User            — A person at that org who interacts with the API
```

### Query Scoping

Every query filters by `org_id`. Client-level queries add `client_id`:

```python
# Org-level: all clients in my org
.eq("org_id", auth.org_id)

# Client-level: Acme's connection
.eq("org_id", auth.org_id).eq("client_id", client_id)
```

### Denormalization

All child tables carry `org_id` for direct filtering without joins. Tenant integrity triggers enforce that `client_id` always belongs to the `org_id` on the same row.

---

## Capability Map

### Connect
| Capability | Endpoint | Description |
|---|---|---|
| Initiate OAuth | `GET /api/connections/authorize/{client_id}` | Returns Salesforce OAuth URL |
| OAuth callback | `GET /api/connections/callback` | Exchanges code for tokens, stores connection |
| Connection status | `GET /api/connections/{client_id}` | Health, last used, error state |
| Health check | `POST /api/connections/{client_id}/health` | Lightweight API call to verify connection |
| Disconnect | `POST /api/connections/{client_id}/disconnect` | Revoke tokens, mark inactive |

### Read
| Capability | Endpoint | Description |
|---|---|---|
| Pull topology | `POST /api/topology/{client_id}/pull` | Full schema snapshot (objects, fields, relationships, picklists) |
| Latest snapshot | `GET /api/topology/{client_id}/latest` | Most recent topology |
| Snapshot history | `GET /api/topology/{client_id}/snapshots` | All snapshots for a client |
| Diff snapshots | `GET /api/topology/{client_id}/diff` | Compare two versions |

### Check
| Capability | Endpoint | Description |
|---|---|---|
| Conflict check | `POST /api/conflicts/{client_id}/check` | Compare deployment plan against topology — green/yellow/red |

### Deploy
| Capability | Endpoint | Description |
|---|---|---|
| Deploy objects/fields/workflows | `POST /api/deploy/{client_id}` | Create custom objects, fields, layouts, workflows |
| Deployment history | `GET /api/deploy/{client_id}/history` | All deployments for a client |
| Rollback | `POST /api/deploy/{client_id}/{deployment_id}/rollback` | Remove what was deployed |

### Push
| Capability | Endpoint | Description |
|---|---|---|
| Push records | `POST /api/push/{client_id}` | Upsert records using canonical-to-SFDC field mappings |
| Push history | `GET /api/push/{client_id}/history` | All push logs |
| Push detail | `GET /api/push/{client_id}/{push_id}` | Per-record errors |

### Workflows
| Capability | Endpoint | Description |
|---|---|---|
| Deploy workflows | `POST /api/workflows/{client_id}/deploy` | Create Flows, assignment rules in client's Salesforce |
| List workflows | `GET /api/workflows/{client_id}` | What sfdc-engine-x deployed |
| Remove workflow | `DELETE /api/workflows/{client_id}/{workflow_id}` | Clean up |

### Field Mappings
| Capability | Endpoint | Description |
|---|---|---|
| Set mappings | `POST /api/field-mappings/{client_id}` | Map canonical fields to SFDC fields |
| List mappings | `GET /api/field-mappings/{client_id}` | All mappings for a client |
| Get mapping | `GET /api/field-mappings/{client_id}/{canonical_object}` | Specific object mapping |

---

## Database Schema (Migration 001)

| Table | Purpose |
|---|---|
| `organizations` | Tenant orgs (RA, SA, future firms) |
| `users` | Org users with roles |
| `api_tokens` | Hashed API tokens for machine-to-machine auth |
| `clients` | Org's customers whose Salesforce is managed |
| `crm_connections` | OAuth tokens, instance URL, connection status per client |
| `crm_topology_snapshots` | Versioned JSONB schema snapshots |
| `crm_conflict_reports` | Pre-deploy check results (green/yellow/red) |
| `crm_deployments` | What was deployed, when, result, rollback status |
| `crm_push_logs` | Record push history with success/fail counts |
| `crm_field_mappings` | Canonical-to-SFDC field mapping per client per object |

### Enums

| Enum | Values |
|---|---|
| `user_role` | org_admin, company_admin, company_member |
| `connection_status` | pending, connected, expired, revoked, error |
| `deployment_status` | pending, deployed, failed, rolled_back |
| `conflict_severity` | green, yellow, red |
| `push_status` | queued, in_progress, succeeded, partial, failed |

---

## Salesforce APIs Used

| API | Purpose |
|---|---|
| REST API (`/services/data/vXX.0/`) | Object describe, record CRUD, composite upserts |
| Tooling API (`/services/data/vXX.0/tooling/`) | Validation rules, Flows, metadata queries |
| Metadata API | Custom object/field creation, layout deployment |
| Composite API | Batch record upserts (up to 200 per call) |
| OAuth endpoints | Token exchange, refresh |

---

## Auth Model

| Method | Mechanism | Use Case |
|---|---|---|
| API Token | Hashed in `api_tokens`, DB lookup per request | Trigger.dev, data-engine-x, automation |
| JWT | Signed with `JWT_SECRET`, no DB call | Admin frontend, user sessions |

Both produce `AuthContext(org_id, user_id, role, client_id, auth_method)` injected into every endpoint.

### RBAC

| Role | Scope | Permissions |
|---|---|---|
| `org_admin` | Org-wide | All operations |
| `company_admin` | Client-scoped | connections.read, topology.read, push.write |
| `company_member` | Client-scoped | connections.read, topology.read |

---

## Error Handling

| Code | Meaning |
|---|---|
| 401 | Missing or invalid auth token |
| 403 | Valid token, insufficient permissions |
| 404 | Not found OR belongs to different org (prevents enumeration) |
| 400 | Invalid request payload |
| 502 | Salesforce API error — includes original SFDC error code in response |

---

## Environment Variables

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Supabase Postgres connection string |
| `SFDC_CLIENT_ID` | Salesforce connected app client ID |
| `SFDC_CLIENT_SECRET` | Salesforce connected app client secret |
| `SFDC_REDIRECT_URI` | OAuth callback URL |
| `JWT_SECRET` | JWT signing secret |
| `SUPER_ADMIN_JWT_SECRET` | Separate secret for super-admin auth |

---

## Directory Structure

```
sfdc-engine-x/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── auth/
│   │   ├── context.py
│   │   └── dependencies.py
│   ├── models/
│   │   ├── connections.py
│   │   ├── topology.py
│   │   └── deployments.py
│   ├── routers/
│   │   ├── connections.py
│   │   ├── topology.py
│   │   ├── conflicts.py
│   │   ├── deploy.py
│   │   ├── push.py
│   │   └── workflows.py
│   └── services/
│       ├── salesforce.py
│       └── token_manager.py
├── supabase/
│   └── migrations/
│       └── 001_initial_schema.sql
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── SYSTEM_OVERVIEW.md
│   ├── WRITING_EXECUTOR_DIRECTIVES.md
│   └── STRATEGIC_DIRECTIVE.md
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── CLAUDE.md
```

---

## Deploy Flow

```bash
# Railway auto-deploy on push
git push origin main

# Run migrations manually
psql "$DATABASE_URL" -f supabase/migrations/001_initial_schema.sql
```

---

## What's Not Built Yet

- **Router implementations** — endpoint shells exist, service logic not implemented
- **Service layer** — `salesforce.py` and `token_manager.py` need full implementation
- **Auth implementation** — `context.py` and `dependencies.py` need implementation
- **Pydantic models** — request/response schemas in `models/`
- **Tests** — no tests written yet
- **Super-admin endpoints** — org creation, stats
- **RLS policies** — RLS enabled on all tables, no policies defined
- **Workflow deployment** — Tooling/Metadata API integration for Flows and assignment rules
- **Topology diff** — comparing two snapshots
- **Rollback logic** — removing deployed objects/fields/workflows