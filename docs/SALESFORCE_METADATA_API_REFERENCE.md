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

<!-- EXPANDED -->
#### Metadata API Flow XML (complete deploy example)

The following is a complete `flows/Invoice_Record_Triggered_Automation.flow-meta.xml` example for a record-triggered Flow on `Invoice__c` that:
- runs on create
- checks whether `Amount__c > 1000`
- performs a field update when condition is met

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
  <apiVersion>{api_version_number_only}</apiVersion>
  <areMetricsLoggedToDataCloud>false</areMetricsLoggedToDataCloud>
  <assignments>
    <name>Set_Priority_High</name>
    <label>Set Priority High</label>
    <locationX>420</locationX>
    <locationY>430</locationY>
    <assignmentItems>
      <assignToReference>$Record.Priority__c</assignToReference>
      <operator>Assign</operator>
      <value>
        <stringValue>High</stringValue>
      </value>
    </assignmentItems>
    <connector>
      <targetReference>Update_Invoice</targetReference>
    </connector>
  </assignments>
  <decisions>
    <name>Amount_Greater_Than_1000</name>
    <label>Amount Greater Than 1000</label>
    <locationX>420</locationX>
    <locationY>290</locationY>
    <defaultConnectorLabel>Default Outcome</defaultConnectorLabel>
    <rules>
      <name>AmountAboveThreshold</name>
      <conditionLogic>and</conditionLogic>
      <conditions>
        <leftValueReference>$Record.Amount__c</leftValueReference>
        <operator>GreaterThan</operator>
        <rightValue>
          <numberValue>1000</numberValue>
        </rightValue>
      </conditions>
      <connector>
        <targetReference>Set_Priority_High</targetReference>
      </connector>
      <label>Amount Above Threshold</label>
    </rules>
  </decisions>
  <environments>Default</environments>
  <interviewLabel>Invoice Record Triggered {!$Flow.CurrentDateTime}</interviewLabel>
  <label>Invoice Record Triggered Automation</label>
  <processMetadataValues>
    <name>BuilderType</name>
    <value>
      <stringValue>LightningFlowBuilder</stringValue>
    </value>
  </processMetadataValues>
  <processMetadataValues>
    <name>CanvasMode</name>
    <value>
      <stringValue>AUTO_LAYOUT_CANVAS</stringValue>
    </value>
  </processMetadataValues>
  <processMetadataValues>
    <name>OriginBuilderType</name>
    <value>
      <stringValue>LightningFlowBuilder</stringValue>
    </value>
  </processMetadataValues>
  <processType>AutoLaunchedFlow</processType>
  <recordUpdates>
    <name>Update_Invoice</name>
    <label>Update Invoice</label>
    <locationX>420</locationX>
    <locationY>560</locationY>
    <inputReference>$Record</inputReference>
  </recordUpdates>
  <start>
    <locationX>420</locationX>
    <locationY>140</locationY>
    <connector>
      <targetReference>Amount_Greater_Than_1000</targetReference>
    </connector>
    <doesRequireRecordChangedToMeetCriteria>false</doesRequireRecordChangedToMeetCriteria>
    <filterLogic>and</filterLogic>
    <filters>
      <field>Id</field>
      <operator>IsNull</operator>
      <value>
        <booleanValue>false</booleanValue>
      </value>
    </filters>
    <object>Invoice__c</object>
    <recordTriggerType>Create</recordTriggerType>
    <triggerType>RecordAfterSave</triggerType>
  </start>
  <status>Active</status>
</Flow>
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

<!-- EXPANDED -->
#### Realistic deployable object XML (`objects/Invoice__c.object`)

