# Architecture — sfdc-engine-x

## What This Is

A multi-tenant API service for programmatic Salesforce administration. Organizations use it to manage their clients' Salesforce instances entirely through API — without ever logging into a client's Salesforce org.

---

## Stack Decisions

| Layer | Choice | Why |
|-------|--------|-----|
| API Framework | FastAPI | Async, Pydantic models, dependency injection for AuthContext |
| Deployment | Railway | Direct deploy, SSL, custom domain |
| Database | Supabase (Postgres) | Managed Postgres, row-level isolation |
| Auth | API tokens + JWT | Machine-to-machine (tokens) and user sessions (JWT) |
| External API | Salesforce REST + Tooling + Metadata APIs | All CRM operations |

### Why No Modal

This service handles synchronous request/response operations: OAuth exchanges, Salesforce API calls, database reads/writes. No long-running compute, no batch processing, no serverless scaling needed. FastAPI on Railway is the right fit.

### Why Separate From hubspot-engine-x

Salesforce and HubSpot have fundamentally different APIs, object models, rate limits, and deployment mechanisms. Merging them into one service creates a codebase full of conditionals. Two clean services, each an expert in one CRM, is simpler to build, test, and debug. The caller routes to the right engine based on the client's CRM type.

---

## Why This Exists Separately

This engine exists as standalone infrastructure — not embedded in any product — to enforce clean boundaries:

- **Multiple products share it** — Staffing Activation, Revenue Activation, future products
- **Each product is a tenant** — not a fork, not a separate deployment
- **CRM-specific logic is contained** — no other service needs to know how Salesforce works
- **Salesforce API changes don't ripple** — only this service adapts

---

## Multi-Tenancy Model

### Three Tiers

```
Tier 1: Organization    — The business (RA, future RevOps firms)
Tier 2: Client           — Customer of that org (staffing agency, SaaS company, etc.)
Tier 3: User             — Person at the org
```

### Data Isolation

```
┌─────────────────────────────────────────────────────────┐
│                    Single Database                       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   RA        │  │   Org B     │  │   Org C     │     │
│  │  org_id=1   │  │  org_id=2   │  │  org_id=3   │     │
│  │             │  │             │  │             │     │
│  │ - clients   │  │ - clients   │  │ - clients   │     │
│  │ - connections│ │ - connections│ │ - connections│     │
│  │ - deploys   │  │ - deploys   │  │ - deploys   │     │
│  │ - pushes    │  │ - pushes    │  │ - pushes    │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Query Scoping

Every database query chains down the tenant hierarchy:

```python
# Org-level: "show me all clients in my org"
.eq("org_id", auth.org_id)

# Client-level: "show me connection for this client"
.eq("org_id", auth.org_id).eq("client_id", client_id)
```

Client-level resources validate the client belongs to the org before any operation.

### Denormalization

Child tables include `org_id` even when they reference a parent that already has it:

| Table | Parent | Has own org_id? | Why? |
|-------|--------|-----------------|------|
| clients | organizations | Yes | Primary tenant key |
| crm_connections | clients | Yes | Query efficiency, direct filtering |
| crm_topology_snapshots | crm_connections | Yes | Can query snapshots directly by org |
| crm_deployments | crm_connections | Yes | Can query deployments directly by org |
| crm_conflict_reports | crm_connections | Yes | Can query reports directly by org |
| crm_push_logs | crm_connections | Yes | Can query push logs directly by org |

Tenant integrity triggers enforce that `client_id` always belongs to `org_id` on insert/update.

---

## Auth Model

### Two Auth Methods

**API Tokens** (machine-to-machine):
- Hashed and stored in `api_tokens` table
- Looked up on each request → returns org_id, user_id
- Used by: data-engine-x, Trigger.dev tasks, external integrations

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

| Role | Scope | Can do |
|------|-------|--------|
| `org_admin` | Org-wide | Everything — connect, read, deploy, push, manage |
| `company_admin` | Client-scoped | View connection status, view topology |
| `company_member` | Client-scoped | Read-only |

### Permissions

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

## Salesforce Integration

### OAuth Flow

```
1. Org admin clicks "Connect Client's Salesforce"
2. Browser redirects to Salesforce OAuth URL:
   https://login.salesforce.com/services/oauth2/authorize
   ?response_type=code
   &client_id={SFDC_CLIENT_ID}
   &redirect_uri={SFDC_REDIRECT_URI}
   &scope=full+refresh_token

3. Client's Salesforce admin clicks "Allow"
4. Salesforce redirects to callback URL with auth code
5. sfdc-engine-x exchanges code for tokens:
   POST https://login.salesforce.com/services/oauth2/token
   → access_token, refresh_token, instance_url

6. Tokens stored in crm_connections
7. Immediate topology pull triggered
```

### Token Lifecycle

- Access tokens expire (~1-2 hours)
- Refresh tokens persist until explicitly revoked
- Token manager checks expiry before every Salesforce API call
- If expired, refreshes automatically using refresh token
- New access token stored, call proceeds
- If refresh fails (token revoked), connection status set to `expired`

### Salesforce APIs Used

| API | Purpose |
|-----|---------|
| REST API (`/services/data/vXX.0/`) | CRUD operations, record push, object describe |
| Tooling API (`/services/data/vXX.0/tooling/`) | Validation rules, Flows, Apex triggers, metadata queries |
| Metadata API | Deploy/retrieve complex metadata (custom objects, layouts, workflows) |
| Composite API (`/composite/sobjects`) | Batch record upserts (up to 200 records per call) |

### Topology Pull — What We Read

1. **All objects:** `GET /sobjects/` — list every standard + custom object
2. **Per-object describe:** `GET /sobjects/{Object}/describe/` — fields, relationships, picklist values, field types, required fields
3. **Validation rules:** Tooling API query on `ValidationRule`
4. **Active Flows:** Tooling API query on `Flow` where Status='Active'
5. **Workflow rules:** Tooling API query on `WorkflowRule`
6. **Record types:** Tooling API query on `RecordType`

Stored as a single JSONB snapshot, versioned per client.

### Conflict Detection — What We Check

| Check | Severity | Description |
|-------|----------|-------------|
| Object name collision | Red | Custom object with same API name already exists |
| Field name collision | Yellow | Field with same name on target object exists |
| Required fields on standard objects | Red | Required fields you won't be populating |
| Active validation rules | Yellow | Rules that could reject your records |
| Active Flows/automations | Yellow | Workflows that fire on create/update of target objects |
| Record type requirements | Yellow | Object requires a record type you haven't specified |

---

## Error Handling

| Code | Meaning |
|------|---------|
| 401 | Missing or invalid auth token |
| 403 | Valid token but insufficient permissions |
| 404 | Resource not found or belongs to different org (same response to prevent enumeration) |
| 400 | Invalid request payload |
| 502 | Salesforce API error — response includes SFDC error code and message |

Salesforce-specific errors (rate limits, invalid field, etc.) are wrapped in 502 with structured error details so the caller can handle them appropriately.

---

## Key Principles

1. **sfdc-engine-x never decides business logic.** It executes what the org tells it to.
2. **One Salesforce connected app, unlimited client connections.** App credentials are env vars. Per-client tokens are in the database.
3. **Tokens are managed automatically.** Callers never deal with Salesforce auth.
4. **Everything is logged.** Every deployment, push, topology pull — recorded with timestamps, org_id, client_id.
5. **Clean up is first-class.** Deployments can be rolled back. Objects, fields, workflows — all removable.
6. **No Salesforce knowledge leaks.** Callers interact with sfdc-engine-x endpoints. They never need to know Salesforce API specifics.