from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.workflows import (
    WorkflowAssignmentRuleSummary,
    WorkflowDeployRequest,
    WorkflowDeployResponse,
    WorkflowFlowSummary,
    WorkflowListRequest,
    WorkflowListResponse,
    WorkflowRemoveRequest,
    WorkflowRemoveResponse,
)
from app.services import deploy_service, salesforce

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _format_workflow_error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, dict):
            code = str(detail.get("code", "workflows_failed"))
            message = str(detail.get("message", "Workflow operation failed"))
            return f"{code}: {message}"
        return str(detail) if detail is not None else "Workflow operation failed"
    return str(error)


def _resolve_db_deployment_status(status: str) -> str:
    valid = {"pending", "in_progress", "succeeded", "partial", "failed", "rolled_back"}
    return status if status in valid else "failed"


def _resolve_workflow_deployment_type(plan: dict) -> str:
    flows = plan.get("flows")
    assignment_rules = plan.get("assignment_rules")
    has_flows = isinstance(flows, list) and any(isinstance(item, dict) for item in flows)
    has_assignment_rules = isinstance(assignment_rules, list) and any(
        isinstance(item, dict) for item in assignment_rules
    )
    if has_assignment_rules and not has_flows:
        return "assignment_rule"
    return "workflow"


@router.post("/list", response_model=WorkflowListResponse)
async def workflows_list(
    body: WorkflowListRequest,
    auth=Depends(get_current_auth),
) -> WorkflowListResponse:
    auth.assert_permission("workflows.read")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    connection_row = await pool.fetchrow(
        """
        SELECT id, nango_connection_id, nango_provider_config_key
        FROM crm_connections
        WHERE org_id = $1
          AND client_id = $2
          AND status = 'connected'
        """,
        auth.org_id,
        db_client_id,
    )
    if connection_row is None:
        raise HTTPException(status_code=400, detail="No connected Salesforce connection found")

    nango_connection_id = connection_row["nango_connection_id"]
    if not nango_connection_id:
        raise HTTPException(status_code=400, detail="Connection has no Nango connection ID")

    try:
        flow_rows = await salesforce.tooling_query(
            nango_connection_id=nango_connection_id,
            soql=(
                "SELECT Id, DeveloperName, ActiveVersionId, LatestVersionId "
                "FROM FlowDefinition ORDER BY DeveloperName"
            ),
            provider_config_key=connection_row["nango_provider_config_key"],
        )
        assignment_rule_rows = await salesforce.tooling_query(
            nango_connection_id=nango_connection_id,
            soql=(
                "SELECT Id, Name, SobjectType, Active "
                "FROM AssignmentRule WHERE Active = true ORDER BY SobjectType, Name"
            ),
            provider_config_key=connection_row["nango_provider_config_key"],
        )
    finally:
        await pool.execute(
            """
            UPDATE crm_connections
            SET last_used_at = NOW()
            WHERE id = $1
              AND org_id = $2
            """,
            connection_row["id"],
            auth.org_id,
        )

    flows = [
        WorkflowFlowSummary(
            id=str(row["Id"]) if row.get("Id") else None,
            api_name=str(row.get("DeveloperName") or ""),
            active_version_id=str(row["ActiveVersionId"]) if row.get("ActiveVersionId") else None,
            latest_version_id=str(row["LatestVersionId"]) if row.get("LatestVersionId") else None,
        )
        for row in flow_rows
        if str(row.get("DeveloperName") or "").strip()
    ]
    assignment_rules = [
        WorkflowAssignmentRuleSummary(
            id=str(row["Id"]) if row.get("Id") else None,
            object_name=str(row["SobjectType"]) if row.get("SobjectType") else None,
            name=str(row.get("Name") or ""),
            active=bool(row.get("Active")),
        )
        for row in assignment_rule_rows
        if str(row.get("Name") or "").strip()
    ]

    return WorkflowListResponse(
        flows=flows,
        assignment_rules=assignment_rules,
    )


