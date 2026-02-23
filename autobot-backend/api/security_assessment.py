# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Assessment API Endpoints

RESTful API for managing security assessments, workflows, and findings.

Issue: #260
"""

import logging
from typing import Any, Optional

from auth_middleware import check_admin_permission
from backend.services.security_tool_parsers import parse_tool_output
from backend.services.security_workflow_manager import (
    PHASE_DESCRIPTIONS,
    VALID_TRANSITIONS,
    AssessmentPhase,
    SecurityWorkflowManager,
    get_security_workflow_manager,
)

# Issue #756: Consolidated from src/utils/request_utils.py
from backend.utils.request_utils import generate_request_id
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


# Pydantic models for request/response validation
class CreateAssessmentRequest(BaseModel):
    """Request to create a new security assessment."""

    name: str = Field(..., min_length=1, max_length=200)
    target: str = Field(..., min_length=1, description="Target IP, CIDR, or hostname")
    scope: Optional[list[str]] = Field(None, description="In-scope targets")
    training_mode: bool = Field(False, description="Enable exploitation phase")
    metadata: Optional[dict[str, Any]] = None


class AdvancePhaseRequest(BaseModel):
    """Request to advance to the next phase."""

    reason: str = Field("", description="Reason for phase transition")
    target_phase: Optional[str] = Field(
        None, description="Specific phase to transition to"
    )


class AddHostRequest(BaseModel):
    """Request to add a host to the assessment."""

    ip: str = Field(..., description="Host IP address")
    hostname: Optional[str] = None
    status: str = Field("up", description="Host status (up/down/unknown)")
    metadata: Optional[dict[str, Any]] = None


class AddPortRequest(BaseModel):
    """Request to add a port to a host."""

    host_ip: str = Field(..., description="Host IP address")
    port: int = Field(..., ge=1, le=65535)
    protocol: str = Field("tcp", description="Protocol (tcp/udp)")
    state: str = Field("open", description="Port state")
    service: Optional[str] = None
    version: Optional[str] = None


class AddVulnerabilityRequest(BaseModel):
    """Request to add a vulnerability."""

    host_ip: str = Field(..., description="Affected host IP")
    cve_id: Optional[str] = None
    title: str = Field("", description="Vulnerability title")
    severity: str = Field("unknown", description="Severity level")
    description: str = ""
    affected_service: Optional[str] = None
    affected_port: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class AddFindingRequest(BaseModel):
    """Request to add a general finding."""

    finding_type: str = Field(..., description="Type of finding")
    description: str = ""
    data: Optional[dict[str, Any]] = None


class ParseToolOutputRequest(BaseModel):
    """Request to parse tool output."""

    output: str = Field(..., min_length=1, description="Raw tool output")
    tool: Optional[str] = Field(
        None, description="Tool name (auto-detect if not provided)"
    )


class RecoverErrorRequest(BaseModel):
    """Request to recover from error state."""

    target_phase: str = Field(..., description="Phase to recover to")
    reason: str = Field("Manual recovery", description="Recovery reason")


# Dependency injection
async def get_workflow_manager() -> SecurityWorkflowManager:
    """Get the workflow manager instance."""
    return get_security_workflow_manager()


# API Endpoints


@router.post("/assessments")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_assessment",
    error_code_prefix="SEC",
)
async def create_assessment(
    admin_check: bool = Depends(check_admin_permission),
    request: CreateAssessmentRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Create a new security assessment.

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        request: Assessment creation request
        manager: Workflow manager instance

    Returns:
        Created assessment data
    """
    request_id = generate_request_id()

    logger.info(
        f"[{request_id}] Creating assessment: name={request.name}, "
        f"target={request.target}, training_mode={request.training_mode}"
    )

    assessment = await manager.create_assessment(
        name=request.name,
        target=request.target,
        scope=request.scope,
        training_mode=request.training_mode,
        metadata=request.metadata,
    )

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "data": assessment.to_dict(),
            "request_id": request_id,
        },
    )


