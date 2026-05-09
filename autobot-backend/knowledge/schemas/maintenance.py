# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for knowledge-base maintenance endpoints.

Issue #5317: wire all api/knowledge_maintenance.py endpoints into
``components.schemas`` in ``/openapi.json`` by declaring Pydantic
response models.

``extra="allow"`` throughout — maintenance operations carry dynamic
diagnostic fields that vary by KB implementation and the frontend
tolerates pass-through values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

# ===== DEDUPLICATION =====


class DeduplicateFactsResponse(BaseModel):
    """Shape of ``POST /deduplicate``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    dry_run: bool = True
    total_facts_scanned: int = 0
    unique_combinations: int = 0
    duplicate_groups_found: int = 0
    total_duplicates: int = 0
    deleted_count: int = 0
    duplicates: List[Any] = []


class FindDuplicatesResponse(BaseModel):
    """Shape of ``POST /deduplicate/advanced``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    total_facts_scanned: Optional[int] = None
    exact_duplicates: Optional[int] = None
    near_duplicates: Optional[int] = None
    total_duplicates: Optional[int] = None
    duplicates: Optional[List[Any]] = None


# ===== DATA QUALITY =====


class DataQualityMetricsResponse(BaseModel):
    """Shape of ``GET /quality``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    overall_score: Optional[float] = None
    dimensions: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    issues: Optional[List[Any]] = None
    recommendations: Optional[List[Any]] = None


class HealthDashboardResponse(BaseModel):
    """Shape of ``GET /health/dashboard``."""

    model_config = ConfigDict(extra="allow")

    status: str = "healthy"
    last_updated: str = ""
    stats: Optional[Dict[str, Any]] = None
    quality: Optional[Dict[str, Any]] = None
    top_recommendations: Optional[List[Any]] = None


# ===== HOST CHANGE SCANNING =====


class ScanHostChangesResponse(BaseModel):
    """Shape of ``POST /scan_host_changes``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    vectorization: Optional[Dict[str, Any]] = None


# ===== ORPHANED FACTS =====


class FindOrphanedFactsResponse(BaseModel):
    """Shape of ``GET /orphans``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    total_facts_checked: int = 0
    orphaned_count: int = 0
    orphaned_facts: List[Any] = []


class CleanupOrphanedFactsResponse(BaseModel):
    """Shape of ``DELETE /orphans``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    dry_run: Optional[bool] = None
    message: Optional[str] = None
    orphaned_count: Optional[int] = None
    deleted_count: int = 0
    orphaned_facts: Optional[List[Any]] = None


# ===== SESSION ORPHANS =====


class FindSessionOrphansResponse(BaseModel):
    """Shape of ``GET /session-orphans``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    total_facts_checked: int = 0
    facts_with_session_tracking: int = 0
    orphaned_count: int = 0
    orphaned_sessions: int = 0
    session_breakdown: Optional[Dict[str, Any]] = None
    orphaned_facts: List[Any] = []


class CleanupSessionOrphansResponse(BaseModel):
    """Shape of ``DELETE /session-orphans``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    dry_run: Optional[bool] = None
    message: Optional[str] = None
    orphaned_count: Optional[int] = None
    deleted_count: int = 0
    preserved_count: int = 0
    preserved_facts: Optional[List[Any]] = None
    session_breakdown: Optional[Dict[str, Any]] = None


# ===== IMPORT / EXPORT =====


class ScanUnimportedFilesResponse(BaseModel):
    """Shape of ``POST /import/scan``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    directory: str = ""
    unimported_files: List[str] = []
    needs_reimport: List[str] = []
    total_unimported: int = 0
    total_needs_reimport: int = 0


class ExportKnowledgeResponse(BaseModel):
    """Shape of ``POST /export``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    format: Optional[str] = None
    total_facts: Optional[int] = None
    data: Optional[str] = None
    exported_at: Optional[str] = None


class ImportKnowledgeResponse(BaseModel):
    """Shape of ``POST /import``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    total_facts: Optional[int] = None
    imported: Optional[int] = None
    skipped: Optional[int] = None
    overwritten: Optional[int] = None
    errors: Optional[List[Any]] = None
    validation_errors: Optional[List[Any]] = None


# ===== FACT MANAGEMENT =====


class UpdateFactResponse(BaseModel):
    """Shape of ``PUT /fact/{fact_id}``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    fact_id: str = ""
    updated_fields: List[str] = []
    vector_updated: bool = False
    message: str = ""


class DeleteFactResponse(BaseModel):
    """Shape of ``DELETE /fact/{fact_id}``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    fact_id: str = ""
    vector_deleted: bool = False
    message: str = ""


# ===== BULK OPERATIONS =====


class BulkDeleteResponse(BaseModel):
    """Shape of ``DELETE /bulk``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    deleted: Optional[int] = None
    not_found: Optional[int] = None
    errors: Optional[List[Any]] = None


class BulkCategoryUpdateResponse(BaseModel):
    """Shape of ``POST /bulk/category``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    updated: Optional[int] = None
    not_found: Optional[int] = None
    errors: Optional[List[Any]] = None


class CleanupKnowledgeBaseResponse(BaseModel):
    """Shape of ``POST /cleanup``."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    dry_run: Optional[bool] = None
    issues_found: Optional[Dict[str, Any]] = None
    issues_details: Optional[Dict[str, Any]] = None
    fixes_applied: Optional[Dict[str, Any]] = None


# ===== BACKUP / RESTORE =====


class CreateBackupResponse(BaseModel):
    """Shape of ``POST /backup``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    backup_file: Optional[str] = None
    backup_name: Optional[str] = None
    facts_count: Optional[int] = None
    file_size: Optional[int] = None
    created_at: Optional[str] = None


class RestoreBackupResponse(BaseModel):
    """Shape of ``POST /restore``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    mode: Optional[str] = None
    backup_version: Optional[str] = None
    backup_created_at: Optional[str] = None
    total_facts_in_backup: Optional[int] = None
    restored: Optional[int] = None
    skipped: Optional[int] = None
    updated: Optional[int] = None
    errors: Optional[int] = None


class ListBackupsResponse(BaseModel):
    """Shape of ``GET /backups``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    backup_dir: Optional[str] = None
    backups: List[Any] = []
    total_count: int = 0


class DeleteBackupResponse(BaseModel):
    """Shape of ``DELETE /backup``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    deleted_file: Optional[str] = None


# ===== LINT =====


class StartLintResponse(BaseModel):
    """Shape of ``POST /lint``."""

    model_config = ConfigDict(extra="allow")

    status: str = "started"
    job_id: str = ""


class GetLintReportResponse(BaseModel):
    """Shape of ``GET /lint/report`` — mirrors ContradictionReport fields."""

    model_config = ConfigDict(extra="allow")

    job_id: Optional[str] = None
    contradictions: Optional[List[Any]] = None
    gaps: Optional[List[Any]] = None
    scanned_at: Optional[str] = None


class SynthesisLogResponse(BaseModel):
    """Shape of ``GET /synthesis/log``."""

    model_config = ConfigDict(extra="allow")

    entries: List[Any] = []
    count: int = 0