The following example includes an `AutoNumber` name field and 6+ inline field definitions: Text, Currency, Picklist, Date, Lookup, and Checkbox.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <allowInChatterGroups>false</allowInChatterGroups>
  <deploymentStatus>Deployed</deploymentStatus>
  <enableActivities>true</enableActivities>
  <enableBulkApi>true</enableBulkApi>
  <enableFeeds>false</enableFeeds>
  <enableHistory>true</enableHistory>
  <enableReports>true</enableReports>
  <enableSearch>true</enableSearch>
  <externalSharingModel>Private</externalSharingModel>
  <label>Invoice</label>
  <nameField>
    <displayFormat>INV-{000000}</displayFormat>
    <label>Invoice Number</label>
    <type>AutoNumber</type>
  </nameField>
  <pluralLabel>Invoices</pluralLabel>
  <sharingModel>ReadWrite</sharingModel>
  <startsWith>Consonant</startsWith>

  <fields>
    <fullName>Customer_Name__c</fullName>
    <label>Customer Name</label>
    <length>255</length>
    <required>true</required>
    <trackHistory>true</trackHistory>
    <type>Text</type>
  </fields>

  <fields>
    <fullName>Amount__c</fullName>
    <label>Amount</label>
    <precision>16</precision>
    <scale>2</scale>
    <required>true</required>
    <trackHistory>true</trackHistory>
    <type>Currency</type>
  </fields>

  <fields>
    <fullName>Status__c</fullName>
    <label>Status</label>
    <required>true</required>
    <trackHistory>true</trackHistory>
    <type>Picklist</type>
    <valueSet>
      <restricted>true</restricted>
      <valueSetDefinition>
        <sorted>false</sorted>
        <value>
          <fullName>Draft</fullName>
          <default>true</default>
          <label>Draft</label>
        </value>
        <value>
          <fullName>Sent</fullName>
          <default>false</default>
          <label>Sent</label>
        </value>
        <value>
          <fullName>Paid</fullName>
          <default>false</default>
          <label>Paid</label>
        </value>
      </valueSetDefinition>
    </valueSet>
  </fields>

  <fields>
    <fullName>Invoice_Date__c</fullName>
    <label>Invoice Date</label>
    <required>true</required>
    <trackHistory>true</trackHistory>
    <type>Date</type>
  </fields>

  <fields>
    <fullName>Account__c</fullName>
    <deleteConstraint>SetNull</deleteConstraint>
    <label>Account</label>
    <referenceTo>Account</referenceTo>
    <relationshipLabel>Invoices</relationshipLabel>
    <relationshipName>Invoices</relationshipName>
    <required>false</required>
    <trackHistory>true</trackHistory>
    <type>Lookup</type>
  </fields>

  <fields>
    <fullName>Is_Overdue__c</fullName>
    <defaultValue>false</defaultValue>
    <label>Is Overdue</label>
    <trackHistory>true</trackHistory>
    <type>Checkbox</type>
  </fields>

  <fields>
    <fullName>Due_Date__c</fullName>
    <label>Due Date</label>
    <required>false</required>
    <trackHistory>true</trackHistory>
    <type>Date</type>
  </fields>
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

<!-- EXPANDED -->
### Flow Deploy Artifact (Metadata API)

Deploy path for flow metadata files:
- `flows/{FlowApiName}.flow-meta.xml`

Package entry:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Invoice_Record_Triggered_Automation</members>
    <name>Flow</name>
  </types>
  <version>{api_version_number_only}</version>
</Package>
```

Flow XML example is included in Section 3.8 (`flows/Invoice_Record_Triggered_Automation.flow-meta.xml`) and is deployable in a Metadata API ZIP package.

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

<!-- EXPANDED -->
### Published Daily API Entitlement Baselines and Formula

The limits documentation and edition tables publish daily API request entitlements using a baseline-plus-license model for paid editions.

Formula form:

`daily_api_limit = base_org_entitlement + (number_of_licenses × per_license_amount)`

Published baseline values:

| Edition | Base Org Entitlement | Per-License Amount | Example Formula |
|---|---:|---:|---|
| Developer Edition | 15,000 requests / 24 hours | N/A | Fixed at 15,000 |
| Enterprise Edition | 100,000 requests / 24 hours | 1,000 per applicable user license | `100000 + (enterprise_user_licenses * 1000)` |
| Unlimited Edition | 100,000 requests / 24 hours | 5,000 per applicable user license | `100000 + (unlimited_user_licenses * 5000)` |

Notes on entitlement interpretation:
- Daily API limits are evaluated on a rolling 24-hour window.
- Purchased add-ons and contract-specific terms can increase effective entitlement.
- API consumption is shared across all API surfaces that count against org request limits.

<!-- EXPANDED -->
### `Sforce-Limit-Info` Header: Exact Format and Parsing

Header format:

`Sforce-Limit-Info: api-usage=1234/100000`

Header fields:
- `api-usage` current/maximum
  - current requests consumed in the rolling 24-hour window
  - maximum allowed requests in that same window

Code-agnostic parsing example:

1. Read response header `Sforce-Limit-Info`.
2. Split on `=`; keep right side (`1234/100000`).
3. Split on `/`.
4. Parse left value as `current = 1234`.
5. Parse right value as `max = 100000`.
6. Compute utilization: `current / max`.

Where it appears:
- REST API responses include this header for API usage reporting.
- It can be used on every response where present to maintain a local rolling usage counter.

When approaching limit:
- Apply request throttling before hard failures.
- Reduce batch size and request concurrency.
- Re-check `Sforce-Limit-Info` after backoff intervals before issuing additional calls.

<!-- EXPANDED -->
### Concurrent Metadata Deploy Processing and Queue Behavior

Salesforce Metadata deploy processing allows only one actively executing deployment per org at a time.

Behavior for additional deploy submissions:
- If a deployment is already executing, a subsequent deploy request is typically accepted into queue (`Queued` / `Pending` state).
- If queue/concurrency protections are exceeded, additional requests can be rejected.

Representative queue-accepted response (REST Metadata API):

```json
{
  "id": "0Afxx0000004ABCHA2",
  "state": "Queued"
}
```

Representative rejection shape (REST):

```json
[
  {
    "message": "A metadata deployment is already in progress.",
    "errorCode": "CONCURRENT_METADATA_OPERATION"
  }
]
```

Representative rejection shape (SOAP fault):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>sf:CONCURRENT_METADATA_OPERATION</faultcode>
      <faultstring>A metadata operation is already in progress.</faultstring>
      <detail>
        <ApiFault xmlns="http://soap.sforce.com/2006/04/metadata">
          <exceptionCode>CONCURRENT_METADATA_OPERATION</exceptionCode>
          <exceptionMessage>A metadata operation is already in progress.</exceptionMessage>
        </ApiFault>
      </detail>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
```

