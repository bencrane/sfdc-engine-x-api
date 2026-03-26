import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.context import AuthContext
from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.crm import (
    AssociationRequest,
    CampaignMembersRequest,
    ContactRolesRequest,
    CountRequest,
    CountResponse,
    LeadConversionsRequest,
    PipelineRequest,
    PipelineResponse,
    QueryMoreRequest,
    SearchFilter,
    SearchRequest,
    SOQLRequest,
    SOQLResponse,
)
from app.services import salesforce

router = APIRouter(prefix="/api", tags=["crm"])

_DML_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|UPSERT|MERGE|UNDELETE)\b", re.IGNORECASE
)
_FIELD_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
_OPERATOR_MAP = {
    "eq": "=",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
    "in": "IN",
    "not_in": "NOT IN",
}
_ID_CHUNK_SIZE = 2000


async def _get_active_connection(
    auth: AuthContext, client_id: str, pool=None
) -> dict:
    """Look up the active Salesforce connection for a client."""
    if pool is None:
        pool = get_pool()
    db_client_id = UUID(client_id)

    row = await pool.fetchrow(
        """
        SELECT nango_connection_id, nango_provider_config_key
        FROM crm_connections
        WHERE org_id = $1
          AND client_id = $2
          AND status = 'connected'
        """,
        auth.org_id,
        db_client_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No active Salesforce connection")

    nango_connection_id = row["nango_connection_id"]
    if not nango_connection_id:
        raise HTTPException(
            status_code=404, detail="Connection has no Nango connection ID"
        )

    return {
        "nango_connection_id": nango_connection_id,
        "provider_config_key": row["nango_provider_config_key"],
    }


def _validate_soql(soql: str) -> None:
    """Reject DML keywords and semicolons in raw SOQL."""
    if not soql or not soql.strip():
        raise HTTPException(status_code=400, detail="SOQL query cannot be empty")
    if ";" in soql:
        raise HTTPException(status_code=400, detail="SOQL query cannot contain semicolons")
    if _DML_KEYWORDS.search(soql):
        raise HTTPException(
            status_code=400, detail="SOQL query cannot contain DML keywords"
        )


def _escape_soql_value(value: str) -> str:
    """Escape single quotes for SOQL string literals."""
    return value.replace("'", "\\'")


def _validate_field_name(field: str) -> None:
    """Validate field name is safe for SOQL injection."""
    if not _FIELD_NAME_RE.match(field):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid field name: {field}",
        )


def _build_where_clause(filters: list[SearchFilter]) -> str:
    """Build a WHERE clause from search filters."""
    if not filters:
        return ""

    clauses = []
    for f in filters:
        _validate_field_name(f.field)
        sql_op = _OPERATOR_MAP.get(f.op)
        if sql_op is None:
            raise HTTPException(status_code=400, detail=f"Unknown operator: {f.op}")

        if f.op in ("in", "not_in"):
            if not isinstance(f.value, list):
                raise HTTPException(
                    status_code=400,
                    detail=f"Operator {f.op} requires a list value",
                )
            escaped = [f"'{_escape_soql_value(v)}'" for v in f.value]
            clauses.append(f"{f.field} {sql_op} ({','.join(escaped)})")
        else:
            val = f.value if isinstance(f.value, str) else str(f.value)
            clauses.append(f"{f.field} {sql_op} '{_escape_soql_value(val)}'")

    return " WHERE " + " AND ".join(clauses)


def _build_soql(
    object_name: str,
    filters: list[SearchFilter],
    fields: list[str],
    limit: int | None = None,
    offset: int | None = None,
) -> str:
    """Build a safe SOQL query string."""
    for field in fields:
        _validate_field_name(field)

    where = _build_where_clause(filters)
    soql = f"SELECT {','.join(fields)} FROM {object_name}{where}"

    if limit is not None:
        soql += f" LIMIT {int(limit)}"
    if offset is not None:
        soql += f" OFFSET {int(offset)}"

    return soql


