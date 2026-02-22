from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_auth, validate_client_access
from app.db import get_pool
from app.models.deployments import (
    DeployHistoryItem,
    DeployHistoryRequest,
    DeployHistoryResponse,
    DeployRequest,
    DeployResponse,
    DeployStatusRequest,
    DeployStatusResponse,
    RollbackRequest,
    RollbackResponse,
)
from app.services import deploy_service

router = APIRouter(prefix="/api/deploy", tags=["deploy"])


def _format_deploy_error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, dict):
            code = str(detail.get("code", "deploy_failed"))
            message = str(detail.get("message", "Deployment failed"))
            return f"{code}: {message}"
        return str(detail) if detail is not None else "Deployment failed"
    return str(error)


def _resolve_db_deployment_status(status: str) -> str:
    valid = {"pending", "in_progress", "succeeded", "partial", "failed", "rolled_back"}
    return status if status in valid else "failed"


@router.post("/execute", response_model=DeployResponse)
async def deploy_execute(
    body: DeployRequest,
    auth=Depends(get_current_auth),
) -> DeployResponse:
    auth.assert_permission("deploy.write")
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
            'custom_object'::deployment_type,
            'in_progress'::deployment_status,
            $5,
            $6
        )
        RETURNING id
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        UUID(auth.user_id),
        body.plan,
        body.conflict_report_id,
    )
    if deployment_row is None:
        raise HTTPException(status_code=500, detail="Failed to create deployment record")

    deployment_id = deployment_row["id"]

    try:
        deploy_result = await deploy_service.execute_deployment(
            nango_connection_id=nango_connection_id,
            plan=body.plan,
            pool=pool,
            org_id=auth.org_id,
            client_id=db_client_id,
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
        error_message = _format_deploy_error_message(error)
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
        raise HTTPException(status_code=500, detail="Failed to execute deployment") from error
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

    return DeployResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        deployment_type=updated_row["deployment_type"],
        deployed_at=updated_row["deployed_at"].isoformat() if updated_row["deployed_at"] else None,
        result=dict(updated_row["result"]) if isinstance(updated_row["result"], dict) else None,
    )