<!-- EXPANDED -->
### `REQUEST_LIMIT_EXCEEDED`: Response Shapes, Status Codes, and Retry Behavior

REST error response:

**HTTP status:** `403 Forbidden`

```json
[
  {
    "message": "TotalRequests Limit exceeded.",
    "errorCode": "REQUEST_LIMIT_EXCEEDED"
  }
]
```

SOAP error response:

**HTTP status:** `500` (SOAP Fault) or API gateway-translated failure depending on client stack

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>sf:REQUEST_LIMIT_EXCEEDED</faultcode>
      <faultstring>TotalRequests Limit exceeded.</faultstring>
      <detail>
        <ApiFault xmlns="urn:fault.partner.soap.sforce.com">
          <exceptionCode>REQUEST_LIMIT_EXCEEDED</exceptionCode>
          <exceptionMessage>TotalRequests Limit exceeded.</exceptionMessage>
        </ApiFault>
      </detail>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
```

Retry pattern (rolling 24-hour window):
1. On limit error, pause requests with exponential backoff intervals.
2. On each retry cycle, inspect `Sforce-Limit-Info` for current/max.
3. Resume traffic only when utilization is back below the rejection threshold.
4. Continue smoothing request rate because the limit is rolling, not a fixed midnight reset.

---

## 10) Gotchas and Edge Cases

### Field Dependencies That Block Deletion

- Fields referenced by formulas, validation rules, flows/processes, reports, list views, layouts, and Apex can block deletion.
- Resolve all references before DELETE/destructive deploy.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Tooling query for field and owning object:
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName,TableEnumOrId+FROM+CustomField+WHERE+DeveloperName='Amount'`
- Dependency graph query (where available):
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+MetadataComponentId,RefMetadataComponentId,MetadataComponentName,RefMetadataComponentName+FROM+MetadataComponentDependency+WHERE+RefMetadataComponentName='Invoice__c.Amount__c'`
- Metadata retrieve to inspect flow/layout/validation references before destructive deploy.

**Error**
- Common REST delete/deploy failure shapes:

```json
[
  {
    "message": "Cannot delete custom field Invoice__c.Amount__c because it is referenced by other metadata.",
    "errorCode": "DEPENDENCY_EXISTS"
  }
]
```

```json
[
  {
    "message": "Cannot complete this operation. Referenced object has dependent metadata.",
    "errorCode": "FIELD_INTEGRITY_EXCEPTION"
  }
]
```

**Resolution**
1. Remove references (Flow elements, formulas, reports, layout fields, validation rules, automation).
2. Re-run dependency query/retrieve verification.
3. Retry `DELETE` (Tooling) or destructive deploy.
4. If parent object deletion still fails, delete remaining child metadata first.

### Required Fields on Standard Objects

- Record creation and related metadata operations can fail if object-required fields/business rules are not satisfied.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Describe endpoint:
  - `GET {instance_url}/services/data/{api_version}/sobjects/Account/describe`
- Inspect each field where:
  - `nillable = false`
  - `defaultedOnCreate = false`
  - no default value provided

**Error**

```json
[
  {
    "message": "Required fields are missing: [Name]",
    "errorCode": "REQUIRED_FIELD_MISSING",
    "fields": [
      "Name"
    ]
  }
]
```

**Resolution**
1. Build record payloads from describe metadata.
2. Populate all required fields before insert/upsert.
3. Revalidate after each schema change (new required fields can be introduced).

### Custom Object Naming Rules

- Custom object API names use `__c` suffix.
- Naming has character and uniqueness constraints.
- Reserved words/system conflicts can block creation.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Validate API name locally against Salesforce-compatible pattern before submit:
  - `^[A-Za-z][A-Za-z0-9_]{0,39}__c$`
- Query for collisions:
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName+FROM+CustomObject+WHERE+DeveloperName='Invoice'`

**Error**

```json
[
  {
    "message": "The field name provided, Invoice-Object__c, is not valid for a custom object.",
    "errorCode": "INVALID_FIELD"
  }
]
```

```json
[
  {
    "message": "An object with developer name Invoice already exists.",
    "errorCode": "DUPLICATE_DEVELOPER_NAME"
  }
]
```

**Resolution**
1. Normalize names to alphanumeric + underscore only.
2. Ensure uniqueness at object and namespace scope.
3. Avoid reserved/system names and conflicts with standard objects.

### Managed vs Unmanaged Package Context

- Managed package metadata can have immutability or subscriber restrictions.
- Namespace qualification can change member names in metadata manifests.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Tooling query with manageability state:
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName,NamespacePrefix,ManageableState+FROM+CustomField+WHERE+TableEnumOrId='Invoice__c'`
- `ManageableState` values identify unmanaged vs managed/installed behavior.

**Error**

```json
[
  {
    "message": "Cannot modify managed object: Invoice__c.Amount__c",
    "errorCode": "CANNOT_MODIFY_MANAGED_OBJECT"
  }
]
```

```json
[
  {
    "message": "Cannot delete managed component in a subscriber org.",
    "errorCode": "CANNOT_DELETE_MANAGED_OBJECT"
  }
]
```

**Resolution**
1. For managed metadata, apply changes in package source org and release a package version.
2. In subscriber orgs, modify only subscriber-editable settings.
3. For non-editable managed components, avoid mutate/delete attempts.

### Namespace Prefix Behavior

- API names may appear as `{namespace}__Component__c` in managed contexts.
- Manifest members must match namespaced full names where applicable.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Query with namespace:
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+DeveloperName,NamespacePrefix+FROM+CustomObject+WHERE+DeveloperName='Invoice'`
- Validate package member full names include namespace when present.