@router.get("/assessments")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_assessments",
    error_code_prefix="SEC",
)
async def list_assessments(
    admin_check: bool = Depends(check_admin_permission),
    active_only: bool = Query(True, description="Only return active assessments"),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    List security assessments.

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        active_only: Filter to active assessments only
        manager: Workflow manager instance

    Returns:
        List of assessments
    """
    request_id = generate_request_id()

    if active_only:
        assessments = await manager.list_active_assessments()
    else:
        # For now, just return active ones
        assessments = await manager.list_active_assessments()

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "assessments": [a.to_dict() for a in assessments],
                "count": len(assessments),
            },
            "request_id": request_id,
        },
    )


@router.get("/assessments/{assessment_id}")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_assessment",
    error_code_prefix="SEC",
)
async def get_assessment(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Get a specific assessment by ID.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        manager: Workflow manager instance

    Returns:
        Assessment data
    """
    request_id = generate_request_id()

    assessment = await manager.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": assessment.to_dict(),
            "request_id": request_id,
        },
    )


@router.get("/assessments/{assessment_id}/summary")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_assessment_summary",
    error_code_prefix="SEC",
)
async def get_assessment_summary(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Get assessment summary for LLM context.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        manager: Workflow manager instance

    Returns:
        Assessment summary
    """
    request_id = generate_request_id()

    summary = await manager.get_assessment_summary(assessment_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": summary,
            "request_id": request_id,
        },
    )


@router.delete("/assessments/{assessment_id}")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="delete_assessment",
    error_code_prefix="SEC",
)
async def delete_assessment(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Delete an assessment.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        manager: Workflow manager instance

    Returns:
        Deletion confirmation
    """
    request_id = generate_request_id()

    deleted = await manager.delete_assessment(assessment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Assessment deleted",
            "request_id": request_id,
        },
    )


@router.get("/assessments/{assessment_id}/phase")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_phase",
    error_code_prefix="SEC",
)
async def get_current_phase(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Get current phase and available transitions.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        manager: Workflow manager instance

    Returns:
        Current phase and transition info
    """
    request_id = generate_request_id()

    assessment = await manager.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    current_phase = assessment.phase.value
    phase_info = PHASE_DESCRIPTIONS.get(current_phase, {})
    valid_transitions = VALID_TRANSITIONS.get(current_phase, [])

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "current_phase": current_phase,
                "description": phase_info.get("description", ""),
                "available_actions": phase_info.get("actions", []),
                "valid_transitions": valid_transitions,
                "training_mode": assessment.training_mode,
            },
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/phase")
@with_error_handling(
    category=ErrorCategory.VALIDATION,
    operation="advance_phase",
    error_code_prefix="SEC",
)
async def advance_phase(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: AdvancePhaseRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Advance to the next workflow phase.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Phase advance request
        manager: Workflow manager instance

    Returns:
        Updated assessment data
    """
    request_id = generate_request_id()

    assessment = await manager.advance_phase(
        assessment_id=assessment_id,
        reason=request.reason,
        target_phase=request.target_phase,
    )

    if not assessment:
        raise HTTPException(
            status_code=400, detail="Invalid phase transition or assessment not found"
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": assessment.to_dict(),
            "message": f"Advanced to phase: {assessment.phase.value}",
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/hosts")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="add_host",
    error_code_prefix="SEC",
)
async def add_host(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: AddHostRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Add a discovered host to the assessment.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Host data
        manager: Workflow manager instance

    Returns:
        Updated assessment data
    """
    request_id = generate_request_id()

    assessment = await manager.add_host(
        assessment_id=assessment_id,
        ip=request.ip,
        hostname=request.hostname,
        status=request.status,
        metadata=request.metadata,
    )

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": f"Added host: {request.ip}",
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/ports")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="add_port",
    error_code_prefix="SEC",
)
async def add_port(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: AddPortRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Add a discovered port to a host.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Port data
        manager: Workflow manager instance

    Returns:
        Confirmation
    """
    request_id = generate_request_id()

    assessment = await manager.add_port(
        assessment_id=assessment_id,
        host_ip=request.host_ip,
        port=request.port,
        protocol=request.protocol,
        state=request.state,
        service=request.service,
        version=request.version,
    )

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": f"Added port: {request.port}/{request.protocol} on {request.host_ip}",
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/vulnerabilities")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="add_vulnerability",
    error_code_prefix="SEC",
)
async def add_vulnerability(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: AddVulnerabilityRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Add a discovered vulnerability.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Vulnerability data
        manager: Workflow manager instance

    Returns:
        Confirmation
    """
    request_id = generate_request_id()

    assessment = await manager.add_vulnerability(
        assessment_id=assessment_id,
        host_ip=request.host_ip,
        cve_id=request.cve_id,
        title=request.title,
        severity=request.severity,
        description=request.description,
        affected_service=request.affected_service,
        affected_port=request.affected_port,
        metadata=request.metadata,
    )

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": f"Added vulnerability: {request.cve_id or request.title}",
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/findings")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="add_finding",
    error_code_prefix="SEC",
)
async def add_finding(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: AddFindingRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Add a general finding.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Finding data
        manager: Workflow manager instance

    Returns:
        Confirmation
    """
    request_id = generate_request_id()

    finding = {
        "type": request.finding_type,
        "description": request.description,
        **(request.data or {}),
    }

    assessment = await manager.add_finding(
        assessment_id=assessment_id,
        finding=finding,
    )

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": f"Added finding: {request.finding_type}",
            "request_id": request_id,
        },
    )


