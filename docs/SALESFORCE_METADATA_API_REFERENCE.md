# Salesforce Metadata API Reference

This document is a standalone reference for Salesforce metadata administration across the Tooling API (REST), SOAP Metadata API, and REST Metadata API.

---

## 1) API Landscape

### Core API Comparison

| API | Protocol | Base URL Pattern | Primary Use Case |
|---|---|---|---|
| Tooling API | REST/JSON | `{instance_url}/services/data/{api_version}/tooling/...` | Create and manage selected development metadata records (for example `CustomField`, `ValidationRule`) and query metadata-oriented sObjects |
| Metadata API (SOAP) | SOAP/XML over HTTPS | `{instance_url}/services/Soap/m/{api_version}` | File-based deployment and retrieval of metadata via ZIP + `package.xml`; broadest deployment surface |
| Metadata API (REST) | REST/JSON + ZIP payload fields | `{instance_url}/services/data/{api_version}/metadata/...` | REST wrapper for asynchronous metadata deploy/retrieve workflows and selected metadata operations |

### CRUD and Behavior by API

#### Tooling API
- **Create/read/update/delete:** Supports CRUD for selected Tooling sObjects (for example `CustomField`, `ValidationRule`, some setup components). Coverage is not universal for all metadata types.
- **Execution model:** Primarily synchronous per REST request; long-running deploy-style operations are not the Tooling API model.
- **Authentication:** OAuth bearer token in `Authorization: Bearer {access_token}`.
- **When used:** For direct record-level metadata operations on supported Tooling objects and for metadata-centric SOQL queries.

#### SOAP Metadata API
- **Create/read/update/delete:** Supports broad metadata deployment, retrieval, and deletion through package-based operations.
- **Execution model:** Asynchronous for deploy/retrieve (`deploy()`, `retrieve()` return IDs; status polling required).
- **Authentication:** Session ID in SOAP `SessionHeader` (session token obtained through OAuth/login flow).
- **When used:** For packaging and deploying metadata bundles, retrieving metadata to local artifacts, and destructive changes.

#### REST Metadata API
- **Create/read/update/delete:** Supports asynchronous deploy/retrieve operations and selected metadata REST resources. Coverage is narrower than SOAP Metadata API for some metadata types/features.
- **Execution model:** Asynchronous for deploy/retrieve endpoints (status endpoints polled by ID).
- **Authentication:** OAuth bearer token in `Authorization: Bearer {access_token}`.
- **When used:** For metadata deploy/retrieve workflows over REST without SOAP envelope handling.

### Capability Matrix

`Yes` indicates documented support path exists. `Partial` means support exists but is constrained by type/version/operation details. `No` means no direct supported path in that API for practical deployment/management.

| Component Type | Tooling API | SOAP Metadata API | REST Metadata API |
|---|---|---|---|
| Custom Objects | Partial | Yes | Partial |
| Custom Fields | Yes | Yes | Partial |
| Picklists | Partial | Yes | Partial |
| Relationships (Lookup/Master-Detail) | Partial | Yes | Partial |
| Flows | Partial | Yes | Partial |
| Validation Rules | Yes | Yes | Partial |
| Layouts / Page Layouts | No | Yes | Partial |
| Permission Sets | Partial | Yes | Partial |
| Record Types | Partial | Yes | Partial |
| Assignment Rules | No | Yes | Partial |

---

## 2) Authentication

### OAuth Bearer Tokens Across the Three APIs

- OAuth access tokens authorize API calls in Salesforce.
- REST APIs (Tooling API and REST Metadata API) use:
  - `Authorization: Bearer {access_token}`
- SOAP Metadata API uses the same session credential in SOAP header:
  - `<met:SessionHeader><met:sessionId>{access_token_or_session_id}</met:sessionId></met:SessionHeader>`

### OAuth Scopes

Salesforce connected apps commonly grant API access through scopes including:
- `api` (general API access)
- `full` (full access)
- `refresh_token` / `offline_access` (token refresh capability)