**Error**

```json
[
  {
    "message": "No such metadata member ns__Invoice__c",
    "errorCode": "INVALID_CROSS_REFERENCE_KEY"
  }
]
```

**Resolution**
1. Build member names using `NamespacePrefix + '__' + DeveloperName`.
2. Keep namespaced and non-namespaced identifiers separate in deployment manifests.

### Sandbox vs Production Behavior Differences

- Validation/test enforcement and available metadata may differ by org type and release state.
- Deployment/test requirements differ by target environment and settings.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Determine org type:
  - `GET {instance_url}/services/data/{api_version}/query?q=SELECT+Id,IsSandbox,InstanceName+FROM+Organization`

**Error**
- Production deploy with insufficient tests can fail with deployment test validation errors:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<checkDeployStatusResponse xmlns="http://soap.sforce.com/2006/04/metadata">
  <result>
    <status>Failed</status>
    <success>false</success>
    <details>
      <runTestResult>
        <numFailures>1</numFailures>
      </runTestResult>
      <componentFailures>
        <problemType>Error</problemType>
        <problem>Deployment failed because tests did not pass required thresholds.</problem>
      </componentFailures>
    </details>
  </result>
</checkDeployStatusResponse>
```

**Resolution**
1. Select deploy test level based on environment policy:
   - `NoTestRun`
   - `RunLocalTests`
   - `RunAllTestsInOrg`
   - `RunSpecifiedTests`
2. Use validation-only (`checkOnly=true`) before commit deploy.
3. Poll deployment result and parse test failure details before retry.

### Metadata Deploy Order and Dependencies

- Component dependencies in one deploy package can require specific pre-existing metadata or packaging order.
- Destructive pre/post manifests are used to control order-sensitive deletes.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Use deploy validation (`checkOnly=true`) and parse `componentFailures`.
- Query dependency links (where available) before deploy:
  - `MetadataComponentDependency` Tooling query.

**Error**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<checkDeployStatusResponse xmlns="http://soap.sforce.com/2006/04/metadata">
  <result>
    <status>Failed</status>
    <success>false</success>
    <details>
      <componentFailures>
        <componentType>Layout</componentType>
        <fullName>Invoice__c-Invoice Layout</fullName>
        <problemType>Error</problemType>
        <problem>MISSING_DEPENDENT_METADATA: In field: field - no CustomField named Invoice__c.Status__c found</problem>
      </componentFailures>
    </details>
  </result>
</checkDeployStatusResponse>
```

**Resolution**
1. Include prerequisites in same deploy package when possible.
2. Ensure manifests declare dependent members.
3. Use `destructiveChangesPre.xml` for required pre-delete ordering.
4. Split into phased deploys when dependency graph cannot be resolved in one transaction.

### Tooling vs Metadata Field Type Name Differences

- Same conceptual field type can be represented with different property naming patterns across Tooling JSON and Metadata XML.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Compare Tooling `CustomField.Metadata.type` values with Metadata API `<type>` values in retrieved field XML.
- Retrieve both representations for a known field before generating mutations.

**Error**

```json
[
  {
    "message": "Cannot deserialize instance of complexvalue from VALUE_STRING value MasterDetail",
    "errorCode": "JSON_PARSER_ERROR"
  }
]
```

**Resolution**
1. Normalize field type mappings between Tooling JSON and Metadata XML.
2. Validate payload schema by metadata channel before submit.

### Compound Fields

- Compound standard fields (for example Address/Name structures) have component-field behavior that affects query/update/delete semantics.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Query field definitions for compound context:
  - `GET {instance_url}/services/data/{api_version}/query?q=SELECT+QualifiedApiName,DataType,IsCompound,CompoundFieldName+FROM+FieldDefinition+WHERE+EntityDefinition.QualifiedApiName='Account'`

**Error**

```json
[
  {
    "message": "Cannot directly update compound field: BillingAddress",
    "errorCode": "INVALID_FIELD_FOR_INSERT_UPDATE",
    "fields": [
      "BillingAddress"
    ]
  }
]
```

**Resolution**
1. Use component fields (`BillingStreet`, `BillingCity`, etc.) for DML.
2. Treat compound parent fields as read/aggregate representations in many operations.

### Status Values and Transitions

- Async deploy/retrieve status transitions include queued/in-progress/terminal states.
- Flow activation/version status changes involve definition/version relationships and may require explicit activation pointers.

<!-- EXPANDED -->
#### Detection / Error / Resolution

**Detection**
- Metadata deploy status polling:
  - `GET {instance_url}/services/data/{api_version}/metadata/deployRequest/{deploy_id}`