def _make_response(result: dict, response_headers: dict | None = None) -> SOQLResponse:
    """Convert salesforce result dict to SOQLResponse."""
    resp = SOQLResponse(
        total_size=result["total_size"],
        done=result["done"],
        records=result["records"],
        next_records_path=result.get("next_records_path"),
    )
    return resp


def _extract_sforce_limit(result: dict) -> dict[str, str] | None:
    """Extract Sforce-Limit-Info for response headers."""
    limit_info = result.get("sforce_limit_info")
    if limit_info:
        return {"Sforce-Limit-Info": limit_info}
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/query/soql", response_model=SOQLResponse)
async def query_soql(
    body: SOQLRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    _validate_soql(body.soql)

    conn = await _get_active_connection(auth, client_id, pool=pool)
    result = await salesforce.query_soql(
        conn["nango_connection_id"],
        body.soql,
        provider_config_key=conn["provider_config_key"],
    )
    return _make_response(result)


@router.post("/query/more", response_model=SOQLResponse)
async def query_more(
    body: QueryMoreRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    if not body.next_records_path.startswith("/services/data/"):
        raise HTTPException(
            status_code=400, detail="Invalid next_records_path format"
        )

    conn = await _get_active_connection(auth, client_id, pool=pool)
    result = await salesforce.query_more(
        conn["nango_connection_id"],
        body.next_records_path,
        provider_config_key=conn["provider_config_key"],
    )
    return _make_response(result)


@router.post("/crm/search", response_model=SOQLResponse)
async def search(
    body: SearchRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    soql = _build_soql(
        body.object_name,
        body.filters,
        body.fields,
        limit=body.limit,
        offset=body.offset,
    )

    conn = await _get_active_connection(auth, client_id, pool=pool)
    result = await salesforce.query_soql(
        conn["nango_connection_id"],
        soql,
        provider_config_key=conn["provider_config_key"],
    )
    return _make_response(result)


@router.post("/crm/count", response_model=CountResponse)
async def count(
    body: CountRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    where = _build_where_clause(body.filters)
    soql = f"SELECT COUNT() FROM {body.object_name}{where}"

    conn = await _get_active_connection(auth, client_id, pool=pool)
    result = await salesforce.query_soql(
        conn["nango_connection_id"],
        soql,
        provider_config_key=conn["provider_config_key"],
    )
    return CountResponse(count=result["total_size"])


@router.post("/crm/associations", response_model=SOQLResponse)
async def associations(
    body: AssociationRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    if not body.source_ids:
        raise HTTPException(status_code=400, detail="source_ids cannot be empty")

    for field in body.related_fields:
        _validate_field_name(field)

    conn = await _get_active_connection(auth, client_id, pool=pool)

    # Determine the relationship field based on source object
    if body.source_object == "Contact":
        relationship_field = "ContactId"
    else:
        relationship_field = "OpportunityId"

    all_records: list[dict] = []
    total_size = 0

    # Chunk source_ids into batches of 2,000
    for i in range(0, len(body.source_ids), _ID_CHUNK_SIZE):
        chunk = body.source_ids[i : i + _ID_CHUNK_SIZE]
        escaped_ids = [f"'{_escape_soql_value(sid)}'" for sid in chunk]
        id_list = ",".join(escaped_ids)

        fields_str = ",".join(body.related_fields)
        soql = (
            f"SELECT {fields_str} FROM {body.related_object} "
            f"WHERE {relationship_field} IN ({id_list})"
        )

        result = await salesforce.query_soql(
            conn["nango_connection_id"],
            soql,
            provider_config_key=conn["provider_config_key"],
        )
        all_records.extend(result["records"])
        total_size += result["total_size"]

    return SOQLResponse(
        total_size=total_size,
        done=True,
        records=all_records,
        next_records_path=None,
    )


@router.post("/crm/contact-roles", response_model=SOQLResponse)
async def contact_roles(
    body: ContactRolesRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    if not body.opportunity_ids:
        raise HTTPException(status_code=400, detail="opportunity_ids cannot be empty")

    conn = await _get_active_connection(auth, client_id, pool=pool)

    all_records: list[dict] = []
    total_size = 0

    for i in range(0, len(body.opportunity_ids), _ID_CHUNK_SIZE):
        chunk = body.opportunity_ids[i : i + _ID_CHUNK_SIZE]
        escaped_ids = [f"'{_escape_soql_value(oid)}'" for oid in chunk]
        id_list = ",".join(escaped_ids)

        soql = (
            "SELECT Id,ContactId,OpportunityId,Role,IsPrimary "
            f"FROM OpportunityContactRole WHERE OpportunityId IN ({id_list})"
        )

        result = await salesforce.query_soql(
            conn["nango_connection_id"],
            soql,
            provider_config_key=conn["provider_config_key"],
        )
        all_records.extend(result["records"])
        total_size += result["total_size"]

    return SOQLResponse(
        total_size=total_size,
        done=True,
        records=all_records,
        next_records_path=None,
    )


@router.post("/crm/campaign-members", response_model=SOQLResponse)
async def campaign_members(
    body: CampaignMembersRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    default_fields = [
        "Id", "ContactId", "LeadId", "CampaignId", "Status", "FirstRespondedDate",
    ]
    fields = body.fields if body.fields else default_fields
    for field in fields:
        _validate_field_name(field)

    fields_str = ",".join(fields)
    campaign_id_escaped = _escape_soql_value(body.campaign_id)
    soql = (
        f"SELECT {fields_str} FROM CampaignMember "
        f"WHERE CampaignId = '{campaign_id_escaped}'"
    )

    conn = await _get_active_connection(auth, client_id, pool=pool)
    result = await salesforce.query_soql(
        conn["nango_connection_id"],
        soql,
        provider_config_key=conn["provider_config_key"],
    )
    return _make_response(result)


@router.post("/crm/lead-conversions", response_model=SOQLResponse)
async def lead_conversions(
    body: LeadConversionsRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    default_fields = [
        "Id", "ConvertedContactId", "ConvertedAccountId",
        "ConvertedOpportunityId", "ConvertedDate", "Name", "Email",
    ]
    fields = body.fields if body.fields else default_fields
    for field in fields:
        _validate_field_name(field)

    where = _build_where_clause(body.filters)
    if where:
        where += " AND IsConverted = true"
    else:
        where = " WHERE IsConverted = true"

    fields_str = ",".join(fields)
    soql = f"SELECT {fields_str} FROM Lead{where}"

    conn = await _get_active_connection(auth, client_id, pool=pool)
    result = await salesforce.query_soql(
        conn["nango_connection_id"],
        soql,
        provider_config_key=conn["provider_config_key"],
    )
    return _make_response(result)


@router.post("/crm/pipelines", response_model=PipelineResponse)
async def pipelines(
    body: PipelineRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    auth.assert_permission("crm.read")

    pool = get_pool()
    client_id = await validate_client_access(auth, body.client_id, pool=pool)

    conn = await _get_active_connection(auth, client_id, pool=pool)
    describe = await salesforce.describe_sobject_direct(
        conn["nango_connection_id"],
        body.object_name,
        provider_config_key=conn["provider_config_key"],
    )

    fields = describe.get("fields", [])
    target_field = None
    for field in fields:
        if isinstance(field, dict) and field.get("name") == body.field_name:
            target_field = field
            break

    if target_field is None:
        raise HTTPException(
            status_code=404,
            detail=f"Field {body.field_name} not found on {body.object_name}",
        )

    picklist_values = target_field.get("picklistValues", [])

    return PipelineResponse(
        object_name=body.object_name,
        field_name=body.field_name,
        stages=picklist_values,
    )
