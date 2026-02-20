# Salesforce Connected App Distribution Reference (External Client Apps)

This document is a standalone reference for distributing a Salesforce External Client App (ECA) to client organizations so a multi-tenant SaaS can run OAuth against each client org.

---

## 1) Landscape: How External OAuth Apps Get Into Client Orgs

### The core distribution problem

You create an External Client App in your own org, but your customer admin authorizes OAuth in **their** Salesforce org. Because ECAs are closed-by-default, the app must be present in the target org before authorization can succeed.

Salesforce describes this explicitly:
- Traditional connected apps were effectively open-by-default once created locally.
- External Client Apps require explicit installation/deployment in the org that will authorize them.

### Why this differs from legacy Connected Apps

- **Legacy Connected Apps**: historically cross-org usable behavior after local creation.
- **External Client Apps**: install-first model; org admins control whether the app exists in their org.

This is why SaaS vendors now need a package/distribution workflow per client org.

### Current status (2025/2026): Connected Apps vs ECAs

As of Spring '26:
- Salesforce documents that **new Connected App creation is restricted**.
- Existing Connected Apps continue to work.
- Salesforce recommends moving to External Client Apps.

### Distribution mechanisms

For packaging/distribution, you will see three paths in Salesforce tooling:
- **1GP Unmanaged**
- **1GP Managed**
- **2GP (Unlocked or Managed)**

### Decision matrix

| Use case | Recommended mechanism | Why |
|---|---|---|
| One-off internal transfer, no upgrade lifecycle | 1GP Unmanaged (or direct metadata deploy) | Quickest, but no controlled upgrades |
| Client-facing commercial SaaS, repeat installs, version lifecycle | **2GP Managed** | Release flow, installable package versions (`04t`), source-driven lifecycle |
| Enterprise internal rollout where subscribers can edit metadata | 2GP Unlocked | Subscriber-editable model |
| Legacy ISV flow already on 1GP namespace/package org | 1GP Managed (legacy continuity) | Existing 1GP workflows still exist |
| New build with long-term distribution strategy | **2GP Managed** | Salesforce’s modern packaging direction |

### Critical practical guidance

- ECAs are documented and taught by Salesforce with **2GP managed packaging** as the standard distribution path.
- Metadata coverage currently shows `ExternalClientApplication` as packageable across packaging columns, including 1GP and 2GP.
- For canonical SaaS client distribution, use **2GP Managed** unless you have a specific legacy 1GP constraint.

---

## 2) External Client Apps (ECA) — What They Are

### What ECAs are

External Client Apps are Salesforce’s modern replacement for Connected Apps for external integrations. They support OAuth flows but separate:
- **Developer-controlled settings** (packageable)
- **Subscriber/admin policies** (not packaged; controlled in subscriber org)

### Key metadata in an ECA

At minimum:
- App header (`ExternalClientApplication`)
- OAuth plugin settings (`ExtlClntAppOauthSettings`)
- Global OAuth settings (`ExtlClntAppGlobalOauthSettings`)
- OAuth configurable policies (`ExtlClntAppOauthConfigurablePolicies`) are generated/managed in deploy lifecycle and subscriber policy flow

OAuth credentials behavior is important:
- Consumer credentials are treated as sensitive/global settings in Salesforce ECA model.
- Do not assume every policy/secret field belongs in package metadata.

### Where it is defined in Setup

In Salesforce Setup:
- Go to **External Client App Manager**.
- Create/manage the ECA and OAuth plugin settings.

### API name and metadata type for packaging

- **Metadata type**: `ExternalClientApplication`
- **Primary source file suffix**: `.eca-meta.xml`
- Typical source directory:
  - `force-app/main/default/externalClientApps/<AppApiName>.eca-meta.xml`

Related ECA metadata types commonly packaged with OAuth plugin configuration:
- `ExtlClntAppGlobalOauthSettings` (`.ecaGlblOauth-meta.xml`)
- `ExtlClntAppOauthSettings` (`.ecaOauth-meta.xml`)