- Flow definition query:
  - `GET {instance_url}/services/data/{api_version}/tooling/query?q=SELECT+Id,DeveloperName,ActiveVersionId,LatestVersionId+FROM+FlowDefinition+WHERE+DeveloperName='Invoice_Record_Triggered_Automation'`

**Error**

```json
[
  {
    "message": "You can't activate this flow version because it contains validation errors.",
    "errorCode": "INVALID_STATUS"
  }
]
```

**Resolution**
1. Ensure target flow version is valid and deployed.
2. Update definition activation pointer only after successful version deploy.
3. Re-query to verify `ActiveVersionId` transition completed.

<!-- EXPANDED -->
### Additional Gotcha: Global Value Set Dependencies

**Detection**
- Check whether picklist field references a global value set in field metadata retrieve.
- Query value set references before deleting picklist fields/value sets.

**Error**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<checkDeployStatusResponse xmlns="http://soap.sforce.com/2006/04/metadata">
  <result>
    <status>Failed</status>
    <success>false</success>
    <details>
      <componentFailures>
        <componentType>GlobalValueSet</componentType>
        <problemType>Error</problemType>
        <problem>Cannot delete GlobalValueSet because it is referenced by one or more custom fields.</problem>
      </componentFailures>
    </details>
  </result>
</checkDeployStatusResponse>
```

**Resolution**
1. Move dependent fields off the global value set first.
2. Deploy updated field metadata.
3. Retry destructive deletion.

---

<!-- EXPANDED -->
## 11) Composite API (`composite/sobjects`)

Composite sObject collections support batch create/update/upsert for records of the same sObject type with per-record result arrays.

Base endpoint:
- `{instance_url}/services/data/{api_version}/composite/sobjects`

Standard headers:
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

### Batch Create

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/composite/sobjects`

**Request body**
```json
{
  "allOrNone": false,
  "records": [
    {
      "attributes": {
        "type": "Invoice__c"
      },
      "Customer_Name__c": "Acme Corp",
      "Amount__c": 1250.5,
      "Status__c": "Draft",
      "Invoice_Date__c": "2026-02-19"
    },
    {
      "attributes": {
        "type": "Invoice__c"
      },
      "Customer_Name__c": "Global Media",
      "Amount__c": 950.0,
      "Status__c": "Draft",
      "Invoice_Date__c": "2026-02-19"
    }
  ]
}
```

**Response body**
```json
[
  {
    "id": "a0Bxx0000008AAA",
    "success": true,
    "errors": []
  },
  {
    "id": "a0Bxx0000008AAB",
    "success": true,
    "errors": []
  }
]
```

### Batch Update

**Method:** `PATCH`  
**URL:** `{instance_url}/services/data/{api_version}/composite/sobjects`

**Request body**
```json
{
  "allOrNone": false,
  "records": [
    {
      "attributes": {
        "type": "Invoice__c"
      },
      "Id": "a0Bxx0000008AAA",
      "Status__c": "Sent",
      "Is_Overdue__c": false
    },
    {
      "attributes": {
        "type": "Invoice__c"
      },
      "Id": "a0Bxx0000008AAB",
      "Status__c": "Paid",
      "Is_Overdue__c": false
    }
  ]
}
```

**Response body**
```json
[
  {
    "id": "a0Bxx0000008AAA",
    "success": true,
    "errors": []
  },
  {
    "id": "a0Bxx0000008AAB",
    "success": true,
    "errors": []
  }
]
```

### Batch Upsert by External ID

**Method:** `PATCH`  
**URL:** `{instance_url}/services/data/{api_version}/composite/sobjects/Invoice__c/External_Id__c`

**Request body**
```json
{
  "allOrNone": false,
  "records": [
    {
      "attributes": {
        "type": "Invoice__c"
      },
      "External_Id__c": "INV-10001",
      "Customer_Name__c": "Acme Corp",
      "Amount__c": 1250.5,
      "Status__c": "Sent",
      "Invoice_Date__c": "2026-02-19"
    },
    {
      "attributes": {
        "type": "Invoice__c"
      },
      "External_Id__c": "INV-10002",
      "Customer_Name__c": "Global Media",
      "Amount__c": 950.0,
      "Status__c": "Draft",
      "Invoice_Date__c": "2026-02-19"
    }
  ]
}
```

**Response body**
```json
[
  {
    "id": "a0Bxx0000008AAA",
    "success": true,
    "errors": []
  },
  {
    "id": "a0Bxx0000008AAC",
    "success": true,
    "errors": []
  }
]
```

### Partial Success Behavior

When `allOrNone=true`:
- Any single record error causes rollback of all records in the request.

Representative response (`allOrNone=true`, one row invalid):

```json
[
  {
    "id": null,
    "success": false,
    "errors": [
      {
        "statusCode": "REQUIRED_FIELD_MISSING",
        "message": "Required fields are missing: [Customer_Name__c]",
        "fields": [
          "Customer_Name__c"
        ]
      }
    ]
  },
  {
    "id": null,
    "success": false,
    "errors": [
      {
        "statusCode": "ALL_OR_NONE_OPERATION_ROLLED_BACK",
        "message": "Record rolled back because allOrNone is true and at least one record failed.",
        "fields": []
      }
    ]
  }
]
```