@router.post("/deploy", response_model=WorkflowDeployResponse)
async def workflows_deploy(
    body: WorkflowDeployRequest,
    auth=Depends(get_current_auth),
) -> WorkflowDeployResponse:
    auth.assert_permission("workflows.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    connection_row = await pool.fetchrow(
        """
        SELECT id, nango_connection_id, nango_provider_config_key
        FROM crm_connections
        WHERE org_id = $1
          AND client_id = $2
          AND status = 'connected'
        """,
        auth.org_id,
        db_client_id,
    )
    if connection_row is None:
        raise HTTPException(status_code=400, detail="No connected Salesforce connection found")

    nango_connection_id = connection_row["nango_connection_id"]
    if not nango_connection_id:
        raise HTTPException(status_code=400, detail="Connection has no Nango connection ID")

    if body.conflict_report_id is not None:
        conflict_row = await pool.fetchrow(
            """
            SELECT id
            FROM crm_conflict_reports
            WHERE id = $1
              AND org_id = $2
              AND client_id = $3
            """,
            body.conflict_report_id,
            auth.org_id,
            db_client_id,
        )
        if conflict_row is None:
            raise HTTPException(status_code=400, detail="Conflict report not found for this org/client")

    deployment_row = await pool.fetchrow(
        """
        INSERT INTO crm_deployments (
            org_id,
            client_id,
            connection_id,
            deployed_by,
            deployment_type,
            status,
            plan,
            conflict_report_id
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5::deployment_type,
            'in_progress'::deployment_status,
            $6,
            $7
        )
        RETURNING id
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        UUID(auth.user_id),
        _resolve_workflow_deployment_type(body.plan),
        body.plan,
        body.conflict_report_id,
    )
    if deployment_row is None:
        raise HTTPException(status_code=500, detail="Failed to create deployment record")

    deployment_id = deployment_row["id"]

    try:
        deploy_result = await deploy_service.execute_workflow_deployment(
            nango_connection_id=nango_connection_id,
            plan=body.plan,
            provider_config_key=connection_row["nango_provider_config_key"],
        )
        updated_row = await pool.fetchrow(
            """
            UPDATE crm_deployments
            SET result = $1,
                status = $2::deployment_status,
                deployed_at = NOW(),
                error_message = NULL
            WHERE id = $3
              AND org_id = $4
            RETURNING id, status::text AS status, deployment_type::text AS deployment_type, deployed_at, result
            """,
            deploy_result,
            _resolve_db_deployment_status(str(deploy_result.get("status", "failed"))),
            deployment_id,
            auth.org_id,
        )
    except Exception as error:
        error_message = _format_workflow_error_message(error)
        await pool.execute(
            """
            UPDATE crm_deployments
            SET status = 'failed'::deployment_status,
                error_message = $1
            WHERE id = $2
              AND org_id = $3
            """,
            error_message,
            deployment_id,
            auth.org_id,
        )
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Failed to deploy workflows") from error
    finally:
        await pool.execute(
            """
            UPDATE crm_connections
            SET last_used_at = NOW()
            WHERE id = $1
              AND org_id = $2
            """,
            connection_row["id"],
            auth.org_id,
        )

    if updated_row is None:
        raise HTTPException(status_code=500, detail="Failed to finalize deployment record")

    return WorkflowDeployResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        deployment_type=updated_row["deployment_type"],
        deployed_at=updated_row["deployed_at"].isoformat() if updated_row["deployed_at"] else None,
        result=dict(updated_row["result"]) if isinstance(updated_row["result"], dict) else None,
    )


@router.post("/remove", response_model=WorkflowRemoveResponse)
async def workflows_remove(
    body: WorkflowRemoveRequest,
    auth=Depends(get_current_auth),
) -> WorkflowRemoveResponse:
    auth.assert_permission("workflows.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    flow_api_names = [str(name).strip() for name in body.flow_api_names if str(name).strip()]
    assignment_rule_objects = [
        str(name).strip() for name in body.assignment_rule_objects if str(name).strip()
    ]
    if not flow_api_names and not assignment_rule_objects:
        raise HTTPException(
            status_code=400,
            detail="At least one flow_api_name or assignment_rule_object is required",
        )

    connection_row = await pool.fetchrow(
        """
        SELECT id, nango_connection_id, nango_provider_config_key
        FROM crm_connections
        WHERE org_id = $1
          AND client_id = $2
          AND status = 'connected'
        """,
        auth.org_id,
        db_client_id,
    )
    if connection_row is None:
        raise HTTPException(status_code=400, detail="No connected Salesforce connection found")

    nango_connection_id = connection_row["nango_connection_id"]
    if not nango_connection_id:
        raise HTTPException(status_code=400, detail="Connection has no Nango connection ID")

    removal_plan = {
        "flow_api_names": flow_api_names,
        "assignment_rule_objects": assignment_rule_objects,
        "operation": "remove",
    }
    deployment_type = "assignment_rule" if assignment_rule_objects and not flow_api_names else "workflow"

    deployment_row = await pool.fetchrow(
        """
        INSERT INTO crm_deployments (
            org_id,
            client_id,
            connection_id,
            deployed_by,
            deployment_type,
            status,
            plan
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5::deployment_type,
            'in_progress'::deployment_status,
            $6
        )
        RETURNING id
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        UUID(auth.user_id),
        deployment_type,
        removal_plan,
    )
    if deployment_row is None:
        raise HTTPException(status_code=500, detail="Failed to create deployment record")

    deployment_id = deployment_row["id"]

    try:
        removal_result = await deploy_service.execute_workflow_removal(
            nango_connection_id=nango_connection_id,
            flow_api_names=flow_api_names,
            assignment_rule_objects=assignment_rule_objects,
            provider_config_key=connection_row["nango_provider_config_key"],
        )
        updated_row = await pool.fetchrow(
            """
            UPDATE crm_deployments
            SET result = $1,
                status = $2::deployment_status,
                deployed_at = NOW(),
                error_message = NULL
            WHERE id = $3
              AND org_id = $4
            RETURNING id, status::text AS status, deployment_type::text AS deployment_type, deployed_at, result
            """,
            removal_result,
            _resolve_db_deployment_status(str(removal_result.get("status", "failed"))),
            deployment_id,
            auth.org_id,
        )
    except Exception as error:
        error_message = _format_workflow_error_message(error)
        await pool.execute(
            """
            UPDATE crm_deployments
            SET status = 'failed'::deployment_status,
                error_message = $1
            WHERE id = $2
              AND org_id = $3
            """,
            error_message,
            deployment_id,
            auth.org_id,
        )
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Failed to remove workflows") from error
    finally:
        await pool.execute(
            """
            UPDATE crm_connections
            SET last_used_at = NOW()
            WHERE id = $1
              AND org_id = $2
            """,
            connection_row["id"],
            auth.org_id,
        )

    if updated_row is None:
        raise HTTPException(status_code=500, detail="Failed to finalize deployment record")

    return WorkflowRemoveResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        deployment_type=updated_row["deployment_type"],
        deployed_at=updated_row["deployed_at"].isoformat() if updated_row["deployed_at"] else None,
        result=dict(updated_row["result"]) if isinstance(updated_row["result"], dict) else None,
    )
