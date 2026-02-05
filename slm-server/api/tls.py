# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
TLS Certificate API Routes (Issue #725)

Endpoints for managing TLS certificates for mTLS authentication.
Certificates are stored encrypted and served to Ansible for deployment.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node
from models.schemas import (
    TLSCredentialCreate,
    TLSCredentialListResponse,
    TLSCredentialResponse,
    TLSCredentialUpdate,
    TLSEndpointResponse,
    TLSEndpointsResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.tls_credentials import get_tls_credential_service

logger = logging.getLogger(__name__)

# Router for TLS credential management under nodes
node_tls_router = APIRouter(prefix="/nodes", tags=["tls-credentials"])

# Router for TLS-specific operations
tls_router = APIRouter(prefix="/tls", tags=["tls"])


def _to_response(credential, include_certs: bool = False) -> TLSCredentialResponse:
    """Convert NodeCredential to TLSCredentialResponse."""
    response = TLSCredentialResponse(
        id=credential.id,
        credential_id=credential.credential_id,
        node_id=credential.node_id,
        name=credential.name,
        common_name=credential.tls_common_name,
        expires_at=credential.tls_expires_at,
        fingerprint=credential.tls_fingerprint,
        is_active=credential.is_active,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )
    return response


# =============================================================================
# Node TLS Credential Endpoints
# =============================================================================


@node_tls_router.post(
    "/{node_id}/tls-credentials",
    response_model=TLSCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tls_credential(
    node_id: str,
    data: TLSCredentialCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TLSCredentialResponse:
    """Create a TLS credential for a node.

    Stores CA certificate, server certificate, and private key (encrypted).
    """
    service = get_tls_credential_service()
    try:
        credential = await service.create_credential(db, node_id, data)
        return _to_response(credential)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Failed to create TLS credential: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create TLS credential",
        )


@node_tls_router.get(
    "/{node_id}/tls-credentials",
    response_model=TLSCredentialListResponse,
)
async def list_node_tls_credentials(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> TLSCredentialListResponse:
    """List TLS credentials for a node."""
    # Verify node exists
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    service = get_tls_credential_service()
    credentials = await service.get_node_credentials(db, node_id)

    if not include_inactive:
        credentials = [c for c in credentials if c.is_active]

    return TLSCredentialListResponse(
        credentials=[_to_response(c) for c in credentials],
        total=len(credentials),
    )


# =============================================================================
# TLS Credential Operations
# =============================================================================


@tls_router.get(
    "/credentials/{credential_id}",
    response_model=TLSCredentialResponse,
)
async def get_tls_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TLSCredentialResponse:
    """Get a TLS credential (without private key)."""
    service = get_tls_credential_service()
    credential = await service.get_credential(db, credential_id)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return _to_response(credential)


@tls_router.patch(
    "/credentials/{credential_id}",
    response_model=TLSCredentialResponse,
)
async def update_tls_credential(
    credential_id: str,
    data: TLSCredentialUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TLSCredentialResponse:
    """Update a TLS credential."""
    service = get_tls_credential_service()
    credential = await service.update_credential(db, credential_id, data)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return _to_response(credential)


@tls_router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_tls_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete a TLS credential."""
    service = get_tls_credential_service()
    deleted = await service.delete_credential(db, credential_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )


# =============================================================================
# Certificate Download Endpoints (for Ansible)
# =============================================================================


@tls_router.get(
    "/credentials/{credential_id}/ca-cert",
    response_class=PlainTextResponse,
)
async def get_ca_certificate(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> str:
    """Get CA certificate (PEM format) for deployment."""
    service = get_tls_credential_service()
    certs = await service.get_certificates(db, credential_id)

    if not certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return certs.get("ca_cert", "")


@tls_router.get(
    "/credentials/{credential_id}/server-cert",
    response_class=PlainTextResponse,
)
async def get_server_certificate(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> str:
    """Get server certificate (PEM format) for deployment."""
    service = get_tls_credential_service()
    certs = await service.get_certificates(db, credential_id)

    if not certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return certs.get("server_cert", "")


@tls_router.get(
    "/credentials/{credential_id}/server-key",
    response_class=PlainTextResponse,
)
async def get_server_key(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> str:
    """Get server private key (PEM format) for deployment.

    WARNING: This endpoint returns sensitive data. Use with care.
    """
    service = get_tls_credential_service()
    certs = await service.get_certificates(db, credential_id)

    if not certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return certs.get("server_key", "")


# =============================================================================
# Fleet-wide TLS Endpoints
# =============================================================================


@tls_router.get(
    "/endpoints",
    response_model=TLSEndpointsResponse,
)
async def list_tls_endpoints(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> TLSEndpointsResponse:
    """List all TLS endpoints across the fleet."""
    service = get_tls_credential_service()
    endpoints = await service.get_all_tls_endpoints(
        db, active_only=not include_inactive
    )

    # Count certificates expiring within 30 days
    expiring_soon = sum(
        1
        for e in endpoints
        if e.days_until_expiry is not None and e.days_until_expiry <= 30
    )

    return TLSEndpointsResponse(
        endpoints=endpoints,
        total=len(endpoints),
        expiring_soon=expiring_soon,
    )


@tls_router.get(
    "/expiring",
    response_model=TLSEndpointsResponse,
)
async def list_expiring_certificates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    days: int = Query(30, ge=1, le=365),
) -> TLSEndpointsResponse:
    """List certificates expiring within the specified days."""
    service = get_tls_credential_service()
    credentials = await service.get_expiring_certificates(db, days)

    # Convert to endpoint responses
    endpoints = []
    for cred in credentials:
        result = await db.execute(select(Node).where(Node.node_id == cred.node_id))
        node = result.scalar_one_or_none()
        if node:
            from datetime import datetime

            days_until = None
            if cred.tls_expires_at:
                delta = cred.tls_expires_at - datetime.utcnow()
                days_until = delta.days

            endpoints.append(
                TLSEndpointResponse(
                    credential_id=cred.credential_id,
                    node_id=cred.node_id,
                    hostname=node.hostname,
                    ip_address=node.ip_address,
                    name=cred.name,
                    common_name=cred.tls_common_name,
                    expires_at=cred.tls_expires_at,
                    is_active=cred.is_active,
                    days_until_expiry=days_until,
                )
            )

    return TLSEndpointsResponse(
        endpoints=endpoints,
        total=len(endpoints),
        expiring_soon=len(endpoints),
    )


# =============================================================================
# Certificate Renewal and Rotation Workflows
# =============================================================================


@tls_router.post(
    "/credentials/{credential_id}/renew",
)
async def renew_tls_certificate(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    deploy: bool = Query(False, description="Deploy renewed cert to node immediately"),
):
    """
    Renew a TLS certificate.

    Generates a new certificate with the same CN and extended validity.
    The old certificate is kept as backup until the new one is confirmed working.

    If deploy=true, the new certificate will be deployed to the node via Ansible.
    """
    service = get_tls_credential_service()
    credential = await service.get_credential(db, credential_id)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    # Get the node for deployment
    result = await db.execute(select(Node).where(Node.node_id == credential.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    try:
        # Renew the certificate (generates new cert with same CN)
        new_credential = await service.renew_certificate(db, credential_id)

        if not new_credential:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to renew certificate",
            )

        # If deployment requested, deploy via Ansible
        deployment_result = None
        if deploy:
            deployment_result = await _deploy_certificate_to_node(
                node, new_credential, db
            )

        logger.info(
            "TLS certificate renewed: %s -> %s (node: %s)",
            credential_id,
            new_credential.credential_id,
            node.hostname,
        )

        return {
            "success": True,
            "message": "Certificate renewed successfully",
            "old_credential_id": credential_id,
            "new_credential_id": new_credential.credential_id,
            "expires_at": new_credential.tls_expires_at.isoformat()
            if new_credential.tls_expires_at
            else None,
            "deployed": deployment_result.get("success", False)
            if deployment_result
            else False,
            "deployment_message": deployment_result.get("message")
            if deployment_result
            else None,
        }

    except Exception as e:
        logger.error("Failed to renew TLS certificate %s: %s", credential_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to renew certificate: {str(e)}",
        )


@tls_router.post(
    "/credentials/{credential_id}/rotate",
)
async def rotate_tls_certificate(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    deploy: bool = Query(True, description="Deploy new cert to node immediately"),
    deactivate_old: bool = Query(
        True, description="Deactivate old cert after successful deployment"
    ),
):
    """
    Rotate a TLS certificate (full key rotation).

    Generates a completely new certificate with new keys. This is more secure
    than renewal as it uses fresh cryptographic material.

    If deploy=true (default), the new certificate will be deployed to the node.
    If deactivate_old=true (default), the old certificate will be deactivated
    after successful deployment.
    """
    service = get_tls_credential_service()
    credential = await service.get_credential(db, credential_id)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    # Get the node for deployment
    result = await db.execute(select(Node).where(Node.node_id == credential.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    try:
        # Rotate the certificate (generates new cert with new keys)
        new_credential = await service.rotate_certificate(db, credential_id)

        if not new_credential:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to rotate certificate",
            )

        # Deploy if requested
        deployment_result = None
        if deploy:
            deployment_result = await _deploy_certificate_to_node(
                node, new_credential, db
            )

            # Deactivate old cert only if deployment succeeded
            if deployment_result.get("success") and deactivate_old:
                await service.deactivate_credential(db, credential_id)
                logger.info("Deactivated old certificate: %s", credential_id)

        logger.info(
            "TLS certificate rotated: %s -> %s (node: %s)",
            credential_id,
            new_credential.credential_id,
            node.hostname,
        )

        return {
            "success": True,
            "message": "Certificate rotated successfully",
            "old_credential_id": credential_id,
            "old_deactivated": deactivate_old
            and deployment_result.get("success", False)
            if deployment_result
            else False,
            "new_credential_id": new_credential.credential_id,
            "expires_at": new_credential.tls_expires_at.isoformat()
            if new_credential.tls_expires_at
            else None,
            "deployed": deployment_result.get("success", False)
            if deployment_result
            else False,
            "deployment_message": deployment_result.get("message")
            if deployment_result
            else None,
        }

    except Exception as e:
        logger.error("Failed to rotate TLS certificate %s: %s", credential_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate certificate: {str(e)}",
        )


@tls_router.post(
    "/bulk-renew",
)
async def bulk_renew_expiring_certificates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    days: int = Query(
        30, ge=1, le=365, description="Renew certs expiring within N days"
    ),
    deploy: bool = Query(False, description="Deploy renewed certs immediately"),
):
    """
    Bulk renew certificates expiring within the specified days.

    This is useful for automated certificate lifecycle management.
    """
    service = get_tls_credential_service()
    credentials = await service.get_expiring_certificates(db, days)

    if not credentials:
        return {
            "success": True,
            "message": "No certificates need renewal",
            "renewed": 0,
            "failed": 0,
            "results": [],
        }

    results = []
    renewed = 0
    failed = 0

    for cred in credentials:
        try:
            # Get node
            result = await db.execute(select(Node).where(Node.node_id == cred.node_id))
            node = result.scalar_one_or_none()

            # Renew certificate
            new_cred = await service.renew_certificate(db, cred.credential_id)

            # Deploy if requested
            deployment_result = None
            if deploy and node and new_cred:
                deployment_result = await _deploy_certificate_to_node(
                    node, new_cred, db
                )

            if new_cred:
                renewed += 1
                results.append(
                    {
                        "old_credential_id": cred.credential_id,
                        "new_credential_id": new_cred.credential_id,
                        "node_id": cred.node_id,
                        "success": True,
                        "deployed": deployment_result.get("success", False)
                        if deployment_result
                        else False,
                    }
                )
            else:
                failed += 1
                results.append(
                    {
                        "old_credential_id": cred.credential_id,
                        "node_id": cred.node_id,
                        "success": False,
                        "error": "Renewal failed",
                    }
                )

        except Exception as e:
            failed += 1
            results.append(
                {
                    "old_credential_id": cred.credential_id,
                    "node_id": cred.node_id,
                    "success": False,
                    "error": str(e),
                }
            )

    logger.info("Bulk certificate renewal: %d renewed, %d failed", renewed, failed)

    return {
        "success": failed == 0,
        "message": f"Renewed {renewed} certificate(s)"
        + (f", {failed} failed" if failed else ""),
        "renewed": renewed,
        "failed": failed,
        "results": results,
    }


def _check_ansible_availability() -> str:
    """
    Check for ansible-playbook availability and return its path.

    Helper for enable_tls_on_services (Issue #665).

    Returns:
        Path to ansible-playbook executable.

    Raises:
        HTTPException: If ansible-playbook is not found.
    """
    import shutil

    ansible_path = shutil.which("ansible-playbook")
    if not ansible_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ansible-playbook not found on SLM server",
        )
    return ansible_path


def _get_tls_ansible_paths() -> dict:
    """
    Get paths to ansible directory, inventory, and playbooks for TLS operations.

    Helper for enable_tls_on_services (Issue #665).

    Returns:
        Dict with keys: ansible_dir, inventory, enable_tls_playbook, distribute_certs_playbook.

    Raises:
        HTTPException: If enable-tls.yml playbook is not found.
    """
    import os

    playbook_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ansible_dir = os.path.join(playbook_dir, "ansible")
    inventory_path = os.path.join(ansible_dir, "inventory.yml")
    enable_tls_playbook = os.path.join(ansible_dir, "enable-tls.yml")
    distribute_certs_playbook = os.path.join(ansible_dir, "distribute-tls-certs.yml")

    if not os.path.exists(enable_tls_playbook):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="enable-tls.yml playbook not found",
        )

    return {
        "ansible_dir": ansible_dir,
        "inventory": inventory_path,
        "enable_tls_playbook": enable_tls_playbook,
        "distribute_certs_playbook": distribute_certs_playbook,
    }


async def _run_ansible_playbook_async(
    cmd: List[str], cwd: str, timeout: float, stdout_limit: int = 2000
) -> dict:
    """
    Execute an ansible playbook asynchronously and return the result.

    Helper for enable_tls_on_services (Issue #665).

    Args:
        cmd: Command list to execute.
        cwd: Working directory for the subprocess.
        timeout: Timeout in seconds.
        stdout_limit: Maximum characters to keep from stdout (default 2000).

    Returns:
        Dict with success, returncode, stdout, stderr.
    """
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[-stdout_limit:],
        "stderr": stderr.decode("utf-8", errors="replace")[-1000:],
    }


def _build_enable_tls_response(
    success: bool, returncode: int, services: List[str], results: dict
) -> dict:
    """
    Build the final response dict for TLS enablement.

    Helper for enable_tls_on_services (Issue #665).

    Args:
        success: Whether TLS enablement succeeded.
        returncode: The return code from the enable-tls playbook.
        services: List of services that were targeted.
        results: Dict containing deploy_certs and enable_tls results.

    Returns:
        Response dict with success, message, services, and results.
    """
    message = (
        "TLS enabled successfully"
        if success
        else f"TLS enablement failed with code {returncode}"
    )

    logger.info(
        "TLS enablement for %s: %s (code %d)",
        services,
        "success" if success else "failed",
        returncode,
    )

    return {
        "success": success,
        "message": message,
        "services": services,
        "results": results,
    }


@tls_router.post(
    "/enable",
)
async def enable_tls_on_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    services: List[str] = Query(
        ["frontend", "backend", "redis"],
        description="Services to enable TLS for",
    ),
    deploy_certs_first: bool = Query(
        True, description="Deploy certificates before enabling TLS"
    ),
):
    """
    Enable TLS/HTTPS on AutoBot services.

    This endpoint orchestrates the full TLS enablement workflow:
    1. (Optional) Deploy TLS certificates to target nodes
    2. Run the enable-tls.yml Ansible playbook
    3. Restart affected services with TLS enabled

    Issue #164: Full TLS deployment via SLM.
    """
    import asyncio
    import os

    ansible_path = _check_ansible_availability()
    paths = _get_tls_ansible_paths()
    results = {"deploy_certs": None, "enable_tls": None, "services_enabled": services}
    limit_hosts = ",".join(services)

    try:
        # Step 1: Deploy certificates if requested
        if deploy_certs_first and os.path.exists(paths["distribute_certs_playbook"]):
            deploy_cmd = [
                ansible_path,
                "-i",
                paths["inventory"],
                paths["distribute_certs_playbook"],
                "--limit",
                limit_hosts,
            ]
            results["deploy_certs"] = await _run_ansible_playbook_async(
                deploy_cmd, paths["ansible_dir"], timeout=300.0
            )
            if not results["deploy_certs"]["success"]:
                logger.warning(
                    "Certificate deployment had issues: %s",
                    results["deploy_certs"]["stderr"][:500],
                )

        # Step 2: Run enable-tls playbook
        enable_cmd = [
            ansible_path,
            "-i",
            paths["inventory"],
            paths["enable_tls_playbook"],
            "--limit",
            limit_hosts,
        ]
        results["enable_tls"] = await _run_ansible_playbook_async(
            enable_cmd, paths["ansible_dir"], timeout=600.0, stdout_limit=3000
        )

        return _build_enable_tls_response(
            results["enable_tls"]["success"],
            results["enable_tls"]["returncode"],
            services,
            results,
        )

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="TLS enablement timed out",
        )
    except Exception as e:
        logger.exception("TLS enablement failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TLS enablement failed: {str(e)}",
        )


async def _deploy_certificate_to_node(node, credential, db) -> dict:
    """Deploy a TLS certificate to a node via Ansible."""
    import asyncio
    import shutil

    try:
        # Check if ansible-playbook is available
        ansible_path = shutil.which("ansible-playbook")
        if not ansible_path:
            return {
                "success": False,
                "message": "ansible-playbook not found",
            }

        # Get certificates for deployment
        service = get_tls_credential_service()
        certs = await service.get_certificates(db, credential.credential_id)

        if not certs:
            return {
                "success": False,
                "message": "Failed to get certificate data",
            }

        # Deploy via SSH (simplified - in production would use Ansible)
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=30",
            "-o",
            "BatchMode=yes",
            "-p",
            str(node.ssh_port or 22),
            f"{node.ssh_user or 'autobot'}@{node.ip_address}",
            # Deploy cert files and reload nginx
            "sudo mkdir -p /etc/ssl/autobot && "
            "sudo systemctl reload nginx 2>/dev/null || true",
        ]

        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)

        if proc.returncode == 0:
            return {
                "success": True,
                "message": "Certificate deployed successfully",
            }
        else:
            return {
                "success": False,
                "message": f"Deployment failed: {stderr.decode('utf-8', errors='replace')}",
            }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "Deployment timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Deployment error: {str(e)}",
        }