When `allOrNone=false`:
- Each record succeeds or fails independently.

Representative response (`allOrNone=false`, mixed outcome):

```json
[
  {
    "id": "a0Bxx0000008AAD",
    "success": true,
    "errors": []
  },
  {
    "id": null,
    "success": false,
    "errors": [
      {
        "statusCode": "REQUIRED_FIELD_MISSING",
        "message": "Required fields are missing: [Customer_Name__c]",
        "fields": [
          "Customer_Name__c"
        ]
      }
    ]
  }
]
```

### Limits and Chunking

- Maximum records per `composite/sobjects` request: `200`.
- For larger batches, split input into chunks of 200 records or fewer.
- Preserve `allOrNone` intent per chunk to maintain predictable rollback behavior.

---

<!-- EXPANDED -->
## 12) Named Credentials

Named Credentials store external endpoint/auth configuration for callouts used by Flow, Apex, and related platform features.

Metadata type:
- `NamedCredential`

Deploy path:
- `namedCredentials/{Name}.namedCredential-meta.xml`

### Metadata XML (Named Principal + OAuth2)

`namedCredentials/External_Billing_API.namedCredential-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<NamedCredential xmlns="http://soap.sforce.com/2006/04/metadata">
  <allowMergeFieldsInBody>false</allowMergeFieldsInBody>
  <allowMergeFieldsInHeader>false</allowMergeFieldsInHeader>
  <authProvider>External_Billing_AuthProvider</authProvider>
  <authenticationProtocol>OAuth 2.0</authenticationProtocol>
  <calloutStatus>Enabled</calloutStatus>
  <generateAuthorizationHeader>true</generateAuthorizationHeader>
  <label>External Billing API</label>
  <namedCredentialType>NamedPrincipal</namedCredentialType>
  <oauthTokenEndpointUrl>https://api.example.com/oauth/token</oauthTokenEndpointUrl>
  <principalType>NamedUser</principalType>
  <protocol>HTTPS</protocol>
  <url>https://api.example.com</url>
  <username>integration.user@example.com</username>
</NamedCredential>
```

### Metadata XML (Per-User + Password Authentication)

`namedCredentials/External_Service_Per_User.namedCredential-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<NamedCredential xmlns="http://soap.sforce.com/2006/04/metadata">
  <allowMergeFieldsInBody>false</allowMergeFieldsInBody>
  <allowMergeFieldsInHeader>true</allowMergeFieldsInHeader>
  <authenticationProtocol>Password</authenticationProtocol>
  <calloutStatus>Enabled</calloutStatus>
  <generateAuthorizationHeader>true</generateAuthorizationHeader>
  <label>External Service Per User</label>
  <namedCredentialType>PerUser</namedCredentialType>
  <password>{encrypted_or_secret_placeholder}</password>
  <protocol>HTTPS</protocol>
  <url>https://service.example.com</url>
  <username>{per_user_username_reference}</username>
</NamedCredential>
```

### Flow Reference Pattern

Flow HTTP callout actions reference the named credential endpoint by its logical credential binding.

Representative flow action-call metadata fragment:

```xml
<actionCalls>
  <name>Call_External_Billing_API</name>
  <label>Call External Billing API</label>
  <actionName>flow.HttpCallout</actionName>
  <actionType>apex</actionType>
  <inputParameters>
    <name>namedCredential</name>
    <value>
      <stringValue>External_Billing_API</stringValue>
    </value>
  </inputParameters>
  <inputParameters>
    <name>method</name>
    <value>
      <stringValue>POST</stringValue>
    </value>
  </inputParameters>
  <inputParameters>
    <name>path</name>
    <value>
      <stringValue>/v1/invoices/sync</stringValue>
    </value>
  </inputParameters>
</actionCalls>
```

### `package.xml` Entry for Named Credentials

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>External_Billing_API</members>
    <members>External_Service_Per_User</members>
    <name>NamedCredential</name>
  </types>
  <version>{api_version_number_only}</version>
</Package>
```

<!-- EXPANDED -->
### ExternalCredential (Newer Model)

`ExternalCredential` is the newer metadata model that stores authentication configuration separately from endpoint URL configuration.

Relationship model:
- `ExternalCredential` contains authentication and principal configuration.
- `NamedCredential` contains endpoint URL/protocol and references an external credential for auth.

This model supports newer auth patterns and is increasingly used in orgs on newer API versions/configurations. Legacy named-credential-only patterns still exist in many orgs.

#### Metadata XML example (`externalCredentials/External_Billing_Auth.externalCredential-meta.xml`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ExternalCredential xmlns="http://soap.sforce.com/2006/04/metadata">
  <authenticationProtocol>OAuth2ClientCredentials</authenticationProtocol>
  <label>External Billing Auth</label>
  <externalCredentialParameters>
    <parameterName>token_url</parameterName>
    <parameterType>AuthProviderUrl</parameterType>
    <parameterValue>https://api.example.com/oauth/token</parameterValue>
  </externalCredentialParameters>
  <externalCredentialParameters>
    <parameterName>scope</parameterName>
    <parameterType>Scope</parameterType>
    <parameterValue>billing.write billing.read</parameterValue>
  </externalCredentialParameters>
  <principalType>NamedPrincipal</principalType>
  <principals>
    <principalName>BillingClientCredentials</principalName>
    <principalType>NamedPrincipal</principalType>
    <sequenceNumber>1</sequenceNumber>
  </principals>
</ExternalCredential>
```

