# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cloud Provider Integration API (Issue #61)

FastAPI router for AWS, Azure, and GCP integrations.
Provides endpoints for testing connections, listing resources, and
getting account information.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.integrations.base import IntegrationConfig
from backend.integrations.cloud_integration import (
    AWSIntegration,
    AzureIntegration,
    GCPIntegration,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["integrations-cloud"])
logger = logging.getLogger(__name__)


class CloudProviderInfo(BaseModel):
    """Information about a supported cloud provider."""

    provider: str
    name: str
    description: str
    required_fields: List[str]


class ConnectionTestRequest(BaseModel):
    """Request model for testing cloud provider connection."""

    provider: str = Field(..., description="Cloud provider (aws, azure, gcp)")
    api_key: Optional[str] = Field(None, description="API key or access key")
    api_secret: Optional[str] = Field(None, description="API secret key")
    token: Optional[str] = Field(None, description="Access token")
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific config"
    )


class ResourceListRequest(BaseModel):
    """Request model for listing cloud resources."""

    provider: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    token: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    resource_type: str = Field(
        ..., description="Type of resource (instances, vms, storage)"
    )


@router.get("/providers", response_model=List[CloudProviderInfo])
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


@router.post("/test-connection")
async def test_connection(request: ConnectionTestRequest):
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
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error testing connection: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{provider}/resources")
async def list_resources(
    provider: str,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    token: Optional[str] = None,
    region: Optional[str] = None,
    subscription_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
    zone: Optional[str] = None,
):
    """List compute resources (instances/VMs) for a cloud provider."""
    try:
        extra = _build_extra_params(
            region, subscription_id, tenant_id, project_id, zone
        )
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
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error listing resources: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{provider}/storage")
async def list_storage(
    provider: str,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    token: Optional[str] = None,
    region: Optional[str] = None,
    subscription_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
):
    """List storage resources (buckets/accounts) for a cloud provider."""
    try:
        extra = _build_extra_params(
            region, subscription_id, tenant_id, project_id, None
        )
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
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error listing storage: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{provider}/account")
async def get_account_info(
    provider: str,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    token: Optional[str] = None,
    region: Optional[str] = None,
    subscription_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
):
    """Get account/subscription/project information for a cloud provider."""
    try:
        extra = _build_extra_params(
            region, subscription_id, tenant_id, project_id, None
        )
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
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error getting account info: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


def _create_integration(
    provider: str,
    api_key: Optional[str],
    api_secret: Optional[str],
    token: Optional[str],
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
    region: Optional[str],
    subscription_id: Optional[str],
    tenant_id: Optional[str],
    project_id: Optional[str],
    zone: Optional[str],
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