### Verify ECA configuration before packaging

Before building a package version:
1. Confirm `distributionState` is packaging-ready (`Packageable` / Setup equivalent).
2. Confirm callback URL(s) and OAuth scopes are correct.
3. Confirm plugin settings files are present in source.
4. Deploy/retrieve once in a non-ephemeral org to validate generated policy metadata behavior.
5. Run metadata validation/package version create against Dev Hub.

---

## 3) 1GP Packages (First Generation)

This section documents 1GP mechanics for completeness and migration planning.

### 1GP Unmanaged

#### Setup UI flow (classic package manager flow)

1. Setup -> **Package Manager**.
2. Click **New** package.
3. Enter package metadata and save.
4. Open package components tab and click **Add**.
5. Add the desired components.
6. Click **Upload** to create an installable package version.
7. Salesforce generates/sends the installation link for the uploaded version.

Typical install URL shape:

```bash
https://login.salesforce.com/packaging/installPackage.apexp?p0=04tXXXXXXXXXXXX
```

Client admin install flow:
1. Open install URL while logged into target org.
2. Approve package installation.
3. Choose access level (`Install for Admins Only` or `Install for All Users` where offered).

Limitations:
- No managed release lifecycle.
- No push-upgrade model.
- Subscriber can modify/delete subscriber-editable assets.

#### Are ECAs supported in 1GP unmanaged?

Salesforce documentation is not explicit with a dedicated 1GP-unmanaged ECA guide. Metadata coverage indicates `ExternalClientApplication` is packageable in 1GP/2GP columns, but Salesforce ECA distribution guidance is centered on 2GP managed packaging.

**Actionable conclusion**: treat 1GP unmanaged for ECA as legacy/exception workflow; use 2GP managed for production SaaS distribution.

### 1GP Managed

#### Steps and requirements

1. Register namespace in packaging org.
2. Create managed package in Package Manager.
3. Add components.
4. Upload a managed package version.
5. Distribute installation URL (`04t...`).

Namespace is mandatory for managed package identity and upgrades.

#### Upgrade behavior

- New uploaded versions can be installed as upgrades by subscribers.
- Managed packaging preserves package ownership/governance model better than unmanaged.

#### Are ECAs supported in 1GP managed?

Metadata coverage indicates `ExternalClientApplication` support includes 1GP column. However, Salesforce’s current ECA distribution learning path and recommended workflow are 2GP managed.

**Actionable conclusion**: 1GP managed may be technically possible in legacy packaging contexts, but for new ECA distribution pipelines use 2GP managed.

---

## 4) 2GP Packages (Second Generation) — Primary Distribution Path

This is the recommended end-to-end path for distributing an ECA to many client orgs.

### Prerequisites

1. **Dev Hub enabled** in your packaging authority org.
2. **Salesforce CLI (`sf`) installed**.
3. Authenticated Dev Hub in CLI.
4. SFDX project with valid `sfdx-project.json`.

Authenticate Dev Hub:

```bash
sf org login web --set-default-dev-hub --alias my-devhub --instance-url https://login.salesforce.com
```

### Create project and baseline configuration

```bash
sf project generate --name eca-distribution --template standard
cd eca-distribution
```

`sfdx-project.json` (minimum practical template):

```json
{
  "packageDirectories": [
    {
      "path": "force-app",
      "default": true,
      "package": "EcaDistributionPkg",
      "versionName": "ver 1.0",
      "versionNumber": "1.0.0.NEXT"
    }
  ],
  "name": "eca-distribution",
  "namespace": "your_ns_prefix",
  "sfdcLoginUrl": "https://login.salesforce.com",
  "sourceApiVersion": "66.0",
  "packageAliases": {}
}
```

### Create the 2GP package

Managed (recommended for multi-tenant SaaS client distribution):

```bash
sf package create \
  --name EcaDistributionPkg \
  --package-type Managed \
  --path force-app \
  --target-dev-hub my-devhub
```