Salesforce documentation does not define a standard OAuth scope named `metadata_api` for core org Metadata API access. Metadata access is enforced by user permissions and connected app policy in combination with API scope.

### API-Specific Auth Notes

- **Tooling API / REST Metadata API:** Require REST base URL calls to the org instance (`{instance_url}`) and valid bearer token.
- **SOAP Metadata API:** Requires SOAP endpoint and `SessionHeader`.
- **Permissions:** Insufficient user permissions return authorization errors even if OAuth token is valid.

---

## 3) Tooling API

Base resource root:

- `{instance_url}/services/data/{api_version}/tooling`

Standard headers for Tooling examples:

- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

### 3.1 Create a Custom Object (`CustomObject` sObject)

Salesforce documentation for Tooling API indicates `CustomObject` support is constrained; creating a net-new custom object via Tooling REST is not the general deployment path.

**Status:** Not generally supported as a reliable Tooling create pattern for net-new object metadata deployment.

**Endpoint:** N/A for supported generic create flow  
**Method:** N/A  
**Request Body:** N/A  
**Response Body:** N/A

Representative unsupported-attempt response shape:

```json
{
  "message": "Operation not supported for this sObject type in Tooling API",
  "errorCode": "INVALID_TYPE"
}
```

### 3.2 Create a Custom Field (`CustomField` sObject)

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/CustomField`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "FullName": "Invoice__c.External_Id__c",
  "Metadata": {
    "type": "Text",
    "label": "External Id",
    "length": 100,
    "required": false,
    "unique": false,
    "externalId": true
  }
}
```

**Response body**
```json
{
  "id": "01Ixx0000008abcEAA",
  "success": true,
  "errors": []
}
```

### 3.3 Create Picklist Values on a Field

Tooling API supports metadata mutation of a `CustomField` record where picklist values are part of the field metadata.

**Method:** `PATCH`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/CustomField/01Ixx0000008abcEAA`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "Metadata": {
    "type": "Picklist",
    "label": "Stage",
    "valueSet": {
      "restricted": true,
      "valueSetDefinition": {
        "sorted": false,
        "value": [
          {
            "fullName": "New",
            "default": true,
            "label": "New",
            "isActive": true
          },
          {
            "fullName": "Qualified",
            "default": false,
            "label": "Qualified",
            "isActive": true
          },
          {
            "fullName": "Closed",
            "default": false,
            "label": "Closed",
            "isActive": true
          }
        ]
      }
    }
  }
}
```

**Response body**
```json
{
  "id": "01Ixx0000008abcEAA",
  "success": true,
  "errors": []
}
```

### 3.4 Create a Lookup Relationship Field

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/CustomField`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "FullName": "Invoice__c.Account__c",
  "Metadata": {
    "type": "Lookup",
    "label": "Account",
    "referenceTo": "Account",
    "relationshipName": "Invoices",
    "required": false,
    "deleteConstraint": "SetNull"
  }
}
```

**Response body**
```json
{
  "id": "01Ixx0000008abdEAA",
  "success": true,
  "errors": []
}
```

### 3.5 Create a Master-Detail Relationship Field

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/CustomField`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "FullName": "Invoice_Line__c.Invoice__c",
  "Metadata": {
    "type": "MasterDetail",
    "label": "Invoice",
    "referenceTo": "Invoice__c",
    "relationshipName": "InvoiceLines",
    "reparentableMasterDetail": false,
    "writeRequiresMasterRead": false
  }
}
```

**Response body**
```json
{
  "id": "01Ixx0000008abeEAA",
  "success": true,
  "errors": []
}
```

### 3.6 Query Existing Custom Objects and Fields

#### Query custom fields
**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName,TableEnumOrId,NamespacePrefix+FROM+CustomField+WHERE+TableEnumOrId='Invoice__c'`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: application/json`

**Request body**
```json
{}
```

