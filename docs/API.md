# API Reference — sfdc-engine-x

All endpoints use POST unless noted. All require authentication via Bearer token (API token or JWT) unless noted.

**Auth methods:**

| Method | Header | Usage |
|--------|--------|-------|
| Super-Admin | `Authorization: Bearer <SUPER_ADMIN_JWT_SECRET>` | Bootstrap only — org and first user creation |
| API Token | `Authorization: Bearer <raw_token>` | Machine-to-machine — SHA-256 hashed and looked up per request |
| JWT Session | `Authorization: Bearer <jwt>` | User login sessions — HS256 signed, contains org_id/user_id/role |

**Common error codes:**

| Code | Meaning |
|------|---------|
| 401 | Missing or invalid auth token |
| 403 | Valid token but insufficient permissions |
| 404 | Resource not found or belongs to different org |
| 400 | Invalid request payload |
| 422 | Invalid request format (Pydantic validation, e.g., bad UUID) |
| 502 | Salesforce or Nango API error |

---

## Super-Admin

Bootstrap endpoints for creating organizations and initial users. Authenticated via the `SUPER_ADMIN_JWT_SECRET` shared secret (constant-time comparison).

### POST /api/super-admin/orgs

Create a new organization (tenant).

**Auth:** Super-Admin bearer token
**Permission:** N/A (super-admin only)

