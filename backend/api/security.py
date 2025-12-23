# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security API endpoints for command approval, audit, and threat intelligence

Includes:
- Command approval and execution security
- Audit logging
- Threat intelligence service status and URL checking (Issue #67)
- Domain security statistics
"""

import logging
from typing import Any, Dict, List, Optional

import aiofiles
from backend.type_defs.common import Metadata

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.enhanced_security_layer import EnhancedSecurityLayer
from src.security.domain_security import get_domain_security_manager
from src.security.threat_intelligence import (
    ThreatLevel,
    get_threat_intelligence_service,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter()


class CommandApprovalRequest(BaseModel):
    command_id: str
    approved: bool


class CommandApprovalResponse(BaseModel):
    success: bool
    message: str


class SecurityStatusResponse(BaseModel):
    security_enabled: bool
    command_security_enabled: bool
    docker_sandbox_enabled: bool
    pending_approvals: List[Metadata]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_status",
    error_code_prefix="SECURITY",
)
@router.get("/status", response_model=SecurityStatusResponse)
async def get_security_status(request: Request):
    """Get current security configuration and status"""
    try:
        # Try to get enhanced security layer, fall back to basic security layer
        enhanced_security = getattr(request.app.state, "enhanced_security_layer", None)
        basic_security = getattr(request.app.state, "security_layer", None)

        if enhanced_security:
            pending_approvals = enhanced_security.get_pending_approvals()
            return SecurityStatusResponse(
                security_enabled=enhanced_security.enable_auth,
                command_security_enabled=enhanced_security.enable_command_security,
                docker_sandbox_enabled=enhanced_security.use_docker_sandbox,
                pending_approvals=pending_approvals,
            )
        elif basic_security:
            # Fallback to basic security layer
            return SecurityStatusResponse(
                security_enabled=basic_security.enable_auth,
                command_security_enabled=False,  # Not available in basic layer
                docker_sandbox_enabled=False,  # Not available in basic layer
                pending_approvals=[],  # Not available in basic layer
            )
        else:
            # No security layer found - initialize enhanced security layer on demand
            enhanced_security = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = enhanced_security

            pending_approvals = enhanced_security.get_pending_approvals()
            return SecurityStatusResponse(
                security_enabled=enhanced_security.enable_auth,
                command_security_enabled=enhanced_security.enable_command_security,
                docker_sandbox_enabled=enhanced_security.use_docker_sandbox,
                pending_approvals=pending_approvals,
            )
    except Exception as e:
        logger.error("Error getting security status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_command",
    error_code_prefix="SECURITY",
)
@router.post("/approve-command", response_model=CommandApprovalResponse)
async def approve_command(request: Request, approval: CommandApprovalRequest):
    """Approve or deny a pending command execution"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer

        # Approve or deny the command
        security_layer.approve_command(approval.command_id, approval.approved)

        action = "approved" if approval.approved else "denied"
        message = f"Command {approval.command_id} {action}"

        logger.info(message)

        return CommandApprovalResponse(success=True, message=message)
    except Exception as e:
        logger.error("Error approving command: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_approvals",
    error_code_prefix="SECURITY",
)
@router.get("/pending-approvals")
async def get_pending_approvals(request: Request):
    """Get list of commands waiting for approval"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer
        pending = security_layer.get_pending_approvals()

        return {"success": True, "pending_approvals": pending, "count": len(pending)}
    except Exception as e:
        logger.error("Error getting pending approvals: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_command_history",
    error_code_prefix="SECURITY",
)
@router.get("/command-history")
async def get_command_history(request: Request, user: str = None, limit: int = 50):
    """Get command execution history from audit log"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer
        history = security_layer.get_command_history(user=user, limit=limit)

        return {"success": True, "command_history": history, "count": len(history)}
    except Exception as e:
        logger.error("Error getting command history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _parse_audit_log_lines(lines: list, limit: int) -> list:
    """Parse JSON audit log lines safely. (Issue #315 - extracted)"""
    import json

    entries = []
    for line in lines[-limit:]:
        try:
            entry = json.loads(line.strip())
            entries.append(entry)
        except json.JSONDecodeError:
            continue
    return entries


async def _read_audit_log_file(log_file: str, limit: int) -> list:
    """Read and parse audit log file. (Issue #315 - extracted)"""
    try:
        async with aiofiles.open(log_file, "r") as f:
            lines = await f.readlines()
        return _parse_audit_log_lines(lines, limit)
    except FileNotFoundError:
        return []
    except OSError as e:
        logger.error("Failed to read audit log file: %s", e)
        return []


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_audit_log",
    error_code_prefix="SECURITY",
)
@router.get("/audit-log")
async def get_audit_log(request: Request, limit: int = 100):
    """Get recent audit log entries"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer

        # Use extracted helper (Issue #315 - reduced depth)
        audit_entries = await _read_audit_log_file(
            security_layer.audit_log_file, limit
        )

        return {
            "success": True,
            "audit_entries": audit_entries,
            "count": len(audit_entries),
        }
    except Exception as e:
        logger.error("Error getting audit log: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# THREAT INTELLIGENCE ENDPOINTS (Issue #67)
# ============================================================================


class URLCheckRequest(BaseModel):
    """Request model for URL reputation check."""

    url: str = Field(..., description="URL to check for threats")


class URLCheckResponse(BaseModel):
    """Response model for URL reputation check."""

    success: bool
    url: str
    overall_score: float
    threat_level: str
    virustotal_score: Optional[float] = None
    urlvoid_score: Optional[float] = None
    sources_checked: int
    cached: bool
    message: Optional[str] = None


class ThreatIntelStatusResponse(BaseModel):
    """Response model for threat intelligence service status."""

    any_service_configured: bool
    virustotal: Dict[str, Any]
    urlvoid: Dict[str, Any]
    cache_stats: Dict[str, Any]


class DomainSecurityStatsResponse(BaseModel):
    """Response model for domain security statistics."""

    success: bool
    stats: Dict[str, Any]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_threat_intel_status",
    error_code_prefix="SECURITY",
)
@router.get("/threat-intel/status", response_model=ThreatIntelStatusResponse)
async def get_threat_intel_status(request: Request):
    """
    Get threat intelligence service configuration and status.

    Returns information about configured services (VirusTotal, URLVoid),
    their rate limit status, and cache statistics.
    """
    try:
        threat_service = get_threat_intelligence_service()
        status = await threat_service.get_service_status()

        return ThreatIntelStatusResponse(
            any_service_configured=threat_service.is_any_service_configured,
            virustotal=status.get("virustotal", {}),
            urlvoid=status.get("urlvoid", {}),
            cache_stats=status.get("cache", {}),
        )
    except Exception as e:
        logger.error("Error getting threat intel status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_url_reputation",
    error_code_prefix="SECURITY",
)
@router.post("/threat-intel/check-url", response_model=URLCheckResponse)
async def check_url_reputation(request: Request, url_request: URLCheckRequest):
    """
    Check URL reputation against threat intelligence services.

    Queries configured services (VirusTotal, URLVoid) and returns
    aggregated threat score. Results are cached for 2 hours.
    """
    try:
        threat_service = get_threat_intelligence_service()

        if not threat_service.is_any_service_configured:
            return URLCheckResponse(
                success=False,
                url=url_request.url,
                overall_score=0.5,
                threat_level=ThreatLevel.UNKNOWN.value,
                sources_checked=0,
                cached=False,
                message="No threat intelligence services configured. "
                "Set VIRUSTOTAL_API_KEY or URLVOID_API_KEY environment variables.",
            )

        result = await threat_service.check_url_reputation(url_request.url)

        return URLCheckResponse(
            success=True,
            url=url_request.url,
            overall_score=result.overall_score,
            threat_level=result.threat_level.value,
            virustotal_score=result.virustotal_score,
            urlvoid_score=result.urlvoid_score,
            sources_checked=result.sources_checked,
            cached=result.cached,
            message=None,
        )
    except Exception as e:
        logger.error("Error checking URL reputation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_domain_security_stats",
    error_code_prefix="SECURITY",
)
@router.get("/domain-security/stats", response_model=DomainSecurityStatsResponse)
async def get_domain_security_stats(request: Request):
    """
    Get domain security statistics including whitelist/blacklist counts,
    threat intelligence integration status, and recent activity.
    """
    try:
        domain_manager = get_domain_security_manager()
        threat_service = get_threat_intelligence_service()

        # Get threat intel status
        threat_status = await threat_service.get_service_status()

        stats = {
            "whitelist_count": len(domain_manager._whitelist),
            "blacklist_count": len(domain_manager._blacklist),
            "suspicious_tlds_count": len(domain_manager._suspicious_tlds),
            "threat_intelligence": {
                "enabled": threat_service.is_any_service_configured,
                "virustotal_configured": threat_status.get("virustotal", {}).get(
                    "configured", False
                ),
                "urlvoid_configured": threat_status.get("urlvoid", {}).get(
                    "configured", False
                ),
                "cache_size": threat_status.get("cache", {}).get("size", 0),
            },
            "settings": {
                "require_https": domain_manager._require_https,
                "max_redirects": domain_manager._max_redirects,
                "check_dns": domain_manager._check_dns,
            },
        }

        return DomainSecurityStatsResponse(success=True, stats=stats)
    except Exception as e:
        logger.error("Error getting domain security stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
