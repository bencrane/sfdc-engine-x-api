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

## Conflicts

### POST /api/conflicts/check

Run pre-deploy conflict analysis against the client's latest topology snapshot. Checks for object name collisions, field name collisions, automation triggers, and validation rules that may interfere with a deployment.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write`

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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client whose topology to check against |
| `deployment_plan` | object | yes | Plan describing objects and fields to deploy |

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

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Conflict report UUID (stored for reference by deploy) |
| `overall_severity` | string | `"green"`, `"yellow"`, or `"red"` — worst finding wins |
| `green_count` | integer | Number of green (safe) findings |
| `yellow_count` | integer | Number of yellow (warning) findings |
| `red_count` | integer | Number of red (blocking) findings |
| `findings` | array | List of individual findings with severity, category, and message |

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `No topology snapshot found - run a topology pull first.` |
| 400 | `No connected Salesforce connection found` |
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |

---

### POST /api/conflicts/get

Retrieve a previously stored conflict report by ID.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Conflict report UUID |

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
    { "severity": "yellow", "category": "automation", "message": "Active Flow 'New Contact Welcome Email' triggers on Contact create" }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Conflict report UUID |
| `overall_severity` | string | `"green"`, `"yellow"`, or `"red"` |
| `green_count` | integer | Number of green findings |
| `yellow_count` | integer | Number of yellow findings |
| `red_count` | integer | Number of red findings |
| `findings` | array | List of findings |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Conflict report not found` |

---

## Deploy

### POST /api/deploy/execute

Execute a deployment plan against the client's Salesforce. Creates custom objects and fields via the Metadata and Tooling APIs. The deployment is recorded with full plan and result for status checks and rollback.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write`