**Response body**
```json
{
  "totalSize": 2,
  "done": true,
  "records": [
    {
      "attributes": {
        "type": "CustomField",
        "url": "/services/data/{api_version}/tooling/sobjects/CustomField/01Ixx0000008abcEAA"
      },
      "Id": "01Ixx0000008abcEAA",
      "DeveloperName": "External_Id",
      "TableEnumOrId": "Invoice__c",
      "NamespacePrefix": null
    },
    {
      "attributes": {
        "type": "CustomField",
        "url": "/services/data/{api_version}/tooling/sobjects/CustomField/01Ixx0000008abdEAA"
      },
      "Id": "01Ixx0000008abdEAA",
      "DeveloperName": "Account",
      "TableEnumOrId": "Invoice__c",
      "NamespacePrefix": null
    }
  ]
}
```

#### Query custom objects
**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName,NamespacePrefix+FROM+CustomObject+WHERE+DeveloperName='Invoice'`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: application/json`

**Request body**
```json
{}
```

**Response body**
```json
{
  "totalSize": 1,
  "done": true,
  "records": [
    {
      "attributes": {
        "type": "CustomObject",
        "url": "/services/data/{api_version}/tooling/sobjects/CustomObject/01Ixx0000009000EAA"
      },
      "Id": "01Ixx0000009000EAA",
      "DeveloperName": "Invoice",
      "NamespacePrefix": null
    }
  ]
}
```

### 3.7 Create or Update a Validation Rule (`ValidationRule` sObject)

#### Create
**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/ValidationRule`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "EntityDefinitionId": "01Ixx0000009000EAA",
  "ValidationName": "Require_Status",
  "Active": true,
  "Description": "Status is required when Amount is populated",
  "ErrorDisplayField": "Status__c",
  "ErrorMessage": "Status must be populated when Amount is set.",
  "ErrorConditionFormula": "AND(NOT(ISBLANK(Amount__c)), ISBLANK(TEXT(Status__c)))"
}
```

**Response body**
```json
{
  "id": "03dxx0000004xyzAAA",
  "success": true,
  "errors": []
}
```

#### Update
**Method:** `PATCH`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/ValidationRule/03dxx0000004xyzAAA`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "Active": false,
  "ErrorMessage": "Status is required whenever Amount is present."
}
```

**Response body**
```json
{
  "id": "03dxx0000004xyzAAA",
  "success": true,
  "errors": []
}
```

### 3.8 Create or Update a Flow (`Flow` / `FlowDefinition`)

Flow metadata lifecycle is primarily Metadata API-based. Tooling API supports query and selected record operations depending on org/version.

#### Query flow definitions
**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName,ActiveVersionId,LatestVersionId+FROM+FlowDefinition+WHERE+DeveloperName='Invoice_Automation'`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: application/json`

**Request body**
```json
{}
```

**Response body**
```json
{
  "totalSize": 1,
  "done": true,
  "records": [
    {
      "attributes": {
        "type": "FlowDefinition",
        "url": "/services/data/{api_version}/tooling/sobjects/FlowDefinition/301xx0000001abcAAA"
      },
      "Id": "301xx0000001abcAAA",
      "DeveloperName": "Invoice_Automation",
      "ActiveVersionId": "300xx0000001defAAA",
      "LatestVersionId": "300xx0000001defAAA"
    }
  ]
}
```

#### Update FlowDefinition activation pointer (supported in orgs where writable)
**Method:** `PATCH`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/FlowDefinition/301xx0000001abcAAA`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "Metadata": {
    "activeVersionNumber": 3
  }
}
```

**Response body**
```json
{
  "id": "301xx0000001abcAAA",
  "success": true,
  "errors": []
}
```

### 3.9 Delete a Custom Field

