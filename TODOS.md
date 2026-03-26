# TODOS

## Bulk API Support for Large Dataset Queries

**What:** Add Salesforce Bulk API 2.0 support as an alternative to REST Query API for large result sets.

**Why:** PaidEdge needs contacts and opportunities for attribution and audience building. REST Query API returns 2,000 records per page and each page counts against Salesforce's daily API call limit (~100k/day for Enterprise). For a client with 500k contacts, that's 250 API calls just to paginate. Bulk API 2.0 handles millions of records with far fewer API calls.

**Pros:** Dramatically better for large datasets, fewer API calls consumed, purpose-built for ETL/attribution workloads.

**Cons:** Fundamentally different paradigm (async: create job → poll status → download CSV/JSON results). Requires job tracking, polling infrastructure, and result storage. Not needed until PaidEdge hits scale limits.

**Context:** The CRM read endpoints use REST Query API which is fine for interactive queries and moderate result sets. When PaidEdge's audience builder needs to pull 100k+ contacts for segment building, Bulk API becomes the right tool. Start with `app/services/salesforce.py` — add `create_bulk_query_job()`, `poll_bulk_job()`, `get_bulk_results()`. New router endpoint `POST /api/query/bulk`.

**Depends on:** CRM read endpoints PR.

**Added:** 2026-03-25 | **Source:** /plan-eng-review outside voice

---

## Migrate Existing salesforce.py to Shared httpx Client

**What:** Migrate existing functions in `salesforce.py` (topology pull, describe, deploy, push) to use the shared `httpx.AsyncClient` from `sfdc_client.py` instead of creating per-call clients.

**Why:** After the CRM read endpoints PR, there are two HTTP client patterns for the same external service: new CRM read functions use the shared client, old functions use per-call clients. Every future contributor has to know which pattern to use.

**Pros:** Single HTTP client lifecycle, connection pooling benefits for all SFDC calls, consistent pattern.

**Cons:** Touches many existing functions that currently work fine. Risk of regressions in deploy/push/topology flows that are already verified in production.

**Context:** The `sfdc_client.py` module follows the same `init/close/get` pattern as `db.py`. Migration means changing each existing function in `salesforce.py` to call `get_sfdc_client()` instead of creating `httpx.AsyncClient()` inline. Straightforward but wide blast radius — test thoroughly.

**Depends on:** CRM read endpoints PR (ships the shared client module).

**Added:** 2026-03-25 | **Source:** /plan-eng-review outside voice

---

## Activity/Task History Pull for Attribution

**What:** Add `POST /api/crm/activities` endpoint to pull Task/Event records filtered by WhoId (Contact/Lead) or WhatId (Opportunity).

**Why:** Attribution isn't complete without engagement data. "Contact was on 3 calls before deal closed" is a core signal PaidEdge will need for multi-touch attribution.

**Pros:** Completes the attribution data picture. Straightforward SOQL once polymorphic handling is understood. Reuses `crm.read` permission and `_get_active_connection()` helper from CRM read endpoints.

**Cons:** Polymorphic `WhoId`/`WhatId` requires careful SOQL construction. Task and Event have different queryable fields. Medium effort.

**Context:** Salesforce stores activities as polymorphic `Task` and `Event` objects. `WhoId` can point to Contact or Lead; `WhatId` can point to Opportunity, Account, etc. Query pattern: `SELECT ... FROM Task WHERE WhoId IN ({contact_ids})`. The polymorphic complexity is in the response — `Who.Type` field tells you the referenced object type. Uses the same CRM router pattern and SOQLResponse envelope.

**Depends on:** CRM read endpoints PR.

**Added:** 2026-03-25 | **Source:** /plan-ceo-review deferred scope
