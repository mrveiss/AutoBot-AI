# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cloud Provider Integration API (Issue #61)

FastAPI router for AWS, Azure, and GCP integrations.
Provides endpoints for testing connections, listing resources, and
getting account information.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_code import (
    CloudAccountInfoResponse,
    CloudConnectionTestResponse,
    CloudResourcesResponse,
    CloudStorageResponse,
)
from api.schemas_workflows import (
    CloudConnectionTestRequest,
    CloudProviderInfo,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from integrations.base import IntegrationConfig
from integrations.cloud_integration import (
    AWSIntegration,
    AzureIntegration,
    GCPIntegration,
)

router = APIRouter(
    tags=["integrations-cloud"],
    dependencies=[Depends(check_admin_permission)],
)
logger = get_logger(__name__)


@router.get("/providers", response_model=List[CloudProviderInfo])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_providers",
    error_code_prefix="INTEGRATION_CLOUD",
)
async def list_providers():
    """List all supported cloud providers."""
    return [
        CloudProviderInfo(
            provider="aws",
            name="Amazon Web Services",
            description="AWS cloud platform integration",
            required_fields=["api_key", "api_secret", "extra.region"],
        ),
        CloudProviderInfo(
            provider="azure",
            name="Microsoft Azure",
            description="Azure cloud platform integration",
            required_fields=[
                "token",
                "extra.subscription_id",
                "extra.tenant_id",
            ],
        ),
        CloudProviderInfo(
            provider="gcp",
            name="Google Cloud Platform",
            description="GCP cloud platform integration",
            required_fields=["token", "extra.project_id"],
        ),
    ]


@router.post("/test-connection", response_model=CloudConnectionTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connection",
    error_code_prefix="INTEGRATION_CLOUD",
)
async def test_connection(request: CloudConnectionTestRequest):
    """Test connection to a cloud provider."""
    try:
        integration = _create_integration(
            request.provider,
            request.api_key,
            request.api_secret,
            request.token,
            request.extra,
        )

        health = await integration.test_connection()
        return {
            "provider": health.provider,
            "status": health.status.value,
            "latency_ms": health.latency_ms,
            "message": health.message,
            "details": health.details,
            "last_checked": health.last_checked.isoformat(),
        }
    except ValueError as exc:
        logger.warning("Invalid provider in test_connection: %s", exc)
        raise HTTPException(status_code=400, detail="Request failed")
    except Exception as exc:
        logger.error("Error testing connection: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{provider}/resources", response_model=CloudResourcesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_resources",
    error_code_prefix="INTEGRATION_CLOUD",
)
async def list_resources(
    provider: str,
    api_key: str | None = None,
    api_secret: str | None = None,
    token: str | None = None,
    region: str | None = None,
    subscription_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    zone: str | None = None,
):
    """List compute resources (instances/VMs) for a cloud provider."""
    try:
        extra = _build_extra_params(region, subscription_id, tenant_id, project_id, zone)
        integration = _create_integration(provider, api_key, api_secret, token, extra)

        action_map = {
            "aws": "list_ec2_instances",
            "azure": "list_vms",
            "gcp": "list_instances",
        }

        action = action_map.get(provider)
        if not action:
            raise ValueError(f"Unsupported provider: {provider}")

        result = await integration.execute_action(action, {"zone": zone})
        return result
    except ValueError as exc:
        logger.warning("Invalid provider in list_resources: %s", exc)
        raise HTTPException(status_code=400, detail="Request failed")
    except Exception as exc:
        logger.error("Error listing resources: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{provider}/storage", response_model=CloudStorageResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_storage",
    error_code_prefix="INTEGRATION_CLOUD",
)
async def list_storage(
    provider: str,
    api_key: str | None = None,
    api_secret: str | None = None,
    token: str | None = None,
    region: str | None = None,
    subscription_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
):
    """List storage resources (buckets/accounts) for a cloud provider."""
    try:
        extra = _build_extra_params(region, subscription_id, tenant_id, project_id, None)
        integration = _create_integration(provider, api_key, api_secret, token, extra)

        action_map = {
            "aws": "list_s3_buckets",
            "azure": "list_storage_accounts",
            "gcp": "list_storage_buckets",
        }

        action = action_map.get(provider)
        if not action:
            raise ValueError(f"Unsupported provider: {provider}")

        result = await integration.execute_action(action, {})
        return result
    except ValueError as exc:
        logger.warning("Invalid provider in list_storage: %s", exc)
        raise HTTPException(status_code=400, detail="Request failed")
    except Exception as exc:
        logger.error("Error listing storage: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{provider}/account", response_model=CloudAccountInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_account_info",
    error_code_prefix="INTEGRATION_CLOUD",
)
async def get_account_info(
    provider: str,
    api_key: str | None = None,
    api_secret: str | None = None,
    token: str | None = None,
    region: str | None = None,
    subscription_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
):
    """Get account/subscription/project information for a cloud provider."""
    try:
        extra = _build_extra_params(region, subscription_id, tenant_id, project_id, None)
        integration = _create_integration(provider, api_key, api_secret, token, extra)

        action_map = {
            "aws": "get_account_info",
            "azure": "get_subscription_info",
            "gcp": "get_project_info",
        }

        action = action_map.get(provider)
        if not action:
            raise ValueError(f"Unsupported provider: {provider}")

        result = await integration.execute_action(action, {})
        return result
    except ValueError as exc:
        logger.warning("Invalid provider in get_account_info: %s", exc)
        raise HTTPException(status_code=400, detail="Request failed")
    except Exception as exc:
        logger.error("Error getting account info: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


def _create_integration(
    provider: str,
    api_key: str | None,
    api_secret: str | None,
    token: str | None,
    extra: Dict[str, Any],
):
    """Create integration instance for the specified provider."""
    config = IntegrationConfig(
        name=f"{provider}_integration",
        provider=provider,
        api_key=api_key,
        api_secret=api_secret,
        token=token,
        extra=extra,
    )

    integration_map = {
        "aws": AWSIntegration,
        "azure": AzureIntegration,
        "gcp": GCPIntegration,
    }

    integration_class = integration_map.get(provider)
    if not integration_class:
        raise ValueError(f"Unsupported provider: {provider}")

    return integration_class(config)


def _build_extra_params(
    region: str | None,
    subscription_id: str | None,
    tenant_id: str | None,
    project_id: str | None,
    zone: str | None,
) -> Dict[str, Any]:
    """Build extra parameters dict from query params."""
    extra = {}
    if region:
        extra["region"] = region
    if subscription_id:
        extra["subscription_id"] = subscription_id
    if tenant_id:
        extra["tenant_id"] = tenant_id
    if project_id:
        extra["project_id"] = project_id
    if zone:
        extra["zone"] = zone
    return extra
