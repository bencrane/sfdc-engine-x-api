# Salesforce Analytics Metadata Deploy Reference (Reports + Dashboards)

This document is the implementation reference for deploying Salesforce Reports and Dashboards in `sfdc-engine-x`.

---

## 1) API Positioning

### Deployment Channel

Reports and Dashboards are deployed through the **Metadata API** deploy/retrieve workflow (ZIP + `package.xml`), using:

- REST Metadata API:
  - `POST {instance_url}/services/data/{api_version}/metadata/deployRequest`
  - `GET {instance_url}/services/data/{api_version}/metadata/deployRequest/{deploy_id}`
  - `POST {instance_url}/services/data/{api_version}/metadata/retrieveRequest`
  - `GET {instance_url}/services/data/{api_version}/metadata/retrieveRequest/{retrieve_id}`
- SOAP Metadata API parity path:
  - `deploy()`, `checkDeployStatus()`, `retrieve()`, `checkRetrieveStatus()`

### Tooling API Limitation (Important)

Tooling API is not the operational deploy channel for `Report`, `Dashboard`, `ReportFolder`, or `DashboardFolder` package deployment. Use Tooling/query APIs only for supplemental discovery or diagnostics; package deployment is Metadata API-driven.

### REST vs SOAP Parity Notes

- REST Metadata API is the preferred transport in `sfdc-engine-x` because request/response handling aligns with existing JSON pipeline patterns.
- SOAP Metadata API remains the canonical parity path for the same asynchronous deploy/retrieve lifecycle and can be used as fallback for edge cases.
- Operational model is identical: submit async job ID, poll status, inspect per-component successes/failures.

---

## 2) Metadata Types + File Layout

### Metadata Types Covered

- `Report`
- `Dashboard`
- `ReportFolder`
- `DashboardFolder`

### Deploy ZIP Layout (Single Package)

```text
package.xml
reports/
  Revenue_Analytics.reportFolder-meta.xml
  Revenue_Analytics/
    Opportunity_Pipeline_by_Stage.report
    Pipeline_Trended_by_Owner.report
dashboards/
  Revenue_Analytics_Dashboards.dashboardFolder-meta.xml
  Revenue_Analytics_Dashboards/
    Executive_Pipeline_Overview.dashboard
```

### Folder Metadata Files

Include folder metadata files when creating/managing folders as part of deployment:

- `reports/{ReportFolderApiName}.reportFolder-meta.xml`
- `dashboards/{DashboardFolderApiName}.dashboardFolder-meta.xml`

Example `reports/Revenue_Analytics.reportFolder-meta.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ReportFolder xmlns="http://soap.sforce.com/2006/04/metadata">
  <!-- UNVERIFIED: Root element for report folder metadata could not be re-confirmed from accessible official page content in this environment; verify against https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_reportfolder.htm -->
  <accessType>Public</accessType>
  <name>Revenue Analytics</name>
</ReportFolder>
```

Example `dashboards/Revenue_Analytics_Dashboards.dashboardFolder-meta.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DashboardFolder xmlns="http://soap.sforce.com/2006/04/metadata">
  <!-- UNVERIFIED: Root element for dashboard folder metadata could not be re-confirmed from accessible official page content in this environment; verify against https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_dashboardfolder.htm -->
  <accessType>Public</accessType>
  <name>Revenue Analytics Dashboards</name>
</DashboardFolder>
```

### `package.xml` Example (All Four Types)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Revenue_Analytics</members>
    <name>ReportFolder</name>
  </types>
  <types>
    <members>Revenue_Analytics/Opportunity_Pipeline_by_Stage</members>
    <members>Revenue_Analytics/Pipeline_Trended_by_Owner</members>
    <name>Report</name>
  </types>
  <types>
    <members>Revenue_Analytics_Dashboards</members>
    <name>DashboardFolder</name>
  </types>
  <types>
    <members>Revenue_Analytics_Dashboards/Executive_Pipeline_Overview</members>
    <name>Dashboard</name>
  </types>
  <version>{api_version_number_only}</version>
