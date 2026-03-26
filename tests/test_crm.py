"""Tests for CRM read endpoints."""

import re
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.auth.context import AuthContext
from app.routers.crm import (
    _build_soql,
    _build_where_clause,
    _escape_soql_value,
    _validate_soql,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(role: str = "org_admin", org_id: str = "org-1", client_id: str | None = None):
    from app.auth.context import ROLE_PERMISSIONS

    return AuthContext(
        org_id=org_id,
        user_id="user-1",
        role=role,
        permissions=ROLE_PERMISSIONS[role],
        client_id=client_id,
    )


def _sfdc_result(records=None, done=True, total_size=None, next_path=None):
    recs = records or []
    return {
        "total_size": total_size if total_size is not None else len(recs),
        "done": done,
        "records": recs,
        "next_records_path": next_path,
    }


# ---------------------------------------------------------------------------
# 1. SOQL Validation
# ---------------------------------------------------------------------------


class TestSOQLValidation:
    def test_valid_soql(self):
        _validate_soql("SELECT Id FROM Contact")

    def test_empty_soql_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_soql("")
        assert exc_info.value.status_code == 400

    def test_whitespace_only_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("   ")

    def test_semicolon_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_soql("SELECT Id FROM Contact; DROP TABLE")
        assert exc_info.value.status_code == 400

    def test_insert_keyword_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("INSERT INTO Contact")

    def test_update_keyword_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("UPDATE Contact SET Name = 'x'")

    def test_delete_keyword_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("DELETE FROM Contact")

    def test_upsert_keyword_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("UPSERT Contact")

    def test_merge_keyword_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("MERGE Contact")

    def test_undelete_keyword_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("UNDELETE Contact")

    def test_case_insensitive_dml_rejection(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _validate_soql("select id from contact; delete from contact")


# ---------------------------------------------------------------------------
# 2. SOQL Builder
# ---------------------------------------------------------------------------


class TestSOQLBuilder:
    def test_simple_select(self):
        soql = _build_soql("Contact", [], ["Id", "Name"])
        assert soql == "SELECT Id,Name FROM Contact"

    def test_with_eq_filter(self):
        from app.models.crm import SearchFilter

        filters = [SearchFilter(field="Name", op="eq", value="Acme")]
        soql = _build_soql("Account", filters, ["Id"])
        assert "WHERE Name = 'Acme'" in soql

    def test_with_in_filter(self):
        from app.models.crm import SearchFilter

        filters = [SearchFilter(field="Status", op="in", value=["Open", "Closed"])]
        soql = _build_soql("Case", filters, ["Id"])
        assert "IN ('Open','Closed')" in soql

    def test_escapes_single_quotes(self):
        assert _escape_soql_value("O'Brien") == "O\\'Brien"

    def test_with_limit_and_offset(self):
        soql = _build_soql("Contact", [], ["Id"], limit=10, offset=5)
        assert "LIMIT 10" in soql
        assert "OFFSET 5" in soql

    def test_invalid_field_name_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _build_soql("Contact", [], ["Id; DROP"])

    def test_multiple_filters_and(self):
        from app.models.crm import SearchFilter

        filters = [
            SearchFilter(field="Name", op="eq", value="Acme"),
            SearchFilter(field="Status", op="neq", value="Closed"),
        ]
        soql = _build_soql("Account", filters, ["Id"])
        assert " AND " in soql

    def test_like_operator(self):
        from app.models.crm import SearchFilter

        filters = [SearchFilter(field="Name", op="like", value="%Acme%")]
        soql = _build_soql("Account", filters, ["Id"])
        assert "LIKE '%Acme%'" in soql

    def test_not_in_operator(self):
        from app.models.crm import SearchFilter

        filters = [SearchFilter(field="Type", op="not_in", value=["A", "B"])]
        soql = _build_soql("Account", filters, ["Id"])
        assert "NOT IN ('A','B')" in soql


# ---------------------------------------------------------------------------
# 3. Connection Helper
# ---------------------------------------------------------------------------


class TestConnectionHelper:
    @pytest.mark.asyncio
    async def test_no_connection_raises_404(self):
        from fastapi import HTTPException

        from app.routers.crm import _get_active_connection

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=None)

        auth = _auth()
        client_id = str(uuid4())

        with pytest.raises(HTTPException) as exc_info:
            await _get_active_connection(auth, client_id, pool=mock_pool)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_nango_id_raises_404(self):
        from fastapi import HTTPException

        from app.routers.crm import _get_active_connection

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(
            return_value={
                "nango_connection_id": None,
                "nango_provider_config_key": "salesforce",
            }
        )

        auth = _auth()
        with pytest.raises(HTTPException) as exc_info:
            await _get_active_connection(auth, str(uuid4()), pool=mock_pool)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from app.routers.crm import _get_active_connection

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(
            return_value={
                "nango_connection_id": "conn-123",
                "nango_provider_config_key": "sf-custom",
            }
        )

        auth = _auth()
        result = await _get_active_connection(auth, str(uuid4()), pool=mock_pool)
        assert result["nango_connection_id"] == "conn-123"
        assert result["provider_config_key"] == "sf-custom"


# ---------------------------------------------------------------------------
# 4. Auth & Permissions
# ---------------------------------------------------------------------------


class TestPermissions:
    def test_org_admin_has_crm_read(self):
        auth = _auth("org_admin")
        assert auth.has_permission("crm.read")

    def test_company_admin_has_crm_read(self):
        auth = _auth("company_admin")
        assert auth.has_permission("crm.read")

    def test_company_member_has_crm_read(self):
        auth = _auth("company_member")
        assert auth.has_permission("crm.read")


# ---------------------------------------------------------------------------
# 5. SOQL Proxy Endpoint (via unit-testing the service layer)
# ---------------------------------------------------------------------------


class TestQuerySOQL:
    @pytest.mark.asyncio
    async def test_query_soql_happy_path(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "totalSize": 2,
            "done": True,
            "records": [{"Id": "001"}, {"Id": "002"}],
        }

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import query_soql

            result = await query_soql("conn-1", "SELECT Id FROM Contact")
            assert result["total_size"] == 2
            assert result["done"] is True
            assert len(result["records"]) == 2

    @pytest.mark.asyncio
    async def test_query_soql_with_pagination(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Sforce-Limit-Info": "api-usage=50/100000"}
        mock_response.json.return_value = {
            "totalSize": 5000,
            "done": False,
            "records": [{"Id": "001"}],
            "nextRecordsUrl": "/services/data/v60.0/query/01gxx-2000",
        }

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import query_soql

            result = await query_soql("conn-1", "SELECT Id FROM Contact")
            assert result["done"] is False
            assert result["next_records_path"] == "/services/data/v60.0/query/01gxx-2000"
            assert result["sforce_limit_info"] == "api-usage=50/100000"

    @pytest.mark.asyncio
    async def test_query_soql_sfdc_error(self):
        from fastapi import HTTPException

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = [
            {"errorCode": "MALFORMED_QUERY", "message": "bad soql"}
        ]

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import query_soql

            with pytest.raises(HTTPException) as exc_info:
                await query_soql("conn-1", "SELECT bad FROM nonexistent")
            assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# 6. Query More
# ---------------------------------------------------------------------------


class TestQueryMore:
    @pytest.mark.asyncio
    async def test_query_more_happy_path(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "totalSize": 5000,
            "done": True,
            "records": [{"Id": "003"}],
        }

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import query_more

            result = await query_more(
                "conn-1", "/services/data/v60.0/query/01gxx-2000"
            )
            assert result["done"] is True
            assert len(result["records"]) == 1

    @pytest.mark.asyncio
    async def test_query_more_sfdc_error(self):
        from fastapi import HTTPException

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = [
            {"errorCode": "INVALID_QUERY_LOCATOR", "message": "cursor expired"}
        ]

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import query_more

            with pytest.raises(HTTPException) as exc_info:
                await query_more("conn-1", "/services/data/v60.0/query/expired")
            assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# 7. Describe Sobject Direct
# ---------------------------------------------------------------------------


class TestDescribeSobjectDirect:
    @pytest.mark.asyncio
    async def test_describe_happy_path(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Contact",
            "fields": [{"name": "Id", "type": "id"}],
        }

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import describe_sobject_direct

            result = await describe_sobject_direct("conn-1", "Contact")
            assert result["name"] == "Contact"

    @pytest.mark.asyncio
    async def test_describe_error(self):
        from fastapi import HTTPException

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = [
            {"errorCode": "NOT_FOUND", "message": "object not found"}
        ]

        with (
            patch("app.services.salesforce.token_manager.get_valid_token", new_callable=AsyncMock) as mock_token,
            patch("app.services.salesforce.get_sfdc_client") as mock_client_fn,
        ):
            mock_token.return_value = ("token", "https://test.salesforce.com")
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_fn.return_value = mock_client

            from app.services.salesforce import describe_sobject_direct

            with pytest.raises(HTTPException):
                await describe_sobject_direct("conn-1", "FakeObject__c")


# ---------------------------------------------------------------------------
# 8. Where Clause Builder
# ---------------------------------------------------------------------------


class TestWhereClause:
    def test_empty_filters(self):
        assert _build_where_clause([]) == ""

    def test_eq_filter(self):
        from app.models.crm import SearchFilter

        clause = _build_where_clause([SearchFilter(field="Name", op="eq", value="Acme")])
        assert clause == " WHERE Name = 'Acme'"

    def test_in_requires_list(self):
        from fastapi import HTTPException

        from app.models.crm import SearchFilter

        with pytest.raises(HTTPException):
            _build_where_clause(
                [SearchFilter(field="Status", op="in", value="single")]
            )

    def test_quotes_escaped_in_values(self):
        from app.models.crm import SearchFilter

        clause = _build_where_clause(
            [SearchFilter(field="Name", op="eq", value="O'Brien")]
        )
        assert "O\\'Brien" in clause


# ---------------------------------------------------------------------------
# 9. Shared Client Lifecycle
# ---------------------------------------------------------------------------


class TestSFDCClient:
    @pytest.mark.asyncio
    async def test_init_and_get(self):
        from app.services.sfdc_client import (
            close_sfdc_client,
            get_sfdc_client,
            init_sfdc_client,
        )

        await init_sfdc_client()
        client = get_sfdc_client()
        assert client is not None
        await close_sfdc_client()

    def test_get_before_init_raises(self):
        from app.services import sfdc_client

        # Ensure client is None
        sfdc_client._client = None
        with pytest.raises(RuntimeError):
            sfdc_client.get_sfdc_client()

    @pytest.mark.asyncio
    async def test_close_sets_none(self):
        from app.services.sfdc_client import (
            close_sfdc_client,
            init_sfdc_client,
        )
        from app.services import sfdc_client

        await init_sfdc_client()
        assert sfdc_client._client is not None
        await close_sfdc_client()
        assert sfdc_client._client is None


# ---------------------------------------------------------------------------
# 10. Pydantic Model Validation
# ---------------------------------------------------------------------------


class TestModelValidation:
    def test_soql_request_requires_uuid(self):
        from pydantic import ValidationError

        from app.models.crm import SOQLRequest

        with pytest.raises(ValidationError):
            SOQLRequest(client_id="not-a-uuid", soql="SELECT Id FROM Contact")

    def test_search_filter_validates_operator(self):
        from pydantic import ValidationError

        from app.models.crm import SearchFilter

        with pytest.raises(ValidationError):
            SearchFilter(field="Name", op="invalid_op", value="x")

    def test_association_validates_source_object(self):
        from pydantic import ValidationError

        from app.models.crm import AssociationRequest

        with pytest.raises(ValidationError):
            AssociationRequest(
                client_id=str(uuid4()),
                source_object="InvalidObject",
                source_ids=["001"],
                related_object="Opportunity",
                related_fields=["Id"],
            )

    def test_search_request_defaults(self):
        from app.models.crm import SearchRequest

        req = SearchRequest(client_id=str(uuid4()), object_name="Contact")
        assert req.fields == ["Id", "Name"]
        assert req.filters == []
        assert req.limit is None

    def test_pipeline_request_defaults(self):
        from app.models.crm import PipelineRequest

        req = PipelineRequest(client_id=str(uuid4()))
        assert req.object_name == "Opportunity"
        assert req.field_name == "StageName"
