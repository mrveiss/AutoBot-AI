// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * API Contract Types (Issue #5209)
 *
 * SINGLE SOURCE OF TRUTH for API-contract types shared between backend and frontend.
 *
 * This module re-exports auto-generated OpenAPI types with ergonomic aliases.
 * The generated file `./generated/api.ts` is produced by `npm run gen:types` from
 * the backend's live `/openapi.json` — never hand-edit it.
 *
 * HOW TO EXTEND:
 *   1. Add an alias below for a schema that exists in `components['schemas']`.
 *   2. Migrate hand-written duplicate in `./knowledgeBase.ts` (or similar) to
 *      import from `@/types/api-contract` instead.
 *   3. Delete the hand-written interface only once all call sites compile.
 *
 * WHY: Hand-maintained duplicates between Python models and TS interfaces drift
 * silently — see #5200 for a live production bug caused by this drift class.
 *
 * @see docs/developer/frontend-type-generation.md
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */
import type { components } from './generated/api'

// =============================================================================
// Issue #5248 — Knowledge base stats + categories (knowledge/schemas/stats.py)
//
// These use the conditional fallback pattern because they were added before
// the first `npm run gen:types` run that included #5317 schemas. After
// regeneration, the `components['schemas']` lookup takes over automatically.
// =============================================================================

/** `GET /api/knowledge_base/stats/basic` response. */
export type KnowledgeStatsBasic = components['schemas'] extends {
  KnowledgeStatsBasic: infer T
}
  ? T
  : {
      status: string
      total_facts: number
      total_vectors: number
      categories: string[]
    }

/** `GET /api/knowledge_base/detailed_stats` response. */
export type DetailedKnowledgeStats = components['schemas'] extends {
  DetailedKnowledgeStats: infer T
}
  ? T
  : {
      status: string
      basic_stats: Record<string, unknown>
      category_breakdown: Record<string, number>
      source_breakdown: Record<string, number>
      type_breakdown: Record<string, number>
      size_metrics: Record<string, number>
      rag_available: boolean
      message?: string
    }

/** Single row of `GET /api/knowledge_base/categories`. */
export type KnowledgeCategoryEntry = components['schemas'] extends {
  KnowledgeCategoryEntry: infer T
}
  ? T
  : { id: string; name: string; count: number }

/** `GET /api/knowledge_base/categories` response. */
export type KnowledgeCategoriesResponse = components['schemas'] extends {
  KnowledgeCategoriesResponse: infer T
}
  ? T
  : { categories: KnowledgeCategoryEntry[]; total: number }

/** `GET /api/knowledge_base/categories/main` response. */
export type KnowledgeMainCategoriesResponse = components['schemas'] extends {
  KnowledgeMainCategoriesResponse: infer T
}
  ? T
  : {
      categories: Array<{
        id: string
        name: string
        description: string
        icon: string
        color: string
        examples: string[]
        count: number
      }>
      total: number
    }

// =============================================================================
// Issue #5317 — All remaining KB API schemas.
//
// These use the direct alias pattern (simple string key lookup). They resolve
// to `never` until `npm run gen:types` regenerates `./generated/api.ts` against
// a live backend with the #5317 response_model= annotations deployed.
// After regeneration, no code change is needed — aliases pick up the types.
// =============================================================================

// --- knowledge/schemas/connectors.py -----------------------------------------

/** Request body for `POST /knowledge_base/connectors`. */
export type CreateConnectorRequest = components['schemas']['CreateConnectorRequest']

/** Request body for `PUT /knowledge_base/connectors/{id}`. */
export type UpdateConnectorRequest = components['schemas']['UpdateConnectorRequest']

/** Single entry in the connector types list. */
export type ConnectorTypeEntry = components['schemas']['ConnectorTypeEntry']

/** `GET /knowledge_base/connector_types` response. */
export type ConnectorTypesResponse = components['schemas']['ConnectorTypesResponse']

/** Connector status sub-object. */
export type ConnectorStatusDict = components['schemas']['ConnectorStatusDict']

/** Connector config sub-object. */
export type ConnectorConfigDict = components['schemas']['ConnectorConfigDict']

/** Single connector entry (config + status). */
export type ConnectorEntry = components['schemas']['ConnectorEntry']

/** `GET /knowledge_base/connectors` response. */
export type ConnectorsListResponse = components['schemas']['ConnectorsListResponse']

/** `POST /knowledge_base/connectors` (201) response. */
export type ConnectorCreateResponse = components['schemas']['ConnectorCreateResponse']