Unlocked (use only if subscriber-editable model is required):

```bash
sf package create \
  --name EcaDistributionPkgUnlocked \
  --package-type Unlocked \
  --path force-app \
  --target-dev-hub my-devhub
```

### Add ECA metadata to source

Directory structure:

```text
force-app/main/default/
  externalClientApps/
    MyEca.eca-meta.xml
  extlClntAppGlobalOauthSets/
    MyEcaGlobal.ecaGlblOauth-meta.xml
  extlClntAppOauthSettings/
    MyEcaOauth.ecaOauth-meta.xml
```

`force-app/main/default/externalClientApps/MyEca.eca-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ExternalClientApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <contactEmail>platform@example.com</contactEmail>
    <description>OAuth app distributed to client orgs</description>
    <distributionState>Packageable</distributionState>
    <isProtected>false</isProtected>
    <label>MyEca</label>
</ExternalClientApplication>
```

`force-app/main/default/extlClntAppGlobalOauthSets/MyEcaGlobal.ecaGlblOauth-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ExtlClntAppGlobalOauthSettings xmlns="http://soap.sforce.com/2006/04/metadata">
    <callbackUrl>https://your-saas.example.com/oauth/callback</callbackUrl>
    <externalClientApplication>MyEca</externalClientApplication>
    <isConsumerSecretOptional>false</isConsumerSecretOptional>
    <isIntrospectAllTokens>false</isIntrospectAllTokens>
    <isPkceRequired>true</isPkceRequired>
    <isSecretRequiredForRefreshToken>true</isSecretRequiredForRefreshToken>
    <label>MyEcaGlobal</label>
    <shouldRotateConsumerKey>false</shouldRotateConsumerKey>
    <shouldRotateConsumerSecret>false</shouldRotateConsumerSecret>
</ExtlClntAppGlobalOauthSettings>
```

`force-app/main/default/extlClntAppOauthSettings/MyEcaOauth.ecaOauth-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ExtlClntAppOauthSettings xmlns="http://soap.sforce.com/2006/04/metadata">
    <commaSeparatedOauthScopes>Api, Web, RefreshToken, OpenID</commaSeparatedOauthScopes>
    <externalClientApplication>MyEca</externalClientApplication>
    <label>MyEcaOauth</label>
</ExtlClntAppOauthSettings>
```

### Create a package version

Use install-key bypass for simpler client installs (or use `--installation-key` for controlled distribution):

```bash
sf package version create \
  --package EcaDistributionPkg \
  --target-dev-hub my-devhub \
  --installation-key-bypass \
  --wait 60 \
  --code-coverage
```

### Code coverage requirement and workaround for ECA-only package

`sf package version create` requires code coverage to promote validated versions. An ECA-only package has no Apex, so teams often add a tiny Apex class + test to satisfy package coverage checks.

Add these files:

`force-app/main/default/classes/PackageCoverageProbe.cls`

```apex
public with sharing class PackageCoverageProbe {
    public static String ping() {
        return 'ok';
    }
}
```

`force-app/main/default/classes/PackageCoverageProbe.cls-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>66.0</apiVersion>
    <status>Active</status>
</ApexClass>
```

`force-app/main/default/classes/PackageCoverageProbeTest.cls`

```apex
@IsTest
private class PackageCoverageProbeTest {
    @IsTest
    static void pingReturnsOk() {
        Test.startTest();
        String result = PackageCoverageProbe.ping();
        Test.stopTest();
        System.assertEquals('ok', result);
    }
}
```

`force-app/main/default/classes/PackageCoverageProbeTest.cls-meta.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>66.0</apiVersion>
    <status>Active</status>
</ApexClass>
```

Re-run package version create with `--code-coverage`.

### `--code-coverage` vs `--skip-validation`

From CLI behavior:
- `--code-coverage`: runs packaged Apex tests and stores coverage; required for promotable validated versions.
- `--skip-validation`: faster build, but version is not promotable.
- You cannot use both flags together.

### Promote for production installs

