# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pydantic models for codebase analytics API
"""

from typing import List, Optional

from pydantic import BaseModel


class CodebaseStats(BaseModel):
    """Statistics about the codebase"""
    total_files: int
    total_lines: int
    python_files: int
    javascript_files: int
    vue_files: int
    other_files: int
    total_functions: int
    total_classes: int
    average_file_size: float
    last_indexed: str


class ProblemItem(BaseModel):
    """Represents a code problem or issue"""
    type: str
    severity: str
    file_path: str
    line_number: Optional[int]
    description: str
    suggestion: str


class HardcodeItem(BaseModel):
    """Represents a hardcoded value in the codebase"""
    file_path: str
    line_number: int
    type: str  # 'url', 'path', 'ip', 'port', 'api_key', 'string'
    value: str
    context: str


class DeclarationItem(BaseModel):
    """Represents a code declaration (function, class, variable)"""
    name: str
    type: str  # 'function', 'class', 'variable'
    file_path: str
    line_number: int
    usage_count: int
    is_exported: bool
    parameters: Optional[List[str]]


# =============================================================================
# API Endpoint Checker Models (Issue #527)
# =============================================================================


class APIEndpointItem(BaseModel):
    """Represents a backend API endpoint definition"""
    method: str  # 'GET', 'POST', 'PUT', 'DELETE', 'PATCH'
    path: str  # Full API path (e.g., '/api/monitoring/status')
    file_path: str  # Source file containing the endpoint
    line_number: int  # Line number of decorator
    function_name: str  # Handler function name
    router_prefix: Optional[str] = None  # Router prefix if any
    tags: Optional[List[str]] = None  # API tags
    is_async: bool = False  # Whether handler is async


class FrontendAPICallItem(BaseModel):
    """Represents a frontend API call"""
    method: str  # 'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'UNKNOWN'
    path: str  # API path called (may include variables)
    file_path: str  # Source file containing the call
    line_number: int  # Line number of call
    context: Optional[str] = None  # Surrounding code context
    is_dynamic: bool = False  # True if path contains variables/templates


class EndpointUsageItem(BaseModel):
    """Represents an endpoint with its usage information"""
    endpoint: APIEndpointItem
    call_count: int  # Number of frontend calls
    callers: List[FrontendAPICallItem]  # List of frontend locations calling this


class EndpointMismatchItem(BaseModel):
    """Represents an orphaned or missing endpoint"""
    type: str  # 'orphaned' (no frontend calls) or 'missing' (no backend endpoint)
    method: str
    path: str
    file_path: str
    line_number: int
    details: Optional[str] = None


class APIEndpointAnalysis(BaseModel):
    """Complete API endpoint analysis result"""
    backend_endpoints: int
    frontend_calls: int
    used_endpoints: int
    orphaned_endpoints: int
    missing_endpoints: int
    coverage_percentage: float
    endpoints: List[APIEndpointItem]
    api_calls: List[FrontendAPICallItem]
    orphaned: List[EndpointMismatchItem]
    missing: List[EndpointMismatchItem]
    used: List[EndpointUsageItem]
    scan_timestamp: str