</Package>
```

---

## 3) FullName and Folder Semantics

### FullName Rules

- `ReportFolder` member fullName: `{ReportFolderApiName}`
  - Example: `Revenue_Analytics`
- `DashboardFolder` member fullName: `{DashboardFolderApiName}`
  - Example: `Revenue_Analytics_Dashboards`
- `Report` member fullName: `{ReportFolderApiName}/{ReportApiName}`
  - Example: `Revenue_Analytics/Opportunity_Pipeline_by_Stage`
- `Dashboard` member fullName: `{DashboardFolderApiName}/{DashboardApiName}`
  - Example: `Revenue_Analytics_Dashboards/Executive_Pipeline_Overview`

### Intra-Metadata References

Dashboard component `report` references use report fullName format:

- `Revenue_Analytics/Opportunity_Pipeline_by_Stage`
- `Revenue_Analytics/Pipeline_Trended_by_Owner`

### Rename and Portability Implications

- Folder rename changes every child fullName (`Folder/Member`), so dashboard report references can break unless rewritten.
- Report rename also changes fullName and must be propagated to every dashboard component referencing it.
- Cross-org portability is strongest when folder API names are standardized and stable across tenants.
- Recommended: treat folder and report API names as immutable IDs once published; use label/title for human-facing changes.

---

## 4) Dependency Model + Deploy Order

### Dependency Chain

1. Folders (`ReportFolder`, `DashboardFolder`)
2. Reports (`Report`)
3. Dashboards (`Dashboard`) referencing reports

### Recommended Deploy Order

1. Deploy folder metadata
2. Deploy reports
3. Deploy dashboards

Why: dashboards resolve report references at deploy-time/activation-time; missing report members or folders produce component failures even if dashboard XML is syntactically valid.

### Failure Examples

Dashboard references missing report:

```json
{
  "id": "0Afxx0000004ABCGA2",
  "status": "Failed",
  "success": false,
  "details": {
    "componentFailures": [
      {
        "componentType": "Dashboard",
        "fullName": "Revenue_Analytics_Dashboards/Executive_Pipeline_Overview",
        "problemType": "Error",
        "problem": "In field: report - no Report named Revenue_Analytics/Opportunity_Pipeline_by_Stage found"
      }
    ]
  }
}
```

Report target folder missing:

```json
{
  "id": "0Afxx0000004ABCHA2",
  "status": "Failed",
  "success": false,
  "details": {
    "componentFailures": [
      {
        "componentType": "Report",
        "fullName": "Revenue_Analytics/Opportunity_Pipeline_by_Stage",
        "problemType": "Error",
        "problem": "No such folder: Revenue_Analytics"
      }
    ]
  }
}
```

---

## 5) XML Structure Reference

The following examples are internally consistent with the ZIP/package examples above.

### Report XML Example

`reports/Revenue_Analytics/Opportunity_Pipeline_by_Stage.report`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
  <!-- UNVERIFIED: Could not re-confirm from accessible official page content whether <name> is the canonical top-level display-name element for Report metadata; verify against https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_report.htm -->
  <name>Opportunity Pipeline by Stage</name>
  <description>Pipeline grouped by stage for current quarter.</description>
  <format>Summary</format>
  <reportType>Opportunity</reportType>
  <scope>organization</scope>
  <showDetails>true</showDetails>
  <showGrandTotal>true</showGrandTotal>
  <columns>ACCOUNT.NAME</columns>
  <columns>OPPORTUNITY.NAME</columns>
  <columns>OPPORTUNITY.STAGE_NAME</columns>
  <columns>OPPORTUNITY.AMOUNT</columns>
  <columns>OPPORTUNITY.CLOSE_DATE</columns>
  <filter>
    <booleanFilter>1 AND 2</booleanFilter>
    <criteriaItems>
      <column>OPPORTUNITY.CLOSE_DATE</column>
      <operator>equals</operator>
      <value>THIS_QUARTER</value>
    </criteriaItems>
    <criteriaItems>
      <column>OPPORTUNITY.IS_CLOSED</column>
      <operator>equals</operator>
      <value>false</value>
    </criteriaItems>
  </filter>
  <groupingsDown>
    <dateGranularity>None</dateGranularity>
    <field>OPPORTUNITY.STAGE_NAME</field>
    <sortOrder>Asc</sortOrder>
  </groupingsDown>
  <groupingsAcross>
    <dateGranularity>CalendarMonth</dateGranularity>
    <field>OPPORTUNITY.CLOSE_DATE</field>
    <sortOrder>Asc</sortOrder>
  </groupingsAcross>
  <chart>
    <chartType>VerticalBar</chartType>
    <!-- UNVERIFIED: Could not re-confirm from accessible official page content whether report chart summary container is <summary> (current) versus an alternative structure such as <chartSummaries>; verify against https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_report.htm -->
    <summary>
      <axisBinding>y</axisBinding>
      <column>OPPORTUNITY.AMOUNT</column>
      <aggregate>Sum</aggregate>
    </summary>
  </chart>
</Report>
```

### Dashboard XML Example (References Reports)