After version creation completes and you have an `04t...` package version ID:

```bash
sf package version promote \
  --package 04tXXXXXXXXXXXX \
  --target-dev-hub my-devhub \
  --no-prompt
```

What promoted means:
- Package version becomes released and installable in production subscriber orgs.

Install URL format:

```bash
https://login.salesforce.com/packaging/installPackage.apexp?p0=04tXXXXXXXXXXXX
```

Sandbox URL format:

```bash
https://test.salesforce.com/packaging/installPackage.apexp?p0=04tXXXXXXXXXXXX
```

### Install in a client org

Client admin process:
1. Open install URL while logged into target org.
2. Review package details and approve install.
3. Choose `Install for Admins Only` or `Install for All Users`.
4. Wait for completion message/email.

Verify install:
- Setup -> **Installed Packages** shows package/version.
- Setup -> **External Client App Manager** shows installed ECA metadata.
- OAuth authorization endpoint now recognizes the client app in that org.

### Upgrading

For each new release:
1. Update source metadata.
2. Create new package version (`sf package version create ...`).
3. Promote (`sf package version promote ...`).
4. Distribute new `04t` install URL to clients, or install via CLI in controlled orgs.

CLI upgrade/install example:

```bash
sf package install \
  --target-org client-org-alias \
  --package 04tNEWVERSIONID \
  --security-type AdminsOnly \
  --wait 30 \
  --publish-wait 30
```

---

## 5) The OAuth Flow After Installation

Once installed in the client org, OAuth is standard Salesforce OAuth 2.0 for that org.

### Authorization URL construction

Use the client org login domain (or My Domain), for example:

```bash
https://<client-my-domain>.my.salesforce.com/services/oauth2/authorize?response_type=code&client_id=<consumer_key>&redirect_uri=<urlencoded_callback>&state=<opaque_state>
```

### What client admin sees

- Salesforce login (if needed)
- Consent/approval page for requested scopes
- Redirect back to your callback URL with `code` and `state`

### Token exchange

Your SaaS exchanges the code at token endpoint:

```bash
POST https://<client-my-domain>.my.salesforce.com/services/oauth2/token
```

Common response fields:
- `access_token`
- `refresh_token` (if scope/flow allows)
- `instance_url`
- `id`
- `token_type`
- `issued_at`
- `signature`

### Multi-tenant SaaS implication

Store tokens per client org tenancy boundary. API calls then go to that tenant’s `instance_url` using bearer token. Refresh flow is standard OAuth refresh token grant.

---

## 6) Troubleshooting

### `OAUTH_EC_APP_NOT_FOUND` / “External client app is not installed in this org”

Cause:
- OAuth request sent to org where ECA package is not installed.

Fix:
1. Send/install the correct package version URL (`...installPackage.apexp?p0=04t...`).
2. Verify package appears in **Installed Packages**.
3. Retry authorization URL in the same org.

### Package version code coverage failures

Cause:
- Promotable package validation requires Apex coverage with `--code-coverage`.
- ECA-only package has no Apex tests.

Fix:
1. Add minimal Apex probe class and test (shown above).
2. Recreate version with `--code-coverage`.

### `INSTALLATION_FAILED`

Common causes:
- Missing dependency package version.
- Insufficient permissions in target org.
- API/version incompatibility between package metadata and target org capabilities.
- Trying to install unpromoted or invalid package version in restricted contexts.

Fix checklist:
1. Confirm package version is promoted/released.
2. Check dependency chain in package version report.
3. Install as System Administrator.
4. Retry with full install logs and inspect first hard failure.

### Dev Hub not enabled / Dev Hub permission errors

Cause:
- Packaging commands require Dev Hub and package permissions.

Fix:
1. Enable Dev Hub in the packaging org.
2. Authenticate correct Dev Hub:

```bash
sf org login web --set-default-dev-hub --alias my-devhub --instance-url https://login.salesforce.com
```

3. Re-run with explicit `--target-dev-hub my-devhub`.

### Package creation permission errors