**Method:** `DELETE`  
**URL:** `{instance_url}/services/data/{api_version}/tooling/sobjects/CustomField/01Ixx0000008abcEAA`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: application/json`

**Request body**
```json
{}
```

**Response body**
```json
{
  "id": "01Ixx0000008abcEAA",
  "success": true,
  "errors": []
}
```

### 3.10 Delete a Custom Object

Direct Tooling API custom-object deletion support is constrained and not the standard metadata deletion path.

**Status:** Common deletion path is Metadata API destructive deployment.

Representative unsupported direct deletion response:

```json
{
  "message": "Delete not supported for this metadata type through Tooling API endpoint",
  "errorCode": "METHOD_NOT_ALLOWED"
}
```

### Tooling API Error Response Shapes

Validation/business errors are typically returned as arrays:

```json
[
  {
    "message": "Required field is missing: FullName",
    "errorCode": "REQUIRED_FIELD_MISSING",
    "fields": [
      "FullName"
    ]
  }
]
```

Server-side failures:

```json
[
  {
    "message": "An unexpected error occurred",
    "errorCode": "UNKNOWN_EXCEPTION",
    "fields": []
  }
]
```

### Tooling API Limitations (Documented Operational Gaps)

- Not a full replacement for Metadata API package deployment.
- Deployment of broad metadata bundles (layouts, assignment rules, approval processes, full flow definitions with dependencies) is Metadata API-oriented.
- Destructive batch deletes and ordered deploy transactions are Metadata API-oriented.
- Coverage varies by metadata type and API version for create/update/delete semantics.

### Tooling API sObjects and Query Patterns

Common patterns:
- `GET .../tooling/query?q=SELECT ... FROM CustomField ...`
- `GET .../tooling/query?q=SELECT ... FROM ValidationRule ...`
- `GET .../tooling/query?q=SELECT ... FROM FlowDefinition ...`
- `GET .../tooling/sobjects/{Type}/{Id}`
- `POST/PATCH/DELETE .../tooling/sobjects/{Type}[/{Id}]`

---

## 4) SOAP Metadata API

### Endpoint and Headers

**Method:** `POST`  
**URL:** `{instance_url}/services/Soap/m/{api_version}`

**Required headers**
- `Content-Type: text/xml; charset=UTF-8`
- `SOAPAction: ""`

### 4.1 `deploy()` Lifecycle

`deploy()` sends a ZIP file (base64 encoded) containing metadata files and `package.xml`.

#### Complete SOAP envelope example (`deploy()`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{access_token_or_session_id}</met:sessionId>
    </met:SessionHeader>
    <met:CallOptions>
      <met:client>MetadataDeployClient</met:client>
    </met:CallOptions>
  </soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{base64_encoded_zip_bytes}</met:ZipFile>
      <met:DeployOptions>
        <met:allowMissingFiles>false</met:allowMissingFiles>
        <met:autoUpdatePackage>false</met:autoUpdatePackage>
        <met:checkOnly>false</met:checkOnly>
        <met:ignoreWarnings>false</met:ignoreWarnings>
        <met:performRetrieve>false</met:performRetrieve>
        <met:purgeOnDelete>false</met:purgeOnDelete>
        <met:rollbackOnError>true</met:rollbackOnError>
        <met:singlePackage>true</met:singlePackage>
        <met:testLevel>NoTestRun</met:testLevel>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>
```

#### `deploy()` response example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <deployResponse xmlns="http://soap.sforce.com/2006/04/metadata">
      <result>
        <id>0Afxx0000004ABCGA2</id>
        <state>Queued</state>
      </result>
    </deployResponse>
  </soapenv:Body>
</soapenv:Envelope>
```

### 4.2 `package.xml` Structure and Examples

`package.xml` declares metadata members by type.

#### Example: custom object + fields + flow + validation rules + layout

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Invoice__c</members>
    <name>CustomObject</name>
  </types>
  <types>
    <members>Invoice__c.External_Id__c</members>
    <members>Invoice__c.Account__c</members>
    <name>CustomField</name>
  </types>
  <types>
    <members>Invoice__c.Require_Status</members>
    <name>ValidationRule</name>
  </types>
  <types>
    <members>Invoice_Automation</members>
    <name>Flow</name>
  </types>
  <types>
    <members>Invoice__c-Invoice Layout</members>
    <name>Layout</name>
  </types>
  <version>{api_version_number_only}</version>
</Package>
```

### 4.3 ZIP File Structure

Expected file layout (single-package deploy):

