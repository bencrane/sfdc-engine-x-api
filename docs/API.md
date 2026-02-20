# API Reference — sfdc-engine-x

All endpoints use POST unless noted. All require authentication via Bearer token (API token or JWT).

---

## Auth

### POST /api/auth/login

Issue a JWT session token.

**Request:**
```json
{
  "email": "admin@revenueactivation.com",
  "password": "..."
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### GET /api/auth/me

Return current auth context.

**Response:**
```json
{
  "org_id": "uuid",
  "user_id": "uuid",
  "role": "org_admin",
  "permissions": ["connections.read", "connections.write", "topology.read", "deploy.write", "push.write", "workflows.read", "workflows.write", "org.manage"],
  "client_id": null,
  "auth_method": "session"
}
```

---

## Connections

### POST /api/connections/create

Exchange OAuth authorization code for tokens and store the connection.

**Request:**
```json
{
  "client_id": "uuid",
  "authorization_code": "abc123xyz"
}
```

**Response:**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "status": "connected",
  "instance_url": "https://acme.my.salesforce.com",
  "sfdc_org_id": "00D...",
  "created_at": "2026-02-19T..."
}
```

### POST /api/connections/list

**Request:**
```json
{
  "client_id": "uuid (optional — omit for all connections in org)"
}
```

**Response:**
```json
{
  "data": [
    {
      "id": "uuid",
      "client_id": "uuid",
      "client_name": "Acme Corp",
      "status": "connected",
      "instance_url": "https://acme.my.salesforce.com",
      "last_used_at": "2026-02-19T...",
      "created_at": "2026-02-19T..."
    }
  ]
}
```

### POST /api/connections/get

**Request:**
```json
{
  "id": "uuid"
}
```

**Response:**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "status": "connected",
  "instance_url": "https://acme.my.salesforce.com",
  "sfdc_org_id": "00D...",
  "sfdc_user_id": "005...",
  "scopes": "full refresh_token",
  "last_refreshed_at": "2026-02-19T...",
  "last_used_at": "2026-02-19T...",
  "created_at": "2026-02-19T..."
}
```

### POST /api/connections/refresh

Force a token refresh.

**Request:**
```json
{
  "client_id": "uuid"
}
```

**Response:**
```json
{
  "status": "connected",
  "last_refreshed_at": "2026-02-19T..."
}
```

### POST /api/connections/revoke

Disconnect a client's Salesforce. Revokes refresh token with Salesforce.

**Request:**
```json
{
  "client_id": "uuid"
}
```

**Response:**
```json
{
  "status": "revoked"
}
```

---

## Topology

### POST /api/topology/pull

Pull and store the client's full CRM schema.

**Request:**
```json
{
  "client_id": "uuid"
}
```

**Response:**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "version": 3,
  "objects_count": 847,
  "custom_objects_count": 12,
  "pulled_at": "2026-02-19T..."
}
```

### POST /api/topology/get

Retrieve the latest stored snapshot.

**Request:**
```json
{
  "client_id": "uuid",
  "version": "integer (optional — omit for latest)"
}
```

**Response:**
```json
{
  "id": "uuid",
  "client_id": "uuid",
  "version": 3,
  "objects_count": 847,
  "custom_objects_count": 12,
  "snapshot": { ... },
  "pulled_at": "2026-02-19T..."
}
```

### POST /api/topology/history

List snapshot versions for a client.

**Request:**
```json
{
  "client_id": "uuid"
}
```

**Response:**
```json
{
  "data": [
    { "id": "uuid", "version": 3, "objects_count": 847, "custom_objects_count": 12, "pulled_at": "2026-02-19T..." },
    { "id": "uuid", "version": 2, "objects_count": 840, "custom_objects_count": 11, "pulled_at": "2026-02-01T..." },
    { "id": "uuid", "version": 1, "objects_count": 835, "custom_objects_count": 10, "pulled_at": "2026-01-15T..." }
  ]
}
```

---

## Conflicts

### POST /api/conflicts/check

Run pre-deploy conflict analysis.

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

**Response:**
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

### POST /api/conflicts/get

**Request:**
```json
{
  "id": "uuid"
}
```

---

## Deploy

### POST /api/deploy/custom-objects

Create or update custom objects and fields.

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

**Response:**
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

### POST /api/deploy/workflows

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

### POST /api/deploy/status

**Request:**
```json
{
  "id": "uuid"
}
```

### POST /api/deploy/rollback

Remove all objects/fields/workflows from a specific deployment.

**Request:**
```json
{
  "id": "uuid"
}
```

**Response:**
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

## Push

### POST /api/push/records

Upsert records into client's Salesforce.

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

**Response:**
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

### POST /api/push/status-update

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

### POST /api/push/link

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

## Workflows

### POST /api/workflows/list

List active automations in client's Salesforce.

**Request:**
```json
{
  "client_id": "uuid"
}
```

### POST /api/workflows/deploy

Create or update automation rules.

**Request:** Same as POST /api/deploy/workflows.

### POST /api/workflows/remove

Delete deployed automations.

**Request:**
```json
{
  "client_id": "uuid",
  "workflow_ids": ["uuid", "uuid"]
}
```

---

## Health

### GET /health

No authentication required.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-02-19T..."
}
```