/** `GET /knowledge_base/connectors/health` response. */
export type ConnectorsHealthResponse = components['schemas']['ConnectorsHealthResponse']

/** `GET /knowledge_base/connectors/{id}` response. */
export type ConnectorDetailResponse = components['schemas']['ConnectorDetailResponse']

/** `PUT /knowledge_base/connectors/{id}` response. */
export type ConnectorUpdateResponse = components['schemas']['ConnectorUpdateResponse']

/** `POST /knowledge_base/connectors/{id}/test` response. */
export type ConnectorTestResponse = components['schemas']['ConnectorTestResponse']

/** `POST /knowledge_base/connectors/{id}/sync` response. */
export type ConnectorSyncResponse = components['schemas']['ConnectorSyncResponse']

/** Single sync history record. */
export type ConnectorHistoryEntry = components['schemas']['ConnectorHistoryEntry']

/** `GET /knowledge_base/connectors/{id}/history` response. */
export type ConnectorHistoryResponse = components['schemas']['ConnectorHistoryResponse']

// --- knowledge/schemas/facts.py -----------------------------------------------

/** `POST /add_text` response. */
export type AddTextResponse = components['schemas']['AddTextResponse']

/** `POST /add_fact` response. */
export type AddFactResponse = components['schemas']['AddFactResponse']

/** `POST /add_url` response. */
export type AddUrlResponse = components['schemas']['AddUrlResponse']

/** `POST /upload_file` response. */
export type UploadFileResponse = components['schemas']['UploadFileResponse']

/** `POST /audio_ingest` response. */
export type AudioIngestResponse = components['schemas']['AudioIngestResponse']

/** Single knowledge entry. */
export type KnowledgeEntry = components['schemas']['KnowledgeEntry']

/** `GET /knowledge_entries` response. */
export type KnowledgeEntriesResponse = components['schemas']['KnowledgeEntriesResponse']

/** Single row of a facts-by-category response. */
export type FactByCategoryEntry = components['schemas']['FactByCategoryEntry']

/** `GET /facts_by_category` response. */
export type FactsByCategoryResponse = components['schemas']['FactsByCategoryResponse']

/** `GET /fact/{key}` response. */
export type FactByKeyResponse = components['schemas']['FactByKeyResponse']

/** `DELETE /clear_all` response. */
// #9724: schema is now namespaced in the generated contract
export type ClearAllResponse = components['schemas']['knowledge__schemas__ingestion__ClearAllResponse']

/** `POST /query_knowledge` response. */
export type QueryKnowledgeResponse = components['schemas']['QueryKnowledgeResponse']

/** `GET /man_pages/search` response. */
export type ManPageSearchResponse = components['schemas']['ManPageSearchResponse']

// --- knowledge/schemas/documents.py -------------------------------------------

/** `GET /knowledge_base/docs` response. */
export type DocsBrowseResponse = components['schemas']['DocsBrowseResponse']

/** `GET /knowledge_base/docs/categories` response. */
export type DocsCategoriesResponse = components['schemas']['DocsCategoriesResponse']

/** Single category entry in docs response. */
export type DocsCategoryEntry = components['schemas']['DocsCategoryEntry']

/** Filters applied in docs browse response. */
export type DocsFiltersApplied = components['schemas']['DocsFiltersApplied']

/** Pagination metadata in docs browse response. */
export type DocsPagination = components['schemas']['DocsPagination']

/** `GET /knowledge_base/docs/stats` envelope. */
export type DocsStatsEnvelope = components['schemas']['DocsStatsEnvelope']

/** `GET /knowledge_base/docs/stats` response. */
export type DocsStatsResponse = components['schemas']['DocsStatsResponse']

/** `GET /knowledge_base/docs/watcher/status` response. */
export type DocsWatcherStatusResponse = components['schemas']['DocsWatcherStatusResponse']

/** `POST /knowledge_base/docs/watcher/{action}` response. */
export type DocsWatcherControlResponse = components['schemas']['DocsWatcherControlResponse']

// --- knowledge/schemas/operations.py ------------------------------------------

/** `GET /knowledge_base/stats` response. */
export type KnowledgeStatsResponse = components['schemas']['KnowledgeStatsResponse']

/**
 * `GET /knowledge_base/health/status` response.
 * #9724: the legacy flat `KnowledgeHealthResponse` schema no longer exists in
 * the generated contract — the health surface moved to the health/status endpoint.
 */
export type KnowledgeHealthResponse = components['schemas']['DataResponse_AIStackHealthStatusData_']