**Request:**
```json
{
  "name": "Revenue Activation",
  "slug": "revenue-activation"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Display name of the organization |
| `slug` | string | yes | URL-safe unique identifier |

**Response (200):**
```json
{
  "id": "uuid",
  "name": "Revenue Activation",
  "slug": "revenue-activation",
  "is_active": true,
  "created_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `Organization slug already exists` |
| 401 | `Invalid super-admin token` |

---

### POST /api/super-admin/users

Create a user in any organization (used for bootstrapping the first org_admin).

**Auth:** Super-Admin bearer token
**Permission:** N/A (super-admin only)

**Request:**
```json
{
  "org_id": "uuid",
  "email": "admin@revenueactivation.com",
  "name": "Jane Admin",
  "password": "...",
  "role": "org_admin"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `org_id` | UUID | yes | Organization to create the user in |
| `email` | string | yes | User email (unique per org) |
| `name` | string | no | Display name |
| `password` | string | yes | Plain-text password (hashed with bcrypt before storage) |
| `role` | string | yes | One of: `org_admin`, `company_admin`, `company_member` |

**Response (200):**
```json
{
  "id": "uuid",
  "org_id": "uuid",
  "email": "admin@revenueactivation.com",
  "name": "Jane Admin",
  "role": "org_admin",
  "created_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `User email already exists in organization` |
| 400 | `Invalid input data` |
| 401 | `Invalid super-admin token` |
| 404 | `Organization not found` |

---

## Auth

### POST /api/auth/login

Issue a JWT session token. No authentication required.

**Auth:** None
**Permission:** None

**Request:**
```json
{
  "email": "admin@revenueactivation.com",
  "password": "..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | yes | User email |
| `password` | string | yes | Plain-text password |

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | HS256 JWT containing `org_id`, `user_id`, `role`, `client_id`, `exp` |
| `token_type` | string | Always `"bearer"` |
| `expires_in` | integer | Token lifetime in seconds (default 86400 = 24h) |

**Errors:**

| Code | Detail |
|------|--------|
| 401 | `Invalid credentials` |

---

### GET /api/auth/me

Return the current auth context for the authenticated caller.

**Auth:** API Token or JWT Session
**Permission:** None (any authenticated user)

**Response (200):**
```json
{
  "org_id": "uuid",
  "user_id": "uuid",
  "role": "org_admin",
  "permissions": [
    "connections.read",
    "connections.write",
    "topology.read",
    "deploy.write",
    "push.write",
    "workflows.read",
    "workflows.write",
    "org.manage"
  ],
  "client_id": null,
  "auth_method": "session"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `org_id` | string | Organization UUID |
| `user_id` | string | User UUID |
| `role` | string | `org_admin`, `company_admin`, or `company_member` |
| `permissions` | string[] | Derived from role via ROLE_PERMISSIONS |
| `client_id` | string \| null | Set for company-scoped users |
| `auth_method` | string | `"api_token"` or `"session"` |

---

## Clients

### POST /api/clients/create

Create a new client for the authenticated org.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "name": "Acme Corp",
  "domain": "acme.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Client display name |
| `domain` | string | no | Client domain |

**Response (200):**
```json
{
  "id": "uuid",
  "name": "Acme Corp",
  "domain": "acme.com",
  "is_active": true,
  "created_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |

---

### POST /api/clients/list

List all active clients for the authenticated org.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{}
```

**Response (200):**
```json
{
  "data": [
    {
      "id": "uuid",
      "name": "Acme Corp",
      "domain": "acme.com",
      "is_active": true,
      "created_at": "2026-02-19T00:00:00+00:00"
    }
  ]
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |

---

### POST /api/clients/get

Get details for a specific client.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Client UUID |

**Response (200):**
```json
{
  "id": "uuid",
  "name": "Acme Corp",
  "domain": "acme.com",
  "is_active": true,
  "created_at": "2026-02-19T00:00:00+00:00",
  "updated_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |

---

## Users

### POST /api/users/create

Create a new user in the authenticated org.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "email": "user@acme.com",
  "name": "John Doe",
  "password": "...",
  "role": "company_admin",
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | yes | User email (unique per org) |
| `name` | string | no | Display name |
| `password` | string | yes | Plain-text password (hashed with bcrypt) |
| `role` | string | yes | One of: `org_admin`, `company_admin`, `company_member` |
| `client_id` | UUID | no | Required for `company_admin` and `company_member`; must be null for `org_admin` |

**Scope rules:**
- `org_admin` — `client_id` must be null (org-wide access)
- `company_admin` — `client_id` is required
- `company_member` — `client_id` is required

**Response (200):**
```json
{
  "id": "uuid",
  "org_id": "uuid",
  "email": "user@acme.com",
  "name": "John Doe",
  "role": "company_admin",
  "client_id": "uuid",
  "created_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `org_admin users cannot have client_id` |
| 400 | `company_admin users must include client_id` |
| 400 | `company_member users must include client_id` |
| 400 | `Invalid role` |
| 400 | `User email already exists in organization` |
| 403 | `Insufficient permissions` |
| 404 | `Client not found` (client_id doesn't belong to org) |

---

### POST /api/users/list

List all active users in the authenticated org.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{}
```

**Response (200):**
```json
{
  "data": [
    {
      "id": "uuid",
      "email": "admin@revenueactivation.com",
      "name": "Jane Admin",
      "role": "org_admin",
      "client_id": null,
      "is_active": true,
      "created_at": "2026-02-19T00:00:00+00:00"
    }
  ]
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |

---

## Tokens

### POST /api/tokens/create

Create a new API token. The raw token value is returned **once** in this response and never again.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "label": "data-engine-x production",
  "expires_in_days": 90
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | string | no | Human-readable label for the token |
| `expires_in_days` | integer | no | Days until expiry (minimum 1). Null = never expires |

**Response (200):**
```json
{
  "id": "uuid",
  "token": "raw-token-value-returned-once",
  "label": "data-engine-x production",
  "expires_at": "2026-05-20T00:00:00+00:00",
  "created_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 422 | Validation error (e.g., `expires_in_days` < 1) |

---

### POST /api/tokens/list

List all active API tokens for the authenticated org. Token values are never exposed.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{}
```

**Response (200):**
```json
{
  "data": [
    {
      "id": "uuid",
      "label": "data-engine-x production",
      "last_used_at": "2026-02-19T00:00:00+00:00",
      "expires_at": "2026-05-20T00:00:00+00:00",
      "is_active": true,
      "created_at": "2026-02-19T00:00:00+00:00"
    }
  ]
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |

---

### POST /api/tokens/revoke

Soft-deactivate an API token (sets `is_active = false`).

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Token UUID to revoke |

**Response (200):**
```json
{
  "id": "uuid",
  "is_active": false
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `API token not found` |

---

## Connections

### POST /api/connections/create

Initiate an OAuth connection for a client via Nango. Returns a Nango connect session token for the frontend to use with Nango's Connect UI.

**Auth:** API Token or JWT Session
**Permission:** `connections.write`

**Request:**
```json
{
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client to connect |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "status": "pending",
  "connect_session": {
    "token": "nango-session-token",
    "expires_at": "2026-02-19T01:00:00+00:00"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | CRM connection UUID |
| `client_id` | string | Client UUID |
| `status` | string | Always `"pending"` on create |
| `connect_session.token` | string | Token for Nango Connect UI |
| `connect_session.expires_at` | string \| null | Session expiry |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 502 | `Nango connect session missing token` |

---

### POST /api/connections/callback

Confirm a connection after OAuth completes. Fetches credentials from Nango and updates connection metadata (instance_url, sfdc_org_id, sfdc_user_id).

**Auth:** API Token or JWT Session
**Permission:** `connections.write`

**Request:**
```json
{
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client whose OAuth flow completed |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "status": "connected",
  "instance_url": "https://acme.my.salesforce.com"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 404 | `Connection not found` |
| 502 | Nango API error |

---

### POST /api/connections/list

List connections for the org, optionally filtered to a specific client.

**Auth:** API Token or JWT Session
**Permission:** `connections.read`

**Request:**
```json
{
  "client_id": "uuid (optional — omit for all connections in org)"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | no | Filter to a specific client. Omit or null for all connections |

**Response (200):**
```json
{
  "data": [
    {
      "id": "uuid",
      "client_id": "uuid",
      "status": "connected",
      "instance_url": "https://acme.my.salesforce.com",
      "last_used_at": "2026-02-19T00:00:00+00:00",
      "created_at": "2026-02-19T00:00:00+00:00"
    }
  ]
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` (when client_id provided but not in org) |

---

### POST /api/connections/get

Get full details for a specific connection.

**Auth:** API Token or JWT Session
**Permission:** `connections.read`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Connection UUID |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "status": "connected",
  "instance_url": "https://acme.my.salesforce.com",
  "sfdc_org_id": "00D...",
  "sfdc_user_id": "005...",
  "last_used_at": "2026-02-19T00:00:00+00:00",
  "created_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Connection not found` |

---

### POST /api/connections/refresh

Force a token refresh via Nango. If Nango reports the token is expired/invalid, the connection status is updated to `expired`.

**Auth:** API Token or JWT Session
**Permission:** `connections.write`

**Request:**
```json
{
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client whose token to refresh |

**Response (200):**
```json
{
  "status": "connected",
  "last_refreshed_at": "2026-02-19T00:00:00+00:00"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 404 | `Connection not found` |
| 424 | Nango refresh failed (connection marked as `expired`) |

---

### POST /api/connections/revoke

Disconnect a client's Salesforce. Deletes the connection in Nango and marks the local record as revoked.

**Auth:** API Token or JWT Session
**Permission:** `connections.write`

**Request:**
```json
{
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client to disconnect |

**Response (200):**
```json
{
  "status": "revoked"
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 404 | `Connection not found` |

---

## Topology

### POST /api/topology/pull

Pull the client's full CRM schema from Salesforce and store as a versioned snapshot.

**Auth:** API Token or JWT Session
**Permissions:** `topology.read` + `connections.write`

**Request:**
```json
{
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client whose Salesforce to pull |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "version": 3,
  "objects_count": 847,
  "custom_objects_count": 12,
  "pulled_at": "2026-02-19T00:00:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Snapshot UUID |
| `client_id` | string | Client UUID |
| `version` | integer | Auto-incrementing version per client |
| `objects_count` | integer | Total number of Salesforce objects |
| `custom_objects_count` | integer | Number of custom objects |
| `pulled_at` | string | ISO timestamp |

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `No connected Salesforce connection found` |
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 502 | Salesforce API error |

---

### POST /api/topology/get

Retrieve a stored topology snapshot (latest or specific version).

**Auth:** API Token or JWT Session
**Permission:** `topology.read`

**Request:**
```json
{
  "client_id": "uuid",
  "version": 3
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client UUID |
| `version` | integer | no | Specific version number. Omit for latest |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "version": 3,
  "objects_count": 847,
  "custom_objects_count": 12,
  "snapshot": { "...full JSONB topology..." },
  "pulled_at": "2026-02-19T00:00:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `snapshot` | object | Full CRM topology — objects, fields, relationships, picklists |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 404 | `Topology snapshot not found` |

---

### POST /api/topology/history

List all snapshot versions for a client (without the JSONB snapshot payload).

**Auth:** API Token or JWT Session
**Permission:** `topology.read`

**Request:**
```json
{
  "client_id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client UUID |

**Response (200):**
```json
{
  "data": [
    {
      "id": "uuid",
      "version": 3,
      "objects_count": 847,
      "custom_objects_count": 12,
      "pulled_at": "2026-02-19T00:00:00+00:00"
    },
    {
      "id": "uuid",
      "version": 2,
      "objects_count": 840,
      "custom_objects_count": 11,
      "pulled_at": "2026-02-01T00:00:00+00:00"
    }
  ]
}
```

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |

---

## Health

### GET /health

Health check endpoint. No authentication required.

**Auth:** None
**Permission:** None

**Response (200):**
```json
{
  "status": "ok",
  "timestamp": "2026-02-19T00:00:00+00:00"
}
```

---

## Not Yet Implemented

The following endpoints are planned but not yet built. Specs are provisional and may change during implementation.

---

### Conflicts (Phase 5)

#### POST /api/conflicts/check

> **Status: Not Yet Implemented**

Run pre-deploy conflict analysis.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write` (expected)

**Request:**
```json
{
  "client_id": "uuid",
  "deployment_plan": {
    "custom_objects": [
      {
        "api_name": "Job_Posting__c",
        "label": "Job Posting",
        "fields": [
          { "api_name": "Job_Title__c", "label": "Job Title", "type": "Text", "length": 255 },
          { "api_name": "Company_Name__c", "label": "Company Name", "type": "Text", "length": 255 },
          { "api_name": "Posting_URL__c", "label": "Posting URL", "type": "Url" },
          { "api_name": "Status__c", "label": "Status", "type": "Picklist", "values": ["Active", "Closed"] }
        ]
      }
    ],
    "standard_object_fields": [
      {
        "object": "Contact",
        "fields": [
          { "api_name": "Direct_Phone__c", "label": "Direct Phone", "type": "Phone" }
        ]
      }
    ]
  }
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "overall_severity": "yellow",
  "green_count": 8,
  "yellow_count": 2,
  "red_count": 0,
  "findings": [
    { "severity": "green", "category": "object_name", "message": "Job_Posting__c does not exist — safe to create" },
    { "severity": "yellow", "category": "automation", "message": "Active Flow 'New Contact Welcome Email' triggers on Contact create" },
    { "severity": "yellow", "category": "validation_rule", "message": "Contact.Phone_Format_Check requires 10-digit phone format" }
  ]
}
```

#### POST /api/conflicts/get

> **Status: Not Yet Implemented**

Retrieve a specific conflict report.

**Request:**
```json
{
  "id": "uuid"
}
```

---

### Deploy (Phase 5)

#### POST /api/deploy/custom-objects

> **Status: Not Yet Implemented**

Create or update custom objects and fields.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write` (expected)

**Request:**
```json
{
  "client_id": "uuid",
  "objects": [
    {
      "api_name": "Job_Posting__c",
      "label": "Job Posting",
      "plural_label": "Job Postings",
      "fields": [
        { "api_name": "Job_Title__c", "label": "Job Title", "type": "Text", "length": 255, "required": true },
        { "api_name": "Company_Name__c", "label": "Company Name", "type": "Text", "length": 255 },
        { "api_name": "Location__c", "label": "Location", "type": "Text", "length": 255 },
        { "api_name": "Posting_URL__c", "label": "Posting URL", "type": "Url" },
        { "api_name": "Date_Posted__c", "label": "Date Posted", "type": "Date" },
        { "api_name": "Status__c", "label": "Status", "type": "Picklist", "values": ["Active", "Closed"] },
        { "api_name": "Source__c", "label": "Source", "type": "Text", "length": 100 },
        { "api_name": "Salary_Range__c", "label": "Salary Range", "type": "Text", "length": 100 },
        { "api_name": "Employment_Type__c", "label": "Employment Type", "type": "Picklist", "values": ["Full-time", "Part-time", "Contract", "Temporary"] }
      ],
      "relationships": [
        { "api_name": "Account__c", "label": "Company", "related_to": "Account", "type": "Lookup" }
      ]
    }
  ]
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "status": "succeeded",
  "deployment_type": "custom_object",
  "deployed_at": "2026-02-19T...",
  "result": {
    "objects_created": 1,
    "fields_created": 9,
    "relationships_created": 1
  }
}
```

#### POST /api/deploy/workflows

> **Status: Not Yet Implemented**

Create or update automations in client's Salesforce.

**Request:**
```json
{
  "client_id": "uuid",
  "workflows": [
    {
      "type": "assignment_rule",
      "label": "Assign Dallas postings to Rep A",
      "object": "Job_Posting__c",
      "criteria": { "Location__c": { "contains": "Dallas" } },
      "action": { "assign_to": "user_id_or_queue" }
    }
  ]
}
```

#### POST /api/deploy/status

> **Status: Not Yet Implemented**

Check deployment status.

**Request:**
```json
{
  "id": "uuid"
}
```

#### POST /api/deploy/rollback

> **Status: Not Yet Implemented**

Remove all objects/fields/workflows from a specific deployment.

**Request:**
```json
{
  "id": "uuid"
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "status": "rolled_back",
  "rolled_back_at": "2026-02-19T...",
  "result": {
    "objects_removed": 1,
    "fields_removed": 9,
    "workflows_removed": 1
  }
}
```

---

### Push (Phase 6)

#### POST /api/push/records

> **Status: Not Yet Implemented**

Upsert records into client's Salesforce.

**Auth:** API Token or JWT Session
**Permission:** `push.write` (expected)

**Request:**
```json
{
  "client_id": "uuid",
  "object_type": "Job_Posting__c",
  "external_id_field": "Posting_URL__c",
  "records": [
    {
      "Job_Title__c": "Forklift Operator",
      "Company_Name__c": "Sysco Foods",
      "Location__c": "Dallas, TX",
      "Posting_URL__c": "https://indeed.com/job/12345",
      "Date_Posted__c": "2026-02-18",
      "Status__c": "Active",
      "Source__c": "Indeed",
      "Employment_Type__c": "Full-time"
    }
  ]
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "status": "succeeded",
  "records_total": 1,
  "records_succeeded": 1,
  "records_failed": 0,
  "completed_at": "2026-02-19T..."
}
```

#### POST /api/push/status-update

> **Status: Not Yet Implemented**

Update field values on existing records.

**Request:**
```json
{
  "client_id": "uuid",
  "object_type": "Job_Posting__c",
  "external_id_field": "Posting_URL__c",
  "updates": [
    {
      "Posting_URL__c": "https://indeed.com/job/12345",
      "Status__c": "Closed"
    }
  ]
}
```

#### POST /api/push/link

> **Status: Not Yet Implemented**

Create relationships between records.

**Request:**
```json
{
  "client_id": "uuid",
  "links": [
    {
      "child_object": "Job_Posting__c",
      "child_external_id_field": "Posting_URL__c",
      "child_external_id": "https://indeed.com/job/12345",
      "relationship_field": "Account__c",
      "parent_object": "Account",
      "parent_match_field": "Website",
      "parent_match_value": "sysco.com"
    }
  ]
}
```

---

### Workflows (Phase 7)

#### POST /api/workflows/list

> **Status: Not Yet Implemented**

List active automations in client's Salesforce.

**Request:**
```json
{
  "client_id": "uuid"
}
```

#### POST /api/workflows/deploy

> **Status: Not Yet Implemented**

Create or update automation rules. Same request shape as `POST /api/deploy/workflows`.

#### POST /api/workflows/remove

> **Status: Not Yet Implemented**

Delete deployed automations.

**Request:**
```json
{
  "client_id": "uuid",
  "workflow_ids": ["uuid", "uuid"]
}
```