@router.get("/assessments/{assessment_id}/findings")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="get_findings",
    error_code_prefix="SEC",
)
async def get_findings(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    finding_type: Optional[str] = Query(None, description="Filter by type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Get assessment findings with optional filtering.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        finding_type: Filter by finding type
        severity: Filter by severity
        manager: Workflow manager instance

    Returns:
        List of findings
    """
    request_id = generate_request_id()

    assessment = await manager.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    findings = assessment.findings

    # Apply filters
    if finding_type:
        findings = [f for f in findings if f.get("type") == finding_type]

    if severity:
        findings = [
            f
            for f in findings
            if f.get("data", {}).get("severity") == severity
            or f.get("severity") == severity
        ]

    vulnerabilities = _collect_host_vulnerabilities(assessment, severity)

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "findings": findings,
                "vulnerabilities": vulnerabilities,
                "total_findings": len(findings),
                "total_vulnerabilities": len(vulnerabilities),
            },
            "request_id": request_id,
        },
    )


def _collect_host_vulnerabilities(assessment, severity: Optional[str]) -> list:
    """Helper for get_findings. Ref: #1088."""
    vulnerabilities = []
    for host in assessment.hosts:
        for vuln in host.vulnerabilities:
            if severity and vuln.get("severity") != severity:
                continue
            vulnerabilities.append(
                {
                    "type": "vulnerability",
                    "host": host.ip,
                    **vuln,
                }
            )
    return vulnerabilities


async def _store_parsed_hosts(manager, assessment_id: str, parsed) -> tuple[int, int]:
    """
    Store parsed hosts and their ports in the assessment.

    Issue #281: Extracted from parse_and_store_tool_output to reduce function length.

    Returns:
        Tuple of (hosts_added, ports_added) counts.
    """
    hosts_added = 0
    ports_added = 0

    for host in parsed.hosts:
        await manager.add_host(
            assessment_id=assessment_id,
            ip=host.ip,
            hostname=host.hostname,
            status=host.status,
            metadata={
                "mac_address": host.mac_address,
                "vendor": host.vendor,
                "os_guess": host.os_guess,
            },
        )
        hosts_added += 1

        for port in host.ports:
            await manager.add_port(
                assessment_id=assessment_id,
                host_ip=host.ip,
                port=port.get("port", 0),
                protocol=port.get("protocol", "tcp"),
                state=port.get("state", "open"),
                service=port.get("service"),
                version=port.get("version"),
            )
            ports_added += 1

    return hosts_added, ports_added


async def _store_parsed_vulnerabilities(manager, assessment_id: str, parsed) -> int:
    """
    Store parsed vulnerabilities in the assessment.

    Issue #281: Extracted from parse_and_store_tool_output to reduce function length.

    Returns:
        Number of vulnerabilities added.
    """
    vulns_added = 0
    for vuln in parsed.vulnerabilities:
        await manager.add_vulnerability(
            assessment_id=assessment_id,
            host_ip=vuln.host,
            cve_id=vuln.cve_id,
            title=vuln.title,
            severity=vuln.severity,
            description=vuln.description,
            affected_port=vuln.port,
            metadata=vuln.metadata,
        )
        vulns_added += 1
    return vulns_added


@router.post("/assessments/{assessment_id}/parse")
@with_error_handling(
    category=ErrorCategory.VALIDATION,
    operation="parse_tool_output",
    error_code_prefix="SEC",
)
async def parse_and_store_tool_output(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: ParseToolOutputRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Parse tool output and store results in the assessment.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Tool output to parse
        manager: Workflow manager instance

    Returns:
        Parsed data and storage confirmation
    """
    request_id = generate_request_id()

    # Verify assessment exists
    assessment = await manager.get_assessment(assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Parse the output
    parsed = parse_tool_output(request.output, request.tool)
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not parse tool output")

    # Store parsed data using extracted helpers
    hosts_added, ports_added = await _store_parsed_hosts(manager, assessment_id, parsed)
    vulns_added = await _store_parsed_vulnerabilities(manager, assessment_id, parsed)

    # Record the action
    await manager.record_action(
        assessment_id=assessment_id,
        action=f"Parsed {parsed.tool} output",
        tool=parsed.tool,
        command=parsed.command,
        result=f"Added {hosts_added} hosts, {ports_added} ports, {vulns_added} vulnerabilities",
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "tool": parsed.tool,
                "scan_type": parsed.scan_type,
                "hosts_added": hosts_added,
                "ports_added": ports_added,
                "vulnerabilities_added": vulns_added,
                "parsed_data": parsed.to_dict(),
            },
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/error")
@with_error_handling(
    category=ErrorCategory.NOT_FOUND,
    operation="set_error",
    error_code_prefix="SEC",
)
async def set_error_state(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    error_message: str = Query(..., description="Error message"),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Set assessment to error state.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        error_message: Error description
        manager: Workflow manager instance

    Returns:
        Updated assessment
    """
    request_id = generate_request_id()

    assessment = await manager.set_error(assessment_id, error_message)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": assessment.to_dict(),
            "request_id": request_id,
        },
    )


@router.post("/assessments/{assessment_id}/recover")
@with_error_handling(
    category=ErrorCategory.VALIDATION,
    operation="recover_from_error",
    error_code_prefix="SEC",
)
async def recover_from_error(
    assessment_id: str,
    admin_check: bool = Depends(check_admin_permission),
    request: RecoverErrorRequest = None,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Recover from error state.

    Issue #744: Requires admin authentication.

    Args:
        assessment_id: Assessment UUID
        admin_check: Admin permission verification
        request: Recovery parameters
        manager: Workflow manager instance

    Returns:
        Updated assessment
    """
    request_id = generate_request_id()

    assessment = await manager.recover_from_error(
        assessment_id=assessment_id,
        target_phase=request.target_phase,
        reason=request.reason,
    )

    if not assessment:
        raise HTTPException(
            status_code=400, detail="Recovery failed or assessment not found"
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": assessment.to_dict(),
            "message": f"Recovered to phase: {request.target_phase}",
            "request_id": request_id,
        },
    )


@router.get("/phases")
async def get_phase_definitions(
    admin_check: bool = Depends(check_admin_permission),
) -> JSONResponse:
    """
    Get all phase definitions and valid transitions.

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification

    Returns:
        Phase definitions and transition map
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "phases": {
                    phase.value: PHASE_DESCRIPTIONS.get(phase.value, {})
                    for phase in AssessmentPhase
                },
                "transitions": VALID_TRANSITIONS,
            },
        },
    )
