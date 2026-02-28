/**
 * Knowledge Base API Response Types
 * Type definitions for knowledge base API responses and state management
 */

// ============================================================================
// Core Type Definitions (Consolidated from multiple sources)
// ============================================================================

/**
 * Comprehensive Knowledge Base Statistics
 * Consolidates fields from useKnowledgeStore and useKnowledgeBase
 */
export interface KnowledgeStats {
  total_documents?: number
  total_chunks?: number
  total_facts?: number
  total_vectors?: number
  categories?: string[] | Record<string, number>
  db_size?: number
  status?: string
  last_updated?: string | null
  redis_db?: string | null
  index_name?: string | null
  initialized?: boolean
  rag_available?: boolean
}

// ============================================================================
// Response Interfaces
// ============================================================================

/**
 * @deprecated Use KnowledgeStats instead for consistency
 */
export interface KnowledgeStatsResponse {
  total_facts?: number
  total_vectors?: number
  categories?: Record<string, number> | string[]
}

/**
 * Category item as returned by /api/knowledge_base/categories
 */
export interface KnowledgeCategoryItem {
  name: string
  count: number
  id: string
}

/**
 * Response from /api/knowledge_base/categories endpoint
 */
export interface CategoriesListResponse {
  categories: KnowledgeCategoryItem[]
  total: number
}

export interface CategoryResponse {
  status?: string
  message?: string
  successful?: number
  processed?: number
  current_man_page_files?: number
  total_available_tools?: number
  integration_date?: string
  available_commands?: string[]
  facts?: Array<{
    id: string
    fact: string
    category?: string
    confidence?: number
    source?: string
    created_at: string
    updated_at: string
  }>
}

export interface SearchResponse {
  results?: Array<{
    id: string
    fact: string
    category?: string
    confidence?: number
    source?: string
    similarity_score?: number
  }>
  total_results?: number
  query?: string
  search_time?: number
}

export interface AddFactResponse {
  success: boolean
  message?: string
  fact_id?: string
  fact?: {
    id: string
    fact: string
    category?: string
    confidence?: number
    source?: string
    created_at: string
    updated_at: string
  }
}

export interface UploadResponse {
  success: boolean
  message?: string
  file_path?: string
  facts_added?: number
  error?: string
}

export interface MachineProfileResponse {
  machine_id?: string
  os_type?: string
  distro?: string
  package_manager?: string
  available_tools?: string[]
  architecture?: string
  hostname?: string
  kernel_version?: string
}

export interface ManPagesSummaryResponse {
  status?: string
  message?: string
  successful?: number
  processed?: number
  current_man_page_files?: number
  total_available_tools?: number
  integration_date?: string
  available_commands?: string[]
}

export interface IntegrationResponse {
  status: string
  message: string
  successful?: number
  processed?: number
  errors?: string[]
  machine_id?: string
}

export interface VectorizationStatusResponse {
  status: string
  message?: string
  total_facts?: number
  vectorized_facts?: number
  pending_vectorization?: number
  vectorization_progress?: number
  last_vectorization?: string
}

export interface VectorizationResponse {
  status: string
  message: string
  total_processed?: number
  successful?: number
  failed?: number
  skipped?: number
  batch_size?: number
  processing_time?: number
  errors?: string[]
}

export interface MachineKnowledgeResponse {
  status: string
  message: string
  machine_id?: string
  facts_added?: number
  categories?: string[]
  initialization_time?: number
  errors?: string[]
}

export interface SystemKnowledgeResponse {
  status: string
  message: string
  total_machines?: number
  successful_machines?: number
  failed_machines?: number
  total_facts_updated?: number
  refresh_time?: number
  errors?: string[]
}

export interface ManPagesPopulateResponse {
  status: string
  message: string
  machine_id?: string
  man_pages_added?: number
  processing_time?: number
  errors?: string[]
}

export interface AutoBotDocsResponse {
  status: string
  message: string
  documents_processed?: number
  facts_added?: number
  processing_time?: number
  errors?: string[]
}

export interface BasicStatsResponse {
  total_facts?: number
  total_categories?: number
  total_vectors?: number
  last_updated?: string
}

/**
 * Individual fact item from categorized facts response
 */
export interface CategorizedFact {
  key: string
  title: string
  content: string
  full_content?: string
  category: string
  type: string
  metadata: Record<string, unknown>
}

/**
 * Response from /api/knowledge_base/facts/by_category endpoint
 */
export interface CategorizedFactsResponse {
  categories: Record<string, CategorizedFact[]>
  total_facts: number
  category_filter?: string | null
}

/**
 * Category filter option for UI components
 */
export interface CategoryFilterOption {
  value: string | null
  label: string
  icon: string
  count: number
}

// ============================================================================
// Source Verification & Provenance Types (Issue #1253)
// ============================================================================

/**
 * Provenance metadata attached to knowledge base entries.
 * Tracks source origin, verification status, and chain of custody.
 */
export interface ProvenanceMetadata {
  source_type: 'manual_upload' | 'url_fetch' | 'web_research' | 'connector'
  verification_status: 'unverified' | 'pending_review' | 'verified' | 'rejected'
  verification_method: 'auto_quality' | 'user_approved' | 'connector_trusted' | null
  verified_by: string | null
  verified_at: string | null
  quality_score: number
  provenance_chain: Array<{
    action: string
    actor: string
    timestamp: string
  }>
  source_connector_id: string | null
}

/**
 * Verification mode configuration.
 * - autonomous: auto-approve sources above quality threshold
 * - collaborative: require user review for all sources
 */
export interface VerificationConfig {
  mode: 'autonomous' | 'collaborative'
  quality_threshold: number
}

/**
 * A source pending verification review.
 */
export interface PendingSource {
  fact_id: string
  content: string
  source_type: string
  quality_score: number
  timestamp: string
  domain: string | null
  title: string | null
  url: string | null
}