/** Machine profile capabilities sub-object. */
export type MachineProfileCapabilities = components['schemas']['MachineProfileCapabilities']

/** `GET /knowledge_base/machine_profile` response. */
export type MachineProfileResponse = components['schemas']['MachineProfileResponse']

/** Man pages summary sub-object. */
export type ManPagesSummaryResponse = components['schemas']['ManPagesSummaryResponse']

/** `GET /knowledge_base/man_pages/summary` envelope. */
export type ManPagesSummaryEnvelope = components['schemas']['ManPagesSummaryEnvelope']

/** Machine knowledge init components sub-object. */
export type MachineKnowledgeInitComponents = components['schemas']['MachineKnowledgeInitComponents']

/** `POST /knowledge_base/machine_knowledge/init` response. */
export type MachineKnowledgeInitResponse = components['schemas']['MachineKnowledgeInitResponse']

/** `POST /knowledge_base/man_pages/integrate` response. */
export type ManPagesIntegrateResponse = components['schemas']['ManPagesIntegrateResponse']

/** `GET /knowledge_base/import/status` response. */
export type ImportStatusResponse = components['schemas']['ImportStatusResponse']

/** `GET /knowledge_base/import/statistics` response. */
export type ImportStatisticsResponse = components['schemas']['ImportStatisticsResponse']

/** `GET /knowledge_base/org_knowledge/config` response. */
export type OrgKnowledgeConfigResponse = components['schemas']['OrgKnowledgeConfigResponse']

/** `GET /knowledge_base/test_categories` response. */
export type TestCategoriesResponse = components['schemas']['TestCategoriesResponse']

// --- knowledge/schemas/search.py ----------------------------------------------

/** `POST /search` response. */
export type KnowledgeSearchResponse = components['schemas']['KnowledgeSearchResponse']

/** `GET /search/analytics` response. */
export type SearchAnalyticsResponse = components['schemas']['SearchAnalyticsResponse']

/** `POST /search/record_click` response. */
export type RecordClickResponse = components['schemas']['RecordClickResponse']

/** `POST /search/expand_query` response. */
export type ExpandQueryResponse = components['schemas']['ExpandQueryResponse']

// --- knowledge/schemas/maintenance.py -----------------------------------------

/** `PUT /knowledge_base/facts/{id}` response. */
export type UpdateFactResponse = components['schemas']['UpdateFactResponse']

/** `DELETE /knowledge_base/facts/{id}` response. */
export type DeleteFactResponse = components['schemas']['DeleteFactResponse']

/** `POST /knowledge_base/export` response. */
export type ExportKnowledgeResponse = components['schemas']['ExportKnowledgeResponse']

/** `POST /knowledge_base/import` response. */
export type ImportKnowledgeResponse = components['schemas']['ImportKnowledgeResponse']

/** `POST /knowledge_base/cleanup` response. */
export type CleanupKnowledgeBaseResponse = components['schemas']['CleanupKnowledgeBaseResponse']

/** `POST /knowledge_base/deduplicate` response. */
export type DeduplicateFactsResponse = components['schemas']['DeduplicateFactsResponse']

/** `POST /knowledge_base/find_duplicates` response. */
export type FindDuplicatesResponse = components['schemas']['FindDuplicatesResponse']

/** `GET /knowledge_base/orphaned_facts` response. */
export type FindOrphanedFactsResponse = components['schemas']['FindOrphanedFactsResponse']

/** `DELETE /knowledge_base/orphaned_facts` response. */
export type CleanupOrphanedFactsResponse = components['schemas']['CleanupOrphanedFactsResponse']

/** `GET /knowledge_base/session_orphans` response. */
export type FindSessionOrphansResponse = components['schemas']['FindSessionOrphansResponse']

/** `DELETE /knowledge_base/session_orphans` response. */
export type CleanupSessionOrphansResponse = components['schemas']['CleanupSessionOrphansResponse']

/** `POST /knowledge_base/backup` response. */
export type CreateBackupResponse = components['schemas']['CreateBackupResponse']

/** `GET /knowledge_base/backups` response. */
export type ListBackupsResponse = components['schemas']['ListBackupsResponse']

/** `POST /knowledge_base/restore` response. */
export type RestoreBackupResponse = components['schemas']['RestoreBackupResponse']

/** `DELETE /knowledge_base/backup/{id}` response. */
export type DeleteBackupResponse = components['schemas']['DeleteBackupResponse']

