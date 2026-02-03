# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data models for cross-language pattern detection.

Issue #244: Models for representing patterns, matches, and analysis results
across Python and TypeScript/JavaScript codebases.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PatternType(Enum):
    """Types of cross-language patterns detected."""

    # API Contract Patterns
    API_ENDPOINT = "api_endpoint"
    API_CALL = "api_call"
    API_CONTRACT_MISMATCH = "api_contract_mismatch"

    # Data Transfer Objects
    DTO_DEFINITION = "dto_definition"
    DTO_MISMATCH = "dto_mismatch"
    TYPE_DEFINITION = "type_definition"

    # Validation Patterns
    VALIDATION_RULE = "validation_rule"
    VALIDATION_DUPLICATION = "validation_duplication"

    # Business Logic
    BUSINESS_LOGIC = "business_logic"
    LOGIC_DUPLICATION = "logic_duplication"

    # Error Handling
    ERROR_HANDLING = "error_handling"
    ERROR_PATTERN = "error_pattern"

    # Async Patterns
    ASYNC_CALLBACK = "async_callback"
    PROMISE_PATTERN = "promise_pattern"

    # Other
    UTILITY_FUNCTION = "utility_function"
    CONSTANT_DEFINITION = "constant_definition"


class PatternSeverity(Enum):
    """Severity levels for pattern issues."""

    CRITICAL = "critical"  # API contract breaks, type mismatches
    HIGH = "high"  # Significant duplications
    MEDIUM = "medium"  # Minor inconsistencies
    LOW = "low"  # Suggestions for improvement
    INFO = "info"  # Informational findings


class PatternCategory(Enum):
    """Categories for organizing patterns."""

    API_CONTRACT = "api_contract"
    DATA_TYPES = "data_types"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"
    ERROR_HANDLING = "error_handling"
    ASYNC_PATTERNS = "async_patterns"
    UTILITIES = "utilities"


@dataclass
class PatternLocation:
    """Location of a pattern in source code."""

    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    language: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "column_start": self.column_start,
            "column_end": self.column_end,
            "language": self.language,
        }


@dataclass
class PatternMatch:
    """A match between patterns in different languages."""

    pattern_id: str
    similarity_score: float  # 0.0 to 1.0
    source_location: PatternLocation
    target_location: PatternLocation
    source_code: str
    target_code: str
    match_type: str  # "semantic", "structural", "exact"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "similarity_score": self.similarity_score,
            "source_location": self.source_location.to_dict(),
            "target_location": self.target_location.to_dict(),
            "source_code": self.source_code,
            "target_code": self.target_code,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class CrossLanguagePattern:
    """A pattern that appears across multiple languages."""

    pattern_id: str
    pattern_type: PatternType
    category: PatternCategory
    severity: PatternSeverity
    name: str
    description: str

    # Language implementations
    python_locations: List[PatternLocation] = field(default_factory=list)
    typescript_locations: List[PatternLocation] = field(default_factory=list)
    vue_locations: List[PatternLocation] = field(default_factory=list)

    # Code representations
    python_code: str = ""
    typescript_code: str = ""
    normalized_representation: str = ""

    # Vector embedding for semantic search
    embedding: Optional[List[float]] = None
    embedding_model: str = ""

    # Metadata
    confidence: float = 1.0
    detected_at: datetime = field(default_factory=datetime.now)
    recommendation: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """Generate hash of pattern content for deduplication."""
        content = f"{self.normalized_representation}:{self.pattern_type.value}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "category": self.category.value,
            "severity": self.severity.value,
            "name": self.name,
            "description": self.description,
            "python_locations": [loc.to_dict() for loc in self.python_locations],
            "typescript_locations": [loc.to_dict() for loc in self.typescript_locations],
            "vue_locations": [loc.to_dict() for loc in self.vue_locations],
            "python_code": self.python_code,
            "typescript_code": self.typescript_code,
            "normalized_representation": self.normalized_representation,
            "confidence": self.confidence,
            "detected_at": self.detected_at.isoformat(),
            "recommendation": self.recommendation,
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class DTOMismatch:
    """Mismatch between backend and frontend data types."""

    mismatch_id: str
    backend_type: str
    frontend_type: str
    backend_location: PatternLocation
    frontend_location: PatternLocation
    field_name: str
    mismatch_type: str  # "missing_field", "type_mismatch", "optional_mismatch"
    backend_definition: str = ""
    frontend_definition: str = ""
    severity: PatternSeverity = PatternSeverity.HIGH
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mismatch_id": self.mismatch_id,
            "backend_type": self.backend_type,
            "frontend_type": self.frontend_type,
            "backend_location": self.backend_location.to_dict(),
            "frontend_location": self.frontend_location.to_dict(),
            "field_name": self.field_name,
            "mismatch_type": self.mismatch_type,
            "backend_definition": self.backend_definition,
            "frontend_definition": self.frontend_definition,
            "severity": self.severity.value,
            "recommendation": self.recommendation,
        }