@router.post("/status", response_model=DeployStatusResponse)
async def deploy_status(
    body: DeployStatusRequest,
    auth=Depends(get_current_auth),
) -> DeployStatusResponse:
    auth.assert_permission("deploy.write")
    pool = get_pool()

    row = await pool.fetchrow(
        """
        SELECT id, status::text AS status, deployment_type::text AS deployment_type,
               deployed_at, result, plan, error_message, rolled_back_at
        FROM crm_deployments
        WHERE id = $1
          AND org_id = $2
        """,
        body.id,
        auth.org_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Deployment not found")

    return DeployStatusResponse(
        id=str(row["id"]),
        status=row["status"],
        deployment_type=row["deployment_type"],
        deployed_at=row["deployed_at"].isoformat() if row["deployed_at"] else None,
        result=dict(row["result"]) if isinstance(row["result"], dict) else None,
        plan=dict(row["plan"]) if isinstance(row["plan"], dict) else {},
        error_message=row["error_message"],
        rolled_back_at=row["rolled_back_at"].isoformat() if row["rolled_back_at"] else None,
    )


@router.post("/history", response_model=DeployHistoryResponse)
async def deploy_history(
    body: DeployHistoryRequest,
    auth=Depends(get_current_auth),
) -> DeployHistoryResponse:
    auth.assert_permission("deploy.write")
    pool = get_pool()

    client_id = await validate_client_access(auth, body.client_id, pool=pool)
    db_client_id = UUID(client_id)

    rows = await pool.fetch(
        """
        SELECT id, deployment_type::text AS deployment_type, status::text AS status,
               deployed_at, rolled_back_at, created_at
        FROM crm_deployments
        WHERE org_id = $1
          AND client_id = $2
        ORDER BY created_at DESC
        """,
        auth.org_id,
        db_client_id,
    )

    return DeployHistoryResponse(
        data=[
            DeployHistoryItem(
                id=str(row["id"]),
                deployment_type=row["deployment_type"],
                status=row["status"],
                deployed_at=row["deployed_at"].isoformat() if row["deployed_at"] else None,
                rolled_back_at=row["rolled_back_at"].isoformat() if row["rolled_back_at"] else None,
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]
    )


@router.post("/rollback", response_model=RollbackResponse)
async def deploy_rollback(
    body: RollbackRequest,
    auth=Depends(get_current_auth),
) -> RollbackResponse:
    auth.assert_permission("deploy.write")
    pool = get_pool()

    deployment_row = await pool.fetchrow(
        """
        SELECT id, client_id, connection_id, result
        FROM crm_deployments
        WHERE id = $1
          AND org_id = $2
          AND status = 'succeeded'
        """,
        body.id,
        auth.org_id,
    )
    if deployment_row is None:
        raise HTTPException(
            status_code=400,
            detail="Deployment does not exist or is not in succeeded status",
        )

    deployment_result = deployment_row["result"]
    if not isinstance(deployment_result, dict):
        raise HTTPException(status_code=400, detail="Deployment result is missing or invalid")

    connection_row = await pool.fetchrow(
        """
        SELECT id, nango_connection_id, nango_provider_config_key
        FROM crm_connections
        WHERE id = $1
          AND org_id = $2
          AND client_id = $3
          AND status = 'connected'
        """,
        deployment_row["connection_id"],
        auth.org_id,
        deployment_row["client_id"],
    )
    if connection_row is None:
        raise HTTPException(status_code=400, detail="No connected Salesforce connection found")
    if not connection_row["nango_connection_id"]:
        raise HTTPException(status_code=400, detail="Connection has no Nango connection ID")

    rollback_result = await deploy_service.execute_rollback(
        nango_connection_id=connection_row["nango_connection_id"],
        deployment_result=deployment_result,
        provider_config_key=connection_row["nango_provider_config_key"],
    )
    updated_result = dict(deployment_result)
    updated_result["rollback"] = rollback_result

    updated_row = await pool.fetchrow(
        """
        UPDATE crm_deployments
        SET status = 'rolled_back'::deployment_status,
            rolled_back_at = NOW(),
            result = $1
        WHERE id = $2
          AND org_id = $3
        RETURNING id, status::text AS status, rolled_back_at, result
        """,
        updated_result,
        deployment_row["id"],
        auth.org_id,
    )
    if updated_row is None:
        raise HTTPException(status_code=500, detail="Failed to update deployment rollback status")

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

    return RollbackResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        rolled_back_at=updated_row["rolled_back_at"].isoformat(),
        result=dict(updated_row["result"]) if isinstance(updated_row["result"], dict) else None,
    )


@router.post("/analytics", response_model=DeployResponse)
async def deploy_analytics(
    body: DeployRequest,
    auth=Depends(get_current_auth),
) -> DeployResponse:
    auth.assert_permission("deploy.write")
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
            'report'::deployment_type,
            'in_progress'::deployment_status,
            $5,
            $6
        )
        RETURNING id
        """,
        auth.org_id,
        db_client_id,
        connection_row["id"],
        UUID(auth.user_id),
        body.plan,
        body.conflict_report_id,
    )
    if deployment_row is None:
        raise HTTPException(status_code=500, detail="Failed to create deployment record")

    deployment_id = deployment_row["id"]

    try:
        deploy_result = await deploy_service.execute_analytics_deployment(
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
        error_message = _format_deploy_error_message(error)
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
        raise HTTPException(status_code=500, detail="Failed to execute deployment") from error
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

    return DeployResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        deployment_type=updated_row["deployment_type"],
        deployed_at=updated_row["deployed_at"].isoformat() if updated_row["deployed_at"] else None,
        result=dict(updated_row["result"]) if isinstance(updated_row["result"], dict) else None,
    )


@router.post("/analytics-rollback", response_model=RollbackResponse)
async def deploy_analytics_rollback(
    body: RollbackRequest,
    auth=Depends(get_current_auth),
) -> RollbackResponse:
    auth.assert_permission("deploy.write")
    pool = get_pool()

    deployment_row = await pool.fetchrow(
        """
        SELECT id, client_id, connection_id, result
        FROM crm_deployments
        WHERE id = $1
          AND org_id = $2
          AND status = 'succeeded'
        """,
        body.id,
        auth.org_id,
    )
    if deployment_row is None:
        raise HTTPException(
            status_code=400,
            detail="Deployment does not exist or is not in succeeded status",
        )

    deployment_result = deployment_row["result"]
    if not isinstance(deployment_result, dict):
        raise HTTPException(status_code=400, detail="Deployment result is missing or invalid")

    connection_row = await pool.fetchrow(
        """
        SELECT id, nango_connection_id, nango_provider_config_key
        FROM crm_connections
        WHERE id = $1
          AND org_id = $2
          AND client_id = $3
          AND status = 'connected'
        """,
        deployment_row["connection_id"],
        auth.org_id,
        deployment_row["client_id"],
    )
    if connection_row is None:
        raise HTTPException(status_code=400, detail="No connected Salesforce connection found")
    if not connection_row["nango_connection_id"]:
        raise HTTPException(status_code=400, detail="Connection has no Nango connection ID")

    rollback_result = await deploy_service.execute_analytics_rollback(
        nango_connection_id=connection_row["nango_connection_id"],
        deployment_result=deployment_result,
        provider_config_key=connection_row["nango_provider_config_key"],
    )
    updated_result = dict(deployment_result)
    updated_result["rollback"] = rollback_result

    updated_row = await pool.fetchrow(
        """
        UPDATE crm_deployments
        SET status = 'rolled_back'::deployment_status,
            rolled_back_at = NOW(),
            result = $1
        WHERE id = $2
          AND org_id = $3
        RETURNING id, status::text AS status, rolled_back_at, result
        """,
        updated_result,
        deployment_row["id"],
        auth.org_id,
    )
    if updated_row is None:
        raise HTTPException(status_code=500, detail="Failed to update deployment rollback status")

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

    return RollbackResponse(
        id=str(updated_row["id"]),
        status=updated_row["status"],
        rolled_back_at=updated_row["rolled_back_at"].isoformat(),
        result=dict(updated_row["result"]) if isinstance(updated_row["result"], dict) else None,
    )