Cause:
- User lacks package create/version create rights in Dev Hub.

Fix:
- Use a user with package management permissions (typically System Admin in Dev Hub org with packaging enabled).

### Version promote failures

Cause:
- Version created with `--skip-validation`.
- Coverage/validation incomplete.
- Ancestor/dependency constraints for managed lifecycle.

Fix:
1. Build a fully validated version (`--code-coverage`, no `--skip-validation`).
2. Re-run promote:

```bash
sf package version promote --package 04tXXXXXXXXXXXX --target-dev-hub my-devhub --no-prompt
```

---

## 7) End-to-End Walkthrough (Zero -> Client OAuth Authorized)

### Step 1: Create and auth project

```bash
sf project generate --name eca-distribution --template standard
cd eca-distribution
sf org login web --set-default-dev-hub --alias my-devhub --instance-url https://login.salesforce.com
```

### Step 2: Create ECA metadata in source

Create folders:

```bash
mkdir -p force-app/main/default/externalClientApps
mkdir -p force-app/main/default/extlClntAppGlobalOauthSets
mkdir -p force-app/main/default/extlClntAppOauthSettings
mkdir -p force-app/main/default/classes
```

Create files:
- `force-app/main/default/externalClientApps/MyEca.eca-meta.xml`
- `force-app/main/default/extlClntAppGlobalOauthSets/MyEcaGlobal.ecaGlblOauth-meta.xml`
- `force-app/main/default/extlClntAppOauthSettings/MyEcaOauth.ecaOauth-meta.xml`
- `force-app/main/default/classes/PackageCoverageProbe.cls`
- `force-app/main/default/classes/PackageCoverageProbe.cls-meta.xml`
- `force-app/main/default/classes/PackageCoverageProbeTest.cls`
- `force-app/main/default/classes/PackageCoverageProbeTest.cls-meta.xml`

Use the exact file contents from Section 4.

### Step 3: Configure `sfdx-project.json`

Set package directory and alias metadata exactly as shown in Section 4.

### Step 4: Create package

```bash
sf package create \
  --name EcaDistributionPkg \
  --package-type Managed \
  --path force-app \
  --target-dev-hub my-devhub
```

### Step 5: Create package version

```bash
sf package version create \
  --package EcaDistributionPkg \
  --target-dev-hub my-devhub \
  --installation-key-bypass \
  --wait 60 \
  --code-coverage
```

Capture the generated `04t...` from output/report:

```bash
sf package version create report --package-create-request-id 08cXXXXXXXXXXXX --target-dev-hub my-devhub
```

### Step 6: Promote version

```bash
sf package version promote \
  --package 04tXXXXXXXXXXXX \
  --target-dev-hub my-devhub \
  --no-prompt
```

### Step 7: Send install link to client admin

```bash
https://login.salesforce.com/packaging/installPackage.apexp?p0=04tXXXXXXXXXXXX
```

### Step 8: Client installs package

Client admin:
1. Opens URL in their org session.
2. Installs package.
3. Confirms package in Installed Packages and ECA presence in External Client App Manager.

### Step 9: Client authorizes OAuth

Your SaaS redirects admin/user to:

```bash
https://<client-my-domain>.my.salesforce.com/services/oauth2/authorize?response_type=code&client_id=<consumer_key>&redirect_uri=<urlencoded_callback>&state=<opaque_state>
```

Exchange returned code for tokens and store per tenant boundary.

### Step 10: API access active

Call Salesforce APIs with:
- `Authorization: Bearer <access_token>`
- Base URL: client-specific `instance_url`

---

## Sources (Salesforce)

- Salesforce Developers Blog: Secure Your Org with External Client Apps (2025)
- Salesforce Developers: Metadata Coverage Report (current transition report)
- Trailhead: External Client App Basics -> Package and Distribute External Client Applications
- Trailhead Project: Building an External Client App with SFDX
- Salesforce CLI command reference (validated via `sf` help output for `package create`, `package version create`, `package version promote`, `package install`)