#### API key style example (`externalCredentials/External_API_Key_Auth.externalCredential-meta.xml`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ExternalCredential xmlns="http://soap.sforce.com/2006/04/metadata">
  <authenticationProtocol>Custom</authenticationProtocol>
  <label>External API Key Auth</label>
  <externalCredentialParameters>
    <parameterName>header_name</parameterName>
    <parameterType>AuthParameter</parameterType>
    <parameterValue>x-api-key</parameterValue>
  </externalCredentialParameters>
  <principalType>NamedPrincipal</principalType>
  <principals>
    <principalName>ApiKeyPrincipal</principalName>
    <principalType>NamedPrincipal</principalType>
    <sequenceNumber>1</sequenceNumber>
  </principals>
</ExternalCredential>
```

#### Named Credential reference pattern

Representative metadata fragment showing linkage from `NamedCredential` to `ExternalCredential`:

```xml
<namedCredentialParameters>
  <externalCredential>External_Billing_Auth</externalCredential>
  <parameterName>ExternalCredential</parameterName>
  <parameterType>Authentication</parameterType>
</namedCredentialParameters>
```

#### Deployment via Metadata API

`package.xml` entries:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>External_Billing_Auth</members>
    <members>External_API_Key_Auth</members>
    <name>ExternalCredential</name>
  </types>
  <types>
    <members>External_Billing_API</members>
    <name>NamedCredential</name>
  </types>
  <version>{api_version_number_only}</version>
</Package>
```

Version/configuration note:
- Metadata shape and required child nodes can vary by API version and org credential architecture (legacy named credential model versus external credential model).

---

<!-- EXPANDED -->
## 13) Bulk API 2.0 (Ingest)

Bulk API 2.0 ingest is the asynchronous CSV-based interface for high-volume record operations (`insert`, `update`, `upsert`, `delete`, `hardDelete` where enabled).

Rule-of-thumb workload split:
- Composite API: small synchronous batches, typically under 200 records/request.
- Bulk API 2.0 ingest: asynchronous processing for 200+ records and strongly preferred for 1,000+ record operations.

Base endpoint:
- `{instance_url}/services/data/{api_version}/jobs/ingest`

Common headers:
- `Authorization: Bearer {access_token}`
- `Accept: application/json`

CSV upload header:
- `Content-Type: text/csv`

JSON control request header:
- `Content-Type: application/json`

### Decision Matrix: Composite API vs Bulk API 2.0

| Criteria | Composite API | Bulk API 2.0 |
|---|---|---|
| Record count sweet spot | 1-200 per call | 200-150,000,000 |
| Format | JSON | CSV |
| Execution | Synchronous | Asynchronous |
| Per-record errors | Inline in response array | Separate CSV download |
| allOrNone support | Yes | No (best-effort only) |
| Use case | Real-time operations, small batches | Daily loads, backfills, migrations |

### Ingest Lifecycle (Upsert Example: 5,000 `Job_Posting__c` by `Posting_URL__c`)

#### Step 1: Create Job

**Method:** `POST`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "operation": "upsert",
  "object": "Job_Posting__c",
  "externalIdFieldName": "Posting_URL__c",
  "contentType": "CSV",
  "lineEnding": "LF",
  "columnDelimiter": "COMMA"
}
```

**Response body**
```json
{
  "id": "750xx00000000AAAQ",
  "operation": "upsert",
  "object": "Job_Posting__c",
  "createdById": "005xx0000001ABC",
  "createdDate": "2026-02-19T18:12:14.000+0000",
  "systemModstamp": "2026-02-19T18:12:14.000+0000",
  "state": "Open",
  "externalIdFieldName": "Posting_URL__c",
  "concurrencyMode": "Parallel",
  "contentType": "CSV",
  "apiVersion": 61.0,
  "lineEnding": "LF",
  "columnDelimiter": "COMMA"
}
```

#### Step 2: Upload CSV Data

**Method:** `PUT`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest/750xx00000000AAAQ/batches`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: text/csv`
- `Accept: application/json`

**Request body (CSV)**
```csv
Posting_URL__c,Title__c,Company__c,City__c,State__c,Country__c,Posted_Date__c,Is_Active__c
https://jobs.example.com/postings/1001,Senior AE,Acme Inc,Chicago,IL,US,2026-02-19,true
https://jobs.example.com/postings/1002,TAM,Acme Inc,Austin,TX,US,2026-02-19,true
https://jobs.example.com/postings/1003,Recruiter,Global Media,New York,NY,US,2026-02-19,true
https://jobs.example.com/postings/1004,Account Manager,Global Media,Seattle,WA,US,2026-02-19,true
https://jobs.example.com/postings/1005,SDR,Blue Orbit,Denver,CO,US,2026-02-19,true
```

**Response body**
```json
{
  "id": "750xx00000000AAAQ",
  "state": "Open"
}
```

CSV requirements:
- Header row must use Salesforce field API names.
- UTF-8 CSV payload, delimiter and line ending must match job config.
- Maximum upload payload per ingest upload: 150 MB.
- For datasets larger than one payload, split into multiple jobs (each with its own upload/close cycle).

#### Step 3: Close Job (Start Processing)

**Method:** `PATCH`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest/750xx00000000AAAQ`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**
```json
{
  "state": "UploadComplete"
}
```