`dashboards/Revenue_Analytics_Dashboards/Executive_Pipeline_Overview.dashboard`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Dashboard xmlns="http://soap.sforce.com/2006/04/metadata">
  <title>Executive Pipeline Overview</title>
  <dashboardType>SpecifiedUser</dashboardType>
  <runningUser>ops.integration@example.com</runningUser>
  <leftSection>
    <components>
      <title>Pipeline by Stage</title>
      <header>Current Quarter Pipeline</header>
      <componentType>VerticalBar</componentType>
      <report>Revenue_Analytics/Opportunity_Pipeline_by_Stage</report>
      <useReportChart>false</useReportChart>
      <showPercentage>false</showPercentage>
      <showTotal>true</showTotal>
      <valueDataType>Currency</valueDataType>
      <decimalPrecision>0</decimalPrecision>
      <legendPosition>Bottom</legendPosition>
    </components>
  </leftSection>
  <middleSection>
    <components>
      <title>Pipeline Trend by Owner</title>
      <componentType>Line</componentType>
      <report>Revenue_Analytics/Pipeline_Trended_by_Owner</report>
      <useReportChart>false</useReportChart>
      <showTotal>false</showTotal>
      <legendPosition>Right</legendPosition>
    </components>
  </middleSection>
</Dashboard>
```

Practical rule: generate XML from known-good retrieved artifacts and mutate minimal nodes (`title`, filter values, member names, references), rather than hand-authoring all nodes from scratch.

---

## 6) Product Modes Mapping

Both product modes use the same Metadata API deploy pipeline. Only metadata source differs.

### Mode A: Productized Templates

- Source: versioned template library (internal canonical report/dashboard definitions)
- Runtime transform: field mapping and tenant token substitution
- Output: generated report/dashboard XML + package ZIP
- Deploy: same async Metadata API deploy flow

### Mode B: Frontend-Defined Custom Dashboards

- Source: user-defined dashboard layout/config from frontend
- Runtime transform: layout config -> report/dashboard metadata generation
- Output: generated report/dashboard XML + package ZIP
- Deploy: same async Metadata API deploy flow

### Pipeline Unification

`template_source` is different, but deploy executor, status polling, diagnostics, and rollback semantics are shared.

---

## 7) Preflight Validation Checklist

Run these checks before constructing deploy ZIP:

1. **Object existence**
   - Every report type/object used by report columns/filters/groupings exists in target org.
2. **Field existence + compatibility**
   - All referenced fields exist.
   - Groupings/charts use compatible field types (for example avoid text in numeric aggregations).
   - Filter operators are valid for underlying field data type.
3. **Folder existence / access model**
   - Confirm target report/dashboard folders exist or include folder metadata in same deploy.
   - Validate expected folder `accessType` and tenant sharing model.
4. **Dashboard report reference resolution**
   - Each dashboard component `report` value resolves to a report fullName in package or already deployed state.
5. **API version compatibility**
   - Ensure generated nodes are compatible with `{api_version}` used for deploy/retrieve.
6. **Running user validity**
   - For `SpecifiedUser` dashboards, ensure `runningUser` exists and has access to underlying report data.

Preflight failure should block deploy and return actionable diagnostics before hitting Metadata API.

---

## 8) Runtime and Visibility Gotchas

### Deploy Succeeds, UI Not Visible

Common causes:

- folder access does not include intended users
- dashboard `runningUser` lacks report/object/field visibility
- report in private folder and dashboard in public folder (reference technically exists, but user cannot render)

Example: deploy result is `Succeeded`, but end users cannot open `Revenue_Analytics_Dashboards/Executive_Pipeline_Overview` because folder is private.

### Broken Components After Successful Deploy

If report reference string in dashboard component does not resolve at runtime after rename/move, component can show as broken.

Example stale reference:

- dashboard component: `Revenue_Analytics/Opportunity_Pipeline_by_Stage`
- actual report after rename: `Revenue_Analytics/Opportunity_Pipeline_by_Stage_v2`

### Rename/Delete Drift

- Renaming or deleting reports outside template pipeline creates drift between stored template metadata and org live metadata.
- Dashboard may remain deployed but silently lose data components.

### Namespace / Managed Package Edge Cases

- Namespaced report types or managed metadata dependencies can alter expected API names.
- Retrieval-first generation is required when target org includes managed package report types/fields.

---

## 9) Error Shapes + Diagnostics

### Deploy Submission Error (REST)

```json
[
  {
    "message": "A metadata deployment is already in progress.",
    "errorCode": "CONCURRENT_METADATA_OPERATION"
  }
]
```

Remediation:
- queue/retry with backoff and idempotency key
- avoid parallel metadata deploys per org

### Deploy Status Failure (Component-Level)

```json
{
  "id": "0Afxx0000004ABCGA2",
  "status": "Failed",
  "success": false,
  "numberComponentsTotal": 4,
  "numberComponentErrors": 1,
  "details": {
    "componentFailures": [
      {
        "componentType": "Dashboard",
        "fullName": "Revenue_Analytics_Dashboards/Executive_Pipeline_Overview",
        "problemType": "Error",
        "problem": "In field: report - no Report named Revenue_Analytics/Pipeline_Trended_by_Owner found"
      }
    ]
  }
}
```

Remediation:
- deploy/fix missing report first
- regenerate dashboard references from canonical fullName map

### Retrieve Failure (Version/Type Mismatch)

```json
{
  "id": "09Sxx0000007XYZEA2",
  "status": "Failed",
  "success": false,
  "errorMessage": "Entity of type 'Dashboard' not available for this API version"
}
```

Remediation:
- bump/downgrade `{api_version}` to org-supported version
- retrieve from known-good org/version pair and align generator schema

### Common Failure Classes -> Action Map

| Failure Class | Typical Signal | Remediation |
|---|---|---|
| Missing dependency | `no Report named ... found` | Deploy dependency first, then dashboard |
| Invalid reference | `In field: report` | Rebuild fullName mapping; validate folder/member names |
| Access/running user | Succeeds but not visible/rendered | Fix folder sharing and running user permissions |
| Version incompatibility | `not available for this API version` | Align generator and deploy/retrieve API versions |
| Concurrency | `CONCURRENT_METADATA_OPERATION` | Serialize org-level deploys |

### Recommended Logging Fields

Capture at minimum:

- `deploy_id`
- `org_id`
- `client_id`
- `api_version`
- `componentType`
- `fullName`
- `status`
- `errorCode`
- `problemType`
- `problem`
- `template_key`
- `template_version`

---

## 10) Retrieval + Diff Workflow

### Retrieve From Known-Good Org

Submit retrieve request:

`POST {instance_url}/services/data/{api_version}/metadata/retrieveRequest`

```json
{
  "apiVersion": "{api_version_number_only}",
  "singlePackage": true,
  "unpackaged": {
    "types": [
      {
        "members": [
          "Revenue_Analytics"
        ],
        "name": "ReportFolder"
      },
      <!-- Corrected: removed Dashboard folder member from ReportFolder type; dashboard folders belong under DashboardFolder per Metadata API type model -->
      {
        "members": [
          "Revenue_Analytics/Opportunity_Pipeline_by_Stage",
          "Revenue_Analytics/Pipeline_Trended_by_Owner"
        ],
        "name": "Report"
      },
      {
        "members": [
          "Revenue_Analytics_Dashboards"
        ],
        "name": "DashboardFolder"
      },
      {
        "members": [
          "Revenue_Analytics_Dashboards/Executive_Pipeline_Overview"
        ],
        "name": "Dashboard"
      }
    ],
    "version": "{api_version_number_only}"
  }
}
```

### Baseline Template Workflow

1. Retrieve metadata from known-good org.
2. Decode ZIP and commit artifacts as baseline templates.
3. Normalize stable IDs/placeholders (`{folder_api_name}`, `{report_api_name}`, mapped field tokens).
4. Use structured diff against generated metadata before deploy.
5. Block deploy when diff introduces invalid reference/path changes (for example folder prefix mismatch).

Recommended diff checks:

- dashboard component `report` refs unchanged or intentionally remapped
- no dangling members in `package.xml`
- no unreviewed API version drift

---

## 11) Versioning + Template Lifecycle Guidance

### Template Identity Model

Use deterministic keys:

- `template_key`: stable identifier (for example `revenue.pipeline.executive.v1`)
- `template_version`: semver (`1.4.2`)
- `template_checksum`: hash over normalized metadata bundle

### Compatibility Expectations

- Patch version (`x.y.Z`): non-breaking label/filter default changes
- Minor version (`x.Y.z`): additive components/sections that preserve existing references
- Major version (`X.y.z`): breaking rename/move/reference changes requiring migration logic

### Rollout Strategy

1. Validate-only deploy (`checkOnly=true`) on representative org sample.
2. Canary rollout to subset of tenants.
3. Full rollout with deploy telemetry monitoring (`componentFailures`, visibility signals).

### Rollback Strategy

- Keep last-known-good template artifact per org and per template key.
- On failure or runtime regression:
  - redeploy previous template version bundle
  - re-run reference validation for report/dashboard fullName links
- Avoid destructive folder/report deletes in rollback path unless explicitly required.

### Operational Principle

Treat report/dashboard metadata templates as versioned product assets, not ad hoc XML output. Every deploy should be traceable to `template_key`, `template_version`, and `template_checksum`.