```xml
package.xml
objects/
  Invoice__c.object
flows/
  Invoice_Automation.flow-meta.xml
layouts/
  Invoice__c-Invoice Layout.layout-meta.xml
```

Metadata naming convention examples:
- Custom object file: `objects/Invoice__c.object`
- Field inside object file or as separate deploy unit via metadata type declarations
- Flow metadata file: `flows/{FlowApiName}.flow-meta.xml`
- Layout metadata file: `layouts/{ObjectApiName}-{LayoutLabel}.layout-meta.xml`

### 4.4 `checkDeployStatus()` Polling

#### Request envelope

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{access_token_or_session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>0Afxx0000004ABCGA2</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>
```

#### Response envelope

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <checkDeployStatusResponse xmlns="http://soap.sforce.com/2006/04/metadata">
      <result>
        <id>0Afxx0000004ABCGA2</id>
        <status>Succeeded</status>
        <success>true</success>
        <numberComponentsTotal>5</numberComponentsTotal>
        <numberComponentsDeployed>5</numberComponentsDeployed>
        <numberComponentErrors>0</numberComponentErrors>
        <details>
          <componentSuccesses>
            <componentType>CustomObject</componentType>
            <fullName>Invoice__c</fullName>
            <success>true</success>
          </componentSuccesses>
        </details>
      </result>
    </checkDeployStatusResponse>
  </soapenv:Body>
</soapenv:Envelope>
```

Interpretation:
- `status`: processing state (`Pending`, `InProgress`, terminal states)
- `success`: overall boolean outcome
- component/test detail blocks identify exact failures

### 4.5 `retrieve()` Lifecycle

#### Request envelope

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{access_token_or_session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:retrieve>
      <met:retrieveRequest>
        <met:apiVersion>{api_version_number_only}</met:apiVersion>
        <met:singlePackage>true</met:singlePackage>
        <met:unpackaged>
          <met:types>
            <met:members>Invoice__c</met:members>
            <met:name>CustomObject</met:name>
          </met:types>
          <met:version>{api_version_number_only}</met:version>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>
```

#### Response envelope

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <retrieveResponse xmlns="http://soap.sforce.com/2006/04/metadata">
      <result>
        <id>09Sxx0000007XYZEA2</id>
        <state>Queued</state>
      </result>
    </retrieveResponse>
  </soapenv:Body>
</soapenv:Envelope>
```

### 4.6 `checkRetrieveStatus()` Polling

#### Request envelope

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{access_token_or_session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkRetrieveStatus>
      <met:asyncProcessId>09Sxx0000007XYZEA2</met:asyncProcessId>
      <met:includeZip>true</met:includeZip>
    </met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>
```

#### Response envelope

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <checkRetrieveStatusResponse xmlns="http://soap.sforce.com/2006/04/metadata">
      <result>
        <id>09Sxx0000007XYZEA2</id>
        <status>Succeeded</status>
        <success>true</success>
        <fileProperties>
          <fileName>objects/Invoice__c.object</fileName>
          <fullName>Invoice__c</fullName>
          <type>CustomObject</type>
        </fileProperties>
        <zipFile>{base64_encoded_zip_bytes}</zipFile>
      </result>
    </checkRetrieveStatusResponse>
  </soapenv:Body>
</soapenv:Envelope>
```

### 4.7 DeployOptions (Common Fields)

| DeployOption | Purpose |
|---|---|
| `rollbackOnError` | Roll back all component changes on failure when true |
| `singlePackage` | Indicates ZIP has one package boundary |
| `testLevel` | Controls Apex test execution (`NoTestRun`, `RunLocalTests`, `RunAllTestsInOrg`, `RunSpecifiedTests`) |
| `checkOnly` | Validation-only deploy (no commit) |
| `ignoreWarnings` | Continue despite warnings |
| `purgeOnDelete` | Hard-delete where supported instead of recycle-bin behavior |
| `allowMissingFiles` | Allows deploy even when listed files are missing |
| `autoUpdatePackage` | Updates package manifest to include missing dependencies in package context |

### 4.8 Destructive Changes

Deletion in Metadata API uses destructive manifests:
- `destructiveChangesPre.xml` (executed before main deploy package)
- `destructiveChanges.xml` (executed after main package)

`destructiveChanges.xml` example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Invoice__c.External_Id__c</members>
    <name>CustomField</name>
  </types>
  <types>
    <members>Invoice__c</members>
    <name>CustomObject</name>
  </types>
  <version>{api_version_number_only}</version>
</Package>
```

### What SOAP Metadata API Can Do Beyond Typical Tooling API Paths

- Ordered, package-atomic deploy/retrieve operations.
- Broader metadata type support (layouts, assignment rules, workflow/approval/process components, destructive manifests).
- Asynchronous deployment lifecycle with full deploy result details.

---

## 5) REST Metadata API

REST Metadata API uses REST endpoints for asynchronous metadata jobs and selected metadata operations.

Standard headers:
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

### 5.1 Deploy Request

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/metadata/deployRequest`

**Request body**
```json
{
  "zipFile": "{base64_encoded_zip_bytes}",
  "deployOptions": {
    "allowMissingFiles": false,
    "autoUpdatePackage": false,
    "checkOnly": false,
    "ignoreWarnings": false,
    "performRetrieve": false,
    "purgeOnDelete": false,
    "rollbackOnError": true,
    "singlePackage": true,
    "testLevel": "NoTestRun"
  }
}
```

**Response body**
```json
{
  "id": "0Afxx0000004ABCGA2",
  "state": "Queued"
}
```

### 5.2 Deploy Status

**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/metadata/deployRequest/0Afxx0000004ABCGA2`

**Request body**
```json
{}
```

**Response body**
```json
{
  "id": "0Afxx0000004ABCGA2",
  "status": "Succeeded",
  "success": true,
  "numberComponentsTotal": 5,
  "numberComponentsDeployed": 5,
  "numberComponentErrors": 0,
  "details": {
    "componentSuccesses": [
      {
        "componentType": "CustomObject",
        "fullName": "Invoice__c",
        "success": true
      }
    ],
    "componentFailures": []
  }
}
```

### 5.3 Retrieve Request

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/metadata/retrieveRequest`

**Request body**
```json
{
  "apiVersion": "{api_version_number_only}",
  "singlePackage": true,
  "unpackaged": {
    "types": [
      {
        "members": [
          "Invoice__c"
        ],
        "name": "CustomObject"
      }
    ],
    "version": "{api_version_number_only}"
  }
}
```

**Response body**
```json
{
  "id": "09Sxx0000007XYZEA2",
  "state": "Queued"
}
```

### 5.4 Retrieve Status

**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/metadata/retrieveRequest/09Sxx0000007XYZEA2`

**Request body**
```json
{}
```

**Response body**
```json
{
  "id": "09Sxx0000007XYZEA2",
  "status": "Succeeded",
  "success": true,
  "fileProperties": [
    {
      "fileName": "objects/Invoice__c.object",
      "fullName": "Invoice__c",
      "type": "CustomObject"
    }
  ],
  "zipFile": "{base64_encoded_zip_bytes}"
}
```

### REST Metadata API Overlap and Differences vs SOAP Metadata API

| Area | REST Metadata API | SOAP Metadata API |
|---|---|---|
| Transport | JSON REST + binary fields represented as base64 strings | SOAP XML envelope |
| Deploy/retrieve model | Async IDs + polling endpoints | Async IDs + `check*Status` SOAP calls |
| Metadata type coverage | Partial depending on endpoint and version | Broadest documented deployment coverage |
| Destructive changes | Passed via deploy ZIP manifests like SOAP | Native package/deploy workflow |
| Operational model | Simpler HTTP tooling integration | Canonical Metadata API contract |

### Current Limitations (REST Metadata API)

- Coverage parity with SOAP Metadata API is incomplete for some metadata types and operations.
- Some advanced deploy options/behaviors may still be documented first in SOAP-oriented references.
- Version-specific behavior can differ by org release and enabled features.

---

## 6) Custom Object Lifecycle

### Create

#### Tooling API path (where supported for specific object metadata operations)
- Tooling API is commonly used for field-level metadata mutations and metadata queries.
- Net-new custom object deployment is generally handled by Metadata API package deploy.

#### Metadata API path (SOAP/REST deploy)
- Create object by deploying `objects/{ObjectApiName}.object` in ZIP with `package.xml`.

`objects/Invoice__c.object` example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <label>Invoice</label>
  <pluralLabel>Invoices</pluralLabel>
  <nameField>
    <label>Invoice Number</label>
    <type>Text</type>
  </nameField>
  <deploymentStatus>Deployed</deploymentStatus>
  <sharingModel>ReadWrite</sharingModel>
  <enableActivities>true</enableActivities>
  <enableReports>true</enableReports>
</CustomObject>
```

### Add Fields

- **Tooling API:** `POST/PATCH` on `CustomField` for supported field types.
- **Metadata API:** deploy updated object XML or field metadata files in package.

### Add Relationships

- **Lookup:** field metadata with `type=Lookup` and `referenceTo`.
- **Master-Detail:** field metadata with `type=MasterDetail`, relationship properties.
- Both can be represented in Tooling `CustomField` metadata payloads where supported and in Metadata API XML deploys.

### Read/Describe

Three common read surfaces:
- REST SObject describe:
  - `GET {instance_url}/services/data/{api_version}/sobjects/Invoice__c/describe`
- Tooling SOQL query:
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+...+FROM+CustomField`
- Metadata retrieve:
  - SOAP `retrieve()` or REST metadata `retrieveRequest`.

### Update

- **Labels/properties:** update in object metadata XML and redeploy via Metadata API.
- **Additional fields:** create new `CustomField` entries via Tooling or deploy metadata bundle.

### Delete

- **Tooling:** direct delete supported for selected metadata-backed records (for example many `CustomField` paths).
- **Metadata API:** destructive changes manifest for object/field removal with dependency checks.
- Deletion is blocked when dependencies exist (references in flows, reports, formulas, layouts, etc.).

---

## 7) Workflow and Automation Deployment

| Automation Type | Tooling API | SOAP Metadata API | REST Metadata API |
|---|---|---|---|
| Flows | Partial (`FlowDefinition` and related records) | Yes | Partial |
| Process Builder (legacy) | No | Yes (`Flow`/process metadata artifacts) | Partial |
| Assignment Rules | No | Yes | Partial |
| Validation Rules | Yes (`ValidationRule`) | Yes | Partial |
| Workflow Rules (legacy) | No | Yes (`Workflow` metadata) | Partial |
| Approval Processes | No | Yes (`ApprovalProcess` metadata) | Partial |

### Flow Notes

- Flow metadata deployment and versioning behavior is fully represented in Metadata API package workflows.
- Tooling API can expose/query flow records and selected updates depending on type/version constraints.

### Validation Rule Notes

- Tooling API offers direct CRUD for `ValidationRule` records on supported entities.
- Metadata API supports file-based deployment with object-level metadata definitions.

---

## 8) Rollback and Destructive Changes

### Tooling API DELETE

Direct `DELETE` is available for supported Tooling sObjects. Commonly used for:
- `CustomField` records (when dependencies permit)
- Selected other tooling metadata records depending on type/version

### Metadata API Destructive Deploy

Deletion workflow uses deploy package with:
- `destructiveChangesPre.xml` (delete before add/update deploy)
- `destructiveChanges.xml` (delete after add/update deploy)
- `package.xml` (can be minimal for destructive deploys)

Two-phase pattern exists to resolve dependencies where pre-delete is required before component updates.

### Deletion Limitations

- Components referenced by dependencies cannot be deleted until references are removed.
- Managed-package protected components may not be deletable in subscriber orgs.
- Some metadata states allow deactivation/deprecation rather than hard deletion.

### Delete vs Deprecate for Managed Components

- **Delete:** Physical metadata removal (where permitted).
- **Deprecate:** Component remains but is marked or versioned to stop active use; managed package constraints often favor deprecation semantics.

---

## 9) Rate Limits and Quotas

Salesforce publishes API limits in the Limits Cheat Sheet and edition-specific tables; exact entitlement depends on edition, license counts, and purchased add-ons.

### Daily API Request Limits (24-hour window)

| Edition | Documented Baseline Pattern |
|---|---|
| Developer Edition | Fixed developer-org daily API allocation (commonly 15,000/day in published limits tables) |
| Professional Edition | API entitlement depends on edition access and license-based/org-level limits; org configuration dependent |
| Enterprise Edition | Baseline org entitlement with scaling based on license counts and add-ons |
| Unlimited Edition | Higher entitlement tier with scaling and add-on options |

### Shared Consumption Model

- Limits are org-wide and shared across all connected apps/integrations for that org.
- Exceeding daily allowance can return `REQUEST_LIMIT_EXCEEDED` responses.

### Concurrent Long-Running Request Limits

- Salesforce enforces concurrency limits for long-running synchronous requests and async job queues.
- Metadata deploy/retrieve jobs are queued and processed asynchronously with org-level concurrency controls.

### Metadata API-Specific Limits

Commonly documented limits include:
- Maximum 10,000 files per deploy/retrieve job.
- Compressed ZIP size limit (SOAP Metadata deploy/retrieve commonly documented at 39 MB compressed).

### Tooling API-Specific Limits

- Tooling API requests count against org API usage similar to REST API usage accounting.
- No separate unlimited Tooling pool; usage contributes to overall org API limits.

### Checking Remaining Limits

REST responses may include:

`Sforce-Limit-Info: api-usage=1234/100000`

This header reports current API consumption relative to limit.

---

## 10) Gotchas and Edge Cases

### Field Dependencies That Block Deletion

- Fields referenced by formulas, validation rules, flows/processes, reports, list views, layouts, and Apex can block deletion.
- Resolve all references before DELETE/destructive deploy.

### Required Fields on Standard Objects

- Record creation and related metadata operations can fail if object-required fields/business rules are not satisfied.

### Custom Object Naming Rules

- Custom object API names use `__c` suffix.
- Naming has character and uniqueness constraints.
- Reserved words/system conflicts can block creation.

### Managed vs Unmanaged Package Context

- Managed package metadata can have immutability or subscriber restrictions.
- Namespace qualification can change member names in metadata manifests.

### Namespace Prefix Behavior

- API names may appear as `{namespace}__Component__c` in managed contexts.
- Manifest members must match namespaced full names where applicable.

### Sandbox vs Production Behavior Differences

- Validation/test enforcement and available metadata may differ by org type and release state.
- Deployment/test requirements differ by target environment and settings.

### Metadata Deploy Order and Dependencies

- Component dependencies in one deploy package can require specific pre-existing metadata or packaging order.
- Destructive pre/post manifests are used to control order-sensitive deletes.

### Tooling vs Metadata Field Type Name Differences

- Same conceptual field type can be represented with different property naming patterns across Tooling JSON and Metadata XML.

### Compound Fields

- Compound standard fields (for example Address/Name structures) have component-field behavior that affects query/update/delete semantics.

### Status Values and Transitions

- Async deploy/retrieve status transitions include queued/in-progress/terminal states.
- Flow activation/version status changes involve definition/version relationships and may require explicit activation pointers.

---

## Official Documentation Sources Consulted

- Salesforce Tooling API Developer Guide
  - REST resources and Tooling sObject reference pages (including `CustomField`, `CustomObject`, query resources)
- Salesforce Metadata API Developer Guide
  - `deploy()`, `checkDeployStatus()`, `retrieve()`, `checkRetrieveStatus()`, file-based deployment/retrieval
- Salesforce REST Metadata API documentation
  - `metadata/deployRequest`, `metadata/retrieveRequest`, and status resources
- Salesforce API Limits documentation
  - Limits Cheat Sheet, edition limits tables, REST limit headers (`Sforce-Limit-Info`)

All endpoint URL examples in this document intentionally use placeholders:
- `{instance_url}`
- `{api_version}`

