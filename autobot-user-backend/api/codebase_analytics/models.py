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


# =============================================================================
# Cross-Language Pattern Detection Models (Issue #244)
# =============================================================================


class PatternLocationItem(BaseModel):
    """Location of a pattern in source code"""

    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    language: str = "unknown"


class DTOMismatchItem(BaseModel):
    """Mismatch between backend and frontend data types"""

    mismatch_id: str
    backend_type: str
    frontend_type: str
    backend_location: Optional[PatternLocationItem] = None
    frontend_location: Optional[PatternLocationItem] = None
    field_name: str
    mismatch_type: str  # "missing_field", "type_mismatch", "optional_mismatch"
    backend_definition: str = ""
    frontend_definition: str = ""
    severity: str = "high"
    recommendation: str = ""


class ValidationDuplicationItem(BaseModel):
    """Duplicated validation logic across languages"""

    duplication_id: str
    validation_type: str  # "email", "phone", "required", etc.
    python_location: Optional[PatternLocationItem] = None
    typescript_location: Optional[PatternLocationItem] = None
    python_code: str = ""
    typescript_code: str = ""
    similarity_score: float = 0.0
    severity: str = "medium"
    recommendation: str = ""


class APIContractMismatchItem(BaseModel):
    """Mismatch between backend API endpoint and frontend API call"""

    mismatch_id: str
    endpoint_path: str
    http_method: str
    mismatch_type: str  # "missing_endpoint", "orphaned_endpoint", "method_mismatch"
    backend_location: Optional[PatternLocationItem] = None
    frontend_location: Optional[PatternLocationItem] = None
    backend_definition: str = ""
    frontend_call: str = ""
    severity: str = "critical"
    details: str = ""
    recommendation: str = ""


class PatternMatchItem(BaseModel):
    """A match between patterns in different languages"""

    pattern_id: str
    similarity_score: float  # 0.0 to 1.0
    source_location: Optional[PatternLocationItem] = None
    target_location: Optional[PatternLocationItem] = None
    source_code: str = ""
    target_code: str = ""
    match_type: str = "semantic"  # "semantic", "structural", "exact"
    confidence: float = 1.0


class CrossLanguagePatternItem(BaseModel):
    """A pattern detected across multiple languages"""

    pattern_id: str
    pattern_type: str
    category: str
    severity: str
    name: str
    description: str
    python_locations: List[PatternLocationItem] = []
    typescript_locations: List[PatternLocationItem] = []
    vue_locations: List[PatternLocationItem] = []
    python_code: str = ""
    typescript_code: str = ""
    confidence: float = 1.0
    recommendation: str = ""
    tags: List[str] = []


class CrossLanguageAnalysisSummary(BaseModel):
    """Summary of cross-language analysis results"""

    analysis_id: str
    scan_timestamp: str
    python_files_analyzed: int
    typescript_files_analyzed: int
    vue_files_analyzed: int
    total_patterns: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    dto_mismatches_count: int
    validation_duplications_count: int
    api_contract_mismatches_count: int
    semantic_matches_count: int
    analysis_time_ms: float
    embeddings_generated: int
    cache_hits: int
    cache_misses: int


class CrossLanguageAnalysisResult(BaseModel):
    """Complete cross-language analysis result"""

    analysis_id: str
    scan_timestamp: str
    files_analyzed: dict
    statistics: dict
    performance: dict
    patterns: List[CrossLanguagePatternItem]
    dto_mismatches: List[DTOMismatchItem]
    validation_duplications: List[ValidationDuplicationItem]
    api_contract_mismatches: List[APIContractMismatchItem]
    pattern_matches: List[PatternMatchItem]
    errors: List[str] = []