**Request:**
```json
{
  "client_id": "uuid",
  "plan": {
    "custom_objects": [
      {
        "api_name": "Job_Posting__c",
        "label": "Job Posting",
        "plural_label": "Job Postings",
        "fields": [
          { "api_name": "Job_Title__c", "label": "Job Title", "type": "Text", "length": 255 },
          { "api_name": "Status__c", "label": "Status", "type": "Picklist", "values": ["Active", "Closed"] }
        ]
      }
    ]
  },
  "conflict_report_id": "uuid (optional)"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client whose Salesforce to deploy into |
| `plan` | object | yes | Deployment plan — objects, fields, relationships |
| `conflict_report_id` | UUID | no | Link to a prior conflict report for audit trail |

**Response (200):**
```json
{
  "id": "uuid",
  "status": "succeeded",
  "deployment_type": "custom_object",
  "deployed_at": "2026-02-19T00:00:00+00:00",
  "result": {
    "status": "succeeded",
    "objects_created": ["Job_Posting__c"],
    "fields_created": ["Job_Posting__c.Job_Title__c", "Job_Posting__c.Status__c"],
    "errors": []
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Deployment UUID |
| `status` | string | `"succeeded"`, `"partial"`, or `"failed"` |
| `deployment_type` | string | Always `"custom_object"` |
| `deployed_at` | string \| null | ISO timestamp of completion |
| `result` | object \| null | Detailed result with created objects/fields and any errors |

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `No connected Salesforce connection found` |
| 400 | `Connection has no Nango connection ID` |
| 400 | `Conflict report not found for this org/client` |
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 502 | Salesforce Metadata/Tooling API error |

---

### POST /api/deploy/status

Get the full status and details for a specific deployment.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Deployment UUID |

**Response (200):**
```json
{
  "id": "uuid",
  "status": "succeeded",
  "deployment_type": "custom_object",
  "deployed_at": "2026-02-19T00:00:00+00:00",
  "result": {
    "status": "succeeded",
    "objects_created": ["Job_Posting__c"],
    "fields_created": ["Job_Posting__c.Job_Title__c"],
    "errors": []
  },
  "plan": {
    "custom_objects": [...]
  },
  "error_message": null,
  "rolled_back_at": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Deployment UUID |
| `status` | string | `"pending"`, `"in_progress"`, `"succeeded"`, `"partial"`, `"failed"`, or `"rolled_back"` |
| `deployment_type` | string | `"custom_object"` |
| `deployed_at` | string \| null | ISO timestamp of completion |
| `result` | object \| null | Detailed deployment result |
| `plan` | object | Original deployment plan |
| `error_message` | string \| null | Error message if deployment failed |
| `rolled_back_at` | string \| null | ISO timestamp if rolled back |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Deployment not found` |

---

### POST /api/deploy/history

List all deployments for a client, ordered by most recent first.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write`

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
      "deployment_type": "custom_object",
      "status": "succeeded",
      "deployed_at": "2026-02-19T00:00:00+00:00",
      "rolled_back_at": null,
      "created_at": "2026-02-19T00:00:00+00:00"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `data[].id` | string | Deployment UUID |
| `data[].deployment_type` | string | `"custom_object"` |
| `data[].status` | string | Deployment status |
| `data[].deployed_at` | string \| null | ISO timestamp of completion |
| `data[].rolled_back_at` | string \| null | ISO timestamp if rolled back |
| `data[].created_at` | string | ISO timestamp of creation |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |

---

### POST /api/deploy/rollback

Roll back a succeeded deployment. Deletes the custom objects and fields that were created. Only deployments in `succeeded` status can be rolled back.

**Auth:** API Token or JWT Session
**Permission:** `deploy.write`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Deployment UUID to roll back |

**Response (200):**
```json
{
  "id": "uuid",
  "status": "rolled_back",
  "rolled_back_at": "2026-02-19T00:00:00+00:00",
  "result": {
    "status": "succeeded",
    "objects_created": ["Job_Posting__c"],
    "fields_created": ["Job_Posting__c.Job_Title__c"],
    "errors": [],
    "rollback": {
      "objects_deleted": ["Job_Posting__c"],
      "fields_deleted": [],
      "errors": []
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Deployment UUID |
| `status` | string | Always `"rolled_back"` on success |
| `rolled_back_at` | string | ISO timestamp of rollback |
| `result` | object \| null | Original deployment result with `rollback` key appended |

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `Deployment does not exist or is not in succeeded status` |
| 400 | `Deployment result is missing or invalid` |
| 400 | `No connected Salesforce connection found` |
| 400 | `Connection has no Nango connection ID` |
| 403 | `Insufficient permissions` |
| 502 | Salesforce API error |

---

## Field Mappings

### POST /api/field-mappings/set

Create or update a field mapping for a client. Maps a canonical object name to a Salesforce object and provides field-level mappings used during push. Upserts on `(org_id, client_id, canonical_object)`.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "client_id": "uuid",
  "canonical_object": "job_posting",
  "sfdc_object": "Job_Posting__c",
  "field_mappings": {
    "title": "Job_Title__c",
    "company": "Company_Name__c",
    "url": "Posting_URL__c",
    "status": "Status__c"
  },
  "external_id_field": "Posting_URL__c"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client UUID |
| `canonical_object` | string | yes | Canonical object name (your internal name) |
| `sfdc_object` | string | yes | Target Salesforce object API name |
| `field_mappings` | object | yes | Map of canonical field names → Salesforce field API names |
| `external_id_field` | string | no | Salesforce external ID field for upserts |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "canonical_object": "job_posting",
  "sfdc_object": "Job_Posting__c",
  "field_mappings": {
    "title": "Job_Title__c",
    "company": "Company_Name__c",
    "url": "Posting_URL__c",
    "status": "Status__c"
  },
  "external_id_field": "Posting_URL__c",
  "is_active": true,
  "created_at": "2026-02-19T00:00:00+00:00",
  "updated_at": "2026-02-19T00:00:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Field mapping UUID |
| `client_id` | string | Client UUID |
| `canonical_object` | string | Canonical object name |
| `sfdc_object` | string | Salesforce object API name |
| `field_mappings` | object | Canonical → SFDC field map |
| `external_id_field` | string \| null | External ID field for upserts |
| `is_active` | boolean | Always `true` after set |
| `created_at` | string | ISO timestamp |
| `updated_at` | string | ISO timestamp |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |

---

### POST /api/field-mappings/list

List all active field mappings for a client.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

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
      "client_id": "uuid",
      "canonical_object": "job_posting",
      "sfdc_object": "Job_Posting__c",
      "field_mappings": {
        "title": "Job_Title__c",
        "company": "Company_Name__c"
      },
      "external_id_field": "Posting_URL__c",
      "is_active": true,
      "created_at": "2026-02-19T00:00:00+00:00",
      "updated_at": "2026-02-19T00:00:00+00:00"
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

### POST /api/field-mappings/get

Get a specific field mapping by canonical object name.

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "client_id": "uuid",
  "canonical_object": "job_posting"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client UUID |
| `canonical_object` | string | yes | Canonical object name to look up |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "canonical_object": "job_posting",
  "sfdc_object": "Job_Posting__c",
  "field_mappings": {
    "title": "Job_Title__c",
    "company": "Company_Name__c"
  },
  "external_id_field": "Posting_URL__c",
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
| 404 | `Field mapping not found` |

---

### POST /api/field-mappings/delete

Soft-delete a field mapping (sets `is_active = false`).

**Auth:** API Token or JWT Session
**Permission:** `org.manage`

**Request:**
```json
{
  "client_id": "uuid",
  "canonical_object": "job_posting"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client UUID |
| `canonical_object` | string | yes | Canonical object name to delete |

**Response (200):**
```json
{
  "canonical_object": "job_posting",
  "is_active": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `canonical_object` | string | The deleted mapping's canonical object name |
| `is_active` | boolean | Always `false` after delete |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 404 | `Field mapping not found` |

---

## Push

### POST /api/push/records

Upsert records into the client's Salesforce via the Composite API. If `canonical_object` is provided, field mappings are resolved automatically — canonical field names in the records are translated to Salesforce API names, and `object_type`/`external_id_field` default from the mapping if not provided explicitly.

**Auth:** API Token or JWT Session
**Permission:** `push.write`

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
      "Status__c": "Active"
    }
  ],
  "canonical_object": "job_posting"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | UUID | yes | Client whose Salesforce to push into |
| `object_type` | string | yes* | Salesforce object API name. *Can be omitted if `canonical_object` is set and a field mapping exists |
| `external_id_field` | string | yes* | Salesforce external ID field for upsert matching. *Can be omitted if resolved from field mapping |
| `records` | array | yes | List of record objects to upsert |
| `canonical_object` | string | no | Canonical object name — if set, resolves field mappings, object type, and external ID field automatically |

**Response (200):**
```json
{
  "id": "uuid",
  "status": "succeeded",
  "records_total": 1,
  "records_succeeded": 1,
  "records_failed": 0,
  "completed_at": "2026-02-19T00:00:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Push log UUID |
| `status` | string | `"succeeded"`, `"partial"`, or `"failed"` |
| `records_total` | integer | Total records submitted |
| `records_succeeded` | integer | Records successfully upserted |
| `records_failed` | integer | Records that failed |
| `completed_at` | string | ISO timestamp of completion |

**Errors:**

| Code | Detail |
|------|--------|
| 400 | `No connected Salesforce connection found` |
| 400 | `Connection has no Nango connection ID` |
| 400 | `object_type is required` |
| 400 | `external_id_field is required` |
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |
| 502 | Salesforce Composite API error |

---

### POST /api/push/status

Get the full status and details for a specific push operation.

**Auth:** API Token or JWT Session
**Permission:** `push.write`

**Request:**
```json
{
  "id": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | yes | Push log UUID |

**Response (200):**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "status": "succeeded",
  "object_type": "Job_Posting__c",
  "records_total": 1,
  "records_succeeded": 1,
  "records_failed": 0,
  "result": {
    "results": [...],
    "errors": []
  },
  "error_message": null,
  "started_at": "2026-02-19T00:00:00+00:00",
  "completed_at": "2026-02-19T00:00:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Push log UUID |
| `client_id` | string | Client UUID |
| `status` | string | `"in_progress"`, `"succeeded"`, `"partial"`, or `"failed"` |
| `object_type` | string | Salesforce object API name |
| `records_total` | integer | Total records submitted |
| `records_succeeded` | integer | Records successfully upserted |
| `records_failed` | integer | Records that failed |
| `result` | object \| null | Detailed result with per-record results and errors |
| `error_message` | string \| null | Error message if push failed |
| `started_at` | string \| null | ISO timestamp of push start |
| `completed_at` | string \| null | ISO timestamp of completion |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Push log not found` |

---

### POST /api/push/history

List all push operations for a client, ordered by most recent first.

**Auth:** API Token or JWT Session
**Permission:** `push.write`

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
      "status": "succeeded",
      "object_type": "Job_Posting__c",
      "records_total": 1,
      "records_succeeded": 1,
      "records_failed": 0,
      "started_at": "2026-02-19T00:00:00+00:00",
      "completed_at": "2026-02-19T00:00:00+00:00",
      "created_at": "2026-02-19T00:00:00+00:00"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `data[].id` | string | Push log UUID |
| `data[].status` | string | Push status |
| `data[].object_type` | string | Salesforce object API name |
| `data[].records_total` | integer | Total records submitted |
| `data[].records_succeeded` | integer | Records successfully upserted |
| `data[].records_failed` | integer | Records that failed |
| `data[].started_at` | string \| null | ISO timestamp of push start |
| `data[].completed_at` | string \| null | ISO timestamp of completion |
| `data[].created_at` | string | ISO timestamp of creation |

**Errors:**

| Code | Detail |
|------|--------|
| 403 | `Insufficient permissions` |
| 404 | `Client not found` |

---

## Not Yet Implemented

The following endpoints are planned but not yet built. Specs are provisional and may change during implementation.

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

Create or update automation rules.

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