@dataclass
class ValidationDuplication:
    """Duplicated validation logic across languages."""

    duplication_id: str
    validation_type: str  # "email", "phone", "required", "range", "regex", etc.
    python_location: Optional[PatternLocation] = None
    typescript_location: Optional[PatternLocation] = None
    python_code: str = ""
    typescript_code: str = ""
    similarity_score: float = 0.0
    severity: PatternSeverity = PatternSeverity.MEDIUM
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "duplication_id": self.duplication_id,
            "validation_type": self.validation_type,
            "python_location": self.python_location.to_dict() if self.python_location else None,
            "typescript_location": self.typescript_location.to_dict() if self.typescript_location else None,
            "python_code": self.python_code,
            "typescript_code": self.typescript_code,
            "similarity_score": self.similarity_score,
            "severity": self.severity.value,
            "recommendation": self.recommendation,
        }


@dataclass
class APIContractMismatch:
    """Mismatch between backend API endpoint and frontend API call."""

    mismatch_id: str
    endpoint_path: str
    http_method: str
    mismatch_type: str  # "missing_endpoint", "orphaned_endpoint", "method_mismatch", "param_mismatch"
    backend_location: Optional[PatternLocation] = None
    frontend_location: Optional[PatternLocation] = None
    backend_definition: str = ""
    frontend_call: str = ""
    severity: PatternSeverity = PatternSeverity.CRITICAL
    details: str = ""
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mismatch_id": self.mismatch_id,
            "endpoint_path": self.endpoint_path,
            "http_method": self.http_method,
            "mismatch_type": self.mismatch_type,
            "backend_location": self.backend_location.to_dict() if self.backend_location else None,
            "frontend_location": self.frontend_location.to_dict() if self.frontend_location else None,
            "backend_definition": self.backend_definition,
            "frontend_call": self.frontend_call,
            "severity": self.severity.value,
            "details": self.details,
            "recommendation": self.recommendation,
        }


@dataclass
class CrossLanguageAnalysis:
    """Complete cross-language analysis result."""

    analysis_id: str
    scan_timestamp: datetime = field(default_factory=datetime.now)

    # Files analyzed
    python_files_analyzed: int = 0
    typescript_files_analyzed: int = 0
    vue_files_analyzed: int = 0

    # Pattern results
    patterns: List[CrossLanguagePattern] = field(default_factory=list)
    dto_mismatches: List[DTOMismatch] = field(default_factory=list)
    validation_duplications: List[ValidationDuplication] = field(default_factory=list)
    api_contract_mismatches: List[APIContractMismatch] = field(default_factory=list)

    # Pattern matches (cross-language similarities)
    pattern_matches: List[PatternMatch] = field(default_factory=list)

    # Statistics
    total_patterns: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0

    # Performance
    analysis_time_ms: float = 0.0
    embeddings_generated: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    def calculate_stats(self) -> None:
        """Calculate statistics from patterns."""
        self.total_patterns = len(self.patterns)
        self.critical_issues = sum(
            1 for p in self.patterns if p.severity == PatternSeverity.CRITICAL
        )
        self.high_issues = sum(
            1 for p in self.patterns if p.severity == PatternSeverity.HIGH
        )
        self.medium_issues = sum(
            1 for p in self.patterns if p.severity == PatternSeverity.MEDIUM
        )
        self.low_issues = sum(
            1 for p in self.patterns if p.severity == PatternSeverity.LOW
        )

        # Add mismatches to counts
        self.critical_issues += len(self.api_contract_mismatches)
        self.high_issues += len(self.dto_mismatches)
        self.medium_issues += len(self.validation_duplications)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "analysis_id": self.analysis_id,
            "scan_timestamp": self.scan_timestamp.isoformat(),
            "files_analyzed": {
                "python": self.python_files_analyzed,
                "typescript": self.typescript_files_analyzed,
                "vue": self.vue_files_analyzed,
                "total": (
                    self.python_files_analyzed +
                    self.typescript_files_analyzed +
                    self.vue_files_analyzed
                ),
            },
            "statistics": {
                "total_patterns": self.total_patterns,
                "critical_issues": self.critical_issues,
                "high_issues": self.high_issues,
                "medium_issues": self.medium_issues,
                "low_issues": self.low_issues,
                "dto_mismatches": len(self.dto_mismatches),
                "validation_duplications": len(self.validation_duplications),
                "api_contract_mismatches": len(self.api_contract_mismatches),
                "pattern_matches": len(self.pattern_matches),
            },
            "performance": {
                "analysis_time_ms": self.analysis_time_ms,
                "embeddings_generated": self.embeddings_generated,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            },
            "patterns": [p.to_dict() for p in self.patterns],
            "dto_mismatches": [m.to_dict() for m in self.dto_mismatches],
            "validation_duplications": [v.to_dict() for v in self.validation_duplications],
            "api_contract_mismatches": [a.to_dict() for a in self.api_contract_mismatches],
            "pattern_matches": [m.to_dict() for m in self.pattern_matches],
            "errors": self.errors,
        }