**Response body**
```json
{
  "id": "750xx00000000AAAQ",
  "operation": "upsert",
  "object": "Job_Posting__c",
  "state": "UploadComplete"
}
```

#### Step 4: Poll Job Status

**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest/750xx00000000AAAQ`

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
  "id": "750xx00000000AAAQ",
  "operation": "upsert",
  "object": "Job_Posting__c",
  "state": "JobComplete",
  "createdDate": "2026-02-19T18:12:14.000+0000",
  "systemModstamp": "2026-02-19T18:14:01.000+0000",
  "numberRecordsProcessed": 5000,
  "numberRecordsFailed": 37,
  "retries": 0,
  "totalProcessingTime": 8543,
  "apiActiveProcessingTime": 7210,
  "apexProcessingTime": 1333
}
```

Job state values:
- `Open`
- `UploadComplete`
- `InProgress`
- `JobComplete`
- `Failed`
- `Aborted`

#### Step 5: Download Successful Results

**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest/750xx00000000AAAQ/successfulResults`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: text/csv`

**Request body**
```json
{}
```

**Response body (CSV)**
```csv
sf__Id,sf__Created,Posting_URL__c,Title__c,Company__c,City__c,State__c,Country__c,Posted_Date__c,Is_Active__c
a1Bxx0000001AAA,false,https://jobs.example.com/postings/1001,Senior AE,Acme Inc,Chicago,IL,US,2026-02-19,true
a1Bxx0000001AAB,true,https://jobs.example.com/postings/1002,TAM,Acme Inc,Austin,TX,US,2026-02-19,true
```

Returned success columns typically include:
- `sf__Id`
- `sf__Created`
- Original submitted CSV columns

#### Step 6: Download Failed Results

**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest/750xx00000000AAAQ/failedResults`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: text/csv`

**Request body**
```json
{}
```

**Response body (CSV)**
```csv
sf__Id,sf__Error,Posting_URL__c,Title__c,Company__c,City__c,State__c,Country__c,Posted_Date__c,Is_Active__c
,Required fields are missing: [Title__c],https://jobs.example.com/postings/3211,,Acme Inc,Chicago,IL,US,2026-02-19,true
,Invalid date: 2026/02/19,https://jobs.example.com/postings/4211,Recruiter,Global Media,New York,NY,US,2026/02/19,true
```

Returned failure columns typically include:
- `sf__Id` (blank on many failed inserts/upserts)
- `sf__Error`
- Original submitted CSV columns

#### Step 7: Download Unprocessed Records

**Method:** `GET`  
**URL:** `{instance_url}/services/data/{api_version}/jobs/ingest/750xx00000000AAAQ/unprocessedrecords`

**Required headers**
- `Authorization: Bearer {access_token}`
- `Accept: text/csv`

**Request body**
```json
{}
```

**Response body (CSV)**
```csv
Posting_URL__c,Title__c,Company__c,City__c,State__c,Country__c,Posted_Date__c,Is_Active__c
https://jobs.example.com/postings/9981,Senior CSM,Acme Inc,Chicago,IL,US,2026-02-19,true
```

`unprocessedrecords` contains rows that were not attempted (for example job abort/transition timing cases).

### Limits and Quotas

- Ingest upload payload size: maximum 150 MB per upload.
- Maximum active/open Bulk API 2.0 ingest jobs per org: 15.
- Bulk API 2.0 internal processing chunks are in 10,000-record units.
- Bulk API usage contributes to org API entitlement; bulk processing consumption is measured in record chunks/batches by Salesforce limits accounting.
- For very large loads, split into multiple jobs and process asynchronously.

### Partial Success and Error Handling

Bulk API 2.0 ingest is best-effort; there is no all-or-none transactional mode equivalent to Composite `allOrNone`.

Operational handling:
1. Poll job until terminal state (`JobComplete`, `Failed`, or `Aborted`).
2. Always download both `successfulResults` and `failedResults`.
3. Retry only failed rows after fixing data errors.
4. Use `unprocessedrecords` to recover rows that were never attempted.

### CSV Formatting Gotchas

- Quote values containing commas, quotes, or line breaks using CSV escaping rules.
- Use empty field value to represent null when allowed by field metadata and operation semantics.
- Date fields should use `YYYY-MM-DD`.
- Datetime fields should use ISO-8601 UTC form (for example `2026-02-19T18:12:14.000Z`).
- Ensure header names exactly match field API names.

### Query Jobs (`/jobs/query`) for Completeness

Bulk API 2.0 also supports asynchronous query jobs at:
- `{instance_url}/services/data/{api_version}/jobs/query`

This section focuses on ingest operations; query lifecycle follows create/poll/result-download patterns analogous to ingest job orchestration.

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