/** `POST /knowledge_base/bulk_category_update` response. */
export type BulkCategoryUpdateResponse = components['schemas']['BulkCategoryUpdateResponse']

/** `DELETE /knowledge_base/facts/bulk` response. */
export type BulkDeleteResponse = components['schemas']['BulkDeleteResponse']

/** `POST /knowledge_base/scan_host_changes` response. */
export type ScanHostChangesResponse = components['schemas']['ScanHostChangesResponse']

/** `POST /knowledge_base/scan_unimported_files` response. */
export type ScanUnimportedFilesResponse = components['schemas']['ScanUnimportedFilesResponse']

/** `GET /knowledge_base/data_quality` response. */
export type DataQualityMetricsResponse = components['schemas']['DataQualityMetricsResponse']

/** `GET /knowledge_base/health_dashboard` response. */
export type HealthDashboardResponse = components['schemas']['HealthDashboardResponse']

/** `POST /knowledge_base/lint/start` response. */
export type StartLintResponse = components['schemas']['StartLintResponse']

/** `GET /knowledge_base/lint/report` response. */
export type GetLintReportResponse = components['schemas']['GetLintReportResponse']

/** `GET /knowledge_base/synthesis_log` response. */
export type SynthesisLogResponse = components['schemas']['SynthesisLogResponse']

// --- knowledge/schemas/population.py ------------------------------------------

/** `POST /knowledge_base/populate_man_pages` response. */
export type PopulateManPagesResponse = components['schemas']['PopulateManPagesResponse']

/** `POST /knowledge_base/populate_system_commands` response. */
export type PopulateSystemCommandsResponse = components['schemas']['PopulateSystemCommandsResponse']

/** `POST /knowledge_base/refresh_system_knowledge` response. */
export type RefreshSystemKnowledgeResponse = components['schemas']['RefreshSystemKnowledgeResponse']

/** `POST /knowledge_base/scan_man_pages` response. */
export type ScanManPagesResponse = components['schemas']['ScanManPagesResponse']

/** `POST /knowledge_base/scan_man_pages/changes` response. */
export type ScanManPagesChangesResponse = components['schemas']['ScanManPagesChangesResponse']

/** Population job status response. */
export type JobStatusResponse = components['schemas']['JobStatusResponse']

/** Background task queued response. */
export type TaskQueuedResponse = components['schemas']['TaskQueuedResponse']

/** Background task status poll response. */
export type TaskStatusResponse = components['schemas']['TaskStatusResponse']

// --- knowledge/schemas/rag.py -------------------------------------------------

/** Request body for `POST /rag/advanced_search`. */
export type AdvancedSearchRequest = components['schemas']['AdvancedSearchRequest']

/** Request body for `POST /rag/rerank`. */
export type RerankRequest = components['schemas']['RerankRequest']

/** Request body for `PUT /rag/config`. */
export type RAGConfigUpdate = components['schemas']['RAGConfigUpdate']

/** Request body for `POST /rag/benchmark/run`. */
export type RunBenchmarkRequest = components['schemas']['RunBenchmarkRequest']

/** `POST /rag/advanced_search` response. */
export type AdvancedSearchResponse = components['schemas']['AdvancedSearchResponse']

/** `POST /rag/rerank` response. */
export type RerankResultsResponse = components['schemas']['RerankResultsResponse']

/** `GET /rag/stats` response. */
export type RagStatsResponse = components['schemas']['RagStatsResponse']

/** `GET /rag/config` response. */
export type RagConfigResponse = components['schemas']['RagConfigResponse']

/** `PUT /rag/config` response. */
export type UpdateRagConfigResponse = components['schemas']['UpdateRagConfigResponse']

/** `POST /rag/benchmark/run` response. */
export type BenchmarkRunResponse = components['schemas']['BenchmarkRunResponse']

/** `GET /rag/loop/status` response. */
export type LoopStatusResponse = components['schemas']['LoopStatusResponse']

/** `POST /rag/loop/approve` response. */
export type LoopApproveResponse = components['schemas']['LoopApproveResponse']

/** `POST /rag/loop/reject` response. */
export type LoopRejectResponse = components['schemas']['LoopRejectResponse']

/** `GET /entity/{id}/history` response. */
export type EntityHistoryResponse = components['schemas']['EntityHistoryResponse']

// --- knowledge/schemas/vectorization.py ---------------------------------------

/** Request body for `POST /vectorize_documents`. */
export type BatchVectorizeRequest = components['schemas']['BatchVectorizeRequest']

