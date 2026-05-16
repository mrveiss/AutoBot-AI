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

from typing import Any, Dict, List

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

    status: str | None = None
    total_facts_scanned: int | None = None
    exact_duplicates: int | None = None
    near_duplicates: int | None = None
    total_duplicates: int | None = None
    duplicates: List[Any] | None = None


# ===== DATA QUALITY =====


class DataQualityMetricsResponse(BaseModel):
    """Shape of ``GET /quality``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    overall_score: float | None = None
    dimensions: Dict[str, Any] | None = None
    summary: Dict[str, Any] | None = None
    issues: List[Any] | None = None
    recommendations: List[Any] | None = None


class HealthDashboardResponse(BaseModel):
    """Shape of ``GET /health/dashboard``."""

    model_config = ConfigDict(extra="allow")

    status: str = "healthy"
    last_updated: str = ""
    stats: Dict[str, Any] | None = None
    quality: Dict[str, Any] | None = None
    top_recommendations: List[Any] | None = None


# ===== HOST CHANGE SCANNING =====


class ScanHostChangesResponse(BaseModel):
    """Shape of ``POST /scan_host_changes``."""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    changes: Dict[str, Any] | None = None
    vectorization: Dict[str, Any] | None = None


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
    dry_run: bool | None = None
    message: str | None = None
    orphaned_count: int | None = None
    deleted_count: int = 0
    orphaned_facts: List[Any] | None = None


# ===== SESSION ORPHANS =====


class FindSessionOrphansResponse(BaseModel):
    """Shape of ``GET /session-orphans``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    total_facts_checked: int = 0
    facts_with_session_tracking: int = 0
    orphaned_count: int = 0
    orphaned_sessions: int = 0
    session_breakdown: Dict[str, Any] | None = None
    orphaned_facts: List[Any] = []


class CleanupSessionOrphansResponse(BaseModel):
    """Shape of ``DELETE /session-orphans``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    dry_run: bool | None = None
    message: str | None = None
    orphaned_count: int | None = None
    deleted_count: int = 0
    preserved_count: int = 0
    preserved_facts: List[Any] | None = None
    session_breakdown: Dict[str, Any] | None = None


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

    status: str | None = None
    format: str | None = None
    total_facts: int | None = None
    data: str | None = None
    exported_at: str | None = None


class ImportKnowledgeResponse(BaseModel):
    """Shape of ``POST /import``."""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    total_facts: int | None = None
    imported: int | None = None
    skipped: int | None = None
    overwritten: int | None = None
    errors: List[Any] | None = None
    validation_errors: List[Any] | None = None


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

    status: str | None = None
    deleted: int | None = None
    not_found: int | None = None
    errors: List[Any] | None = None


class BulkCategoryUpdateResponse(BaseModel):
    """Shape of ``POST /bulk/category``."""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    updated: int | None = None
    not_found: int | None = None
    errors: List[Any] | None = None


class CleanupKnowledgeBaseResponse(BaseModel):
    """Shape of ``POST /cleanup``."""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    dry_run: bool | None = None
    issues_found: Dict[str, Any] | None = None
    issues_details: Dict[str, Any] | None = None
    fixes_applied: Dict[str, Any] | None = None


# ===== BACKUP / RESTORE =====


class CreateBackupResponse(BaseModel):
    """Shape of ``POST /backup``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    backup_file: str | None = None
    backup_name: str | None = None
    facts_count: int | None = None
    file_size: int | None = None
    created_at: str | None = None


class RestoreBackupResponse(BaseModel):
    """Shape of ``POST /restore``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    mode: str | None = None
    backup_version: str | None = None
    backup_created_at: str | None = None
    total_facts_in_backup: int | None = None
    restored: int | None = None
    skipped: int | None = None
    updated: int | None = None
    errors: int | None = None


class ListBackupsResponse(BaseModel):
    """Shape of ``GET /backups``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    backup_dir: str | None = None
    backups: List[Any] = []
    total_count: int = 0


class DeleteBackupResponse(BaseModel):
    """Shape of ``DELETE /backup``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    deleted_file: str | None = None


# ===== LINT =====


class StartLintResponse(BaseModel):
    """Shape of ``POST /lint``."""

    model_config = ConfigDict(extra="allow")

    status: str = "started"
    job_id: str = ""


class GetLintReportResponse(BaseModel):
    """Shape of ``GET /lint/report`` — mirrors ContradictionReport fields."""

    model_config = ConfigDict(extra="allow")

    job_id: str | None = None
    contradictions: List[Any] | None = None
    gaps: List[Any] | None = None
    scanned_at: str | None = None


class SynthesisLogResponse(BaseModel):
    """Shape of ``GET /synthesis/log``."""

    model_config = ConfigDict(extra="allow")

    entries: List[Any] = []
    count: int = 0