/** Request body for `POST /reindex_with_context`. */
export type ReindexWithContextRequest = components['schemas']['ReindexWithContextRequest']

/** `POST /vectorization_status` summary sub-object. */
export type VectorizationSummary = components['schemas']['VectorizationSummary']

/** `POST /vectorization_status` response. */
export type VectorizationStatusResponse = components['schemas']['VectorizationStatusResponse']

/** `POST /vectorize_facts` response. */
export type VectorizeFactsResponse = components['schemas']['VectorizeFactsResponse']

/** `POST /vectorize_fact/{id}` response. */
export type VectorizeFactJobResponse = components['schemas']['VectorizeFactJobResponse']

/** Single document result in batch vectorization. */
export type DocumentResult = components['schemas']['DocumentResult']

/** `POST /vectorize_documents` response. */
export type VectorizeDocumentsResponse = components['schemas']['VectorizeDocumentsResponse']

/** `GET /vectorize_job/{id}` response. */
export type VectorizeJobStatusResponse = components['schemas']['VectorizeJobStatusResponse']

/** `GET /vectorize_jobs/failed` response. */
export type FailedJobsResponse = components['schemas']['FailedJobsResponse']

/** `POST /vectorize_jobs/{id}/retry` response. */
export type RetryJobResponse = components['schemas']['RetryJobResponse']

/** `DELETE /vectorize_jobs/{id}` response. */
export type DeleteJobResponse = components['schemas']['DeleteJobResponse']

/** `DELETE /vectorize_jobs/failed/clear` response. */
export type ClearFailedJobsResponse = components['schemas']['ClearFailedJobsResponse']

/** `POST /vectorize_facts/background` response. */
export type BackgroundVectorizationResponse = components['schemas']['BackgroundVectorizationResponse']

/** `GET /vectorize_facts/status` response. */
export type VectorizationStatusPollResponse = components['schemas']['VectorizationStatusPollResponse']

/** `POST /reindex_with_context` response. */
export type ReindexWithContextResponse = components['schemas']['ReindexWithContextResponse']

/** `GET /reindex_with_context/status` response. */
export type ReindexWithContextStatusResponse = components['schemas']['ReindexWithContextStatusResponse']

// --- knowledge/schemas/mcp.py -------------------------------------------------

/** Request body for `POST /mcp/search_knowledge_base`. */
export type KnowledgeSearchRequest = components['schemas']['KnowledgeSearchRequest']

/** Request body for `POST /mcp/add_to_knowledge_base`. */
export type DocumentAddRequest = components['schemas']['DocumentAddRequest']

/** Request body for `POST /mcp/get_knowledge_stats`. */
export type KnowledgeStatsRequest = components['schemas']['KnowledgeStatsRequest']

/** Single MCP tool definition (`GET /mcp/tools` list item). */
export type McpToolsResponse = components['schemas']['McpToolsResponse']

/** `POST /mcp/search_knowledge_base` response. */
export type McpSearchResponse = components['schemas']['McpSearchResponse']

/** `POST /mcp/add_to_knowledge_base` response. */
export type McpAddDocumentResponse = components['schemas']['McpAddDocumentResponse']

/** `POST /mcp/get_knowledge_stats` response. */
export type McpKnowledgeStatsResponse = components['schemas']['McpKnowledgeStatsResponse']

/** `POST /mcp/summarize_knowledge_topic` response. */
export type McpSummarizeTopicResponse = components['schemas']['McpSummarizeTopicResponse']

/** `POST /mcp/vector_similarity_search` response. */
export type McpVectorSimilarityResponse = components['schemas']['McpVectorSimilarityResponse']

/** `POST /mcp/langchain_qa_chain` response. */
export type McpQaChainResponse = components['schemas']['McpQaChainResponse']

/** `POST /mcp/redis_vector_operations` response. */
export type McpRedisVectorOpsResponse = components['schemas']['McpRedisVectorOpsResponse']

/** `GET /mcp/schema` response. */
export type McpSchemaResponse = components['schemas']['McpSchemaResponse']

/** `GET /mcp/health` response. */
export type McpHealthResponse = components['schemas']['McpHealthResponse']

/** `POST /rag-feedback` response. */
export type RagFeedbackResponse = components['schemas']['RagFeedbackResponse']

// --- user-management schemas (GH#7541) ----------------------------------------

/** `GET /user-management/users/{user_id}` response. */
export type UserResponse = components['schemas']['UserResponse']

/** `GET /user-management/teams/{team_id}` response. */
export type TeamResponse = components['schemas']['TeamResponse']
