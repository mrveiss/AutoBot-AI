/**
 * useKnowledgeBase Composable
 *
 * Shared functions for knowledge base management across all knowledge manager components.
 * This composable eliminates duplicate code and provides a consistent API interface.
 */

import apiClient from '@/utils/ApiClient'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import {
  formatDate as formatDateHelper,
  formatFileSize as formatFileSizeHelper,
  formatCategoryName as formatCategoryHelper
} from '@/utils/formatHelpers'
import { getFileIcon as getFileIconUtil } from '@/utils/iconMappings'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeBase')
import type {
  KnowledgeStats,
  CategoryResponse,
  CategoriesListResponse,
  KnowledgeCategoryItem,
  SearchResponse,
  AddFactResponse,
  UploadResponse,
  IntegrationResponse,
  VectorizationStatusResponse,
  VectorizationResponse,
  MachineKnowledgeResponse,
  SystemKnowledgeResponse,
  ManPagesPopulateResponse,
  AutoBotDocsResponse,
  CategorizedFactsResponse,
  CategoryFilterOption
} from '@/types/knowledgeBase'

// KnowledgeStats imported from @/types/knowledgeBase (consolidated type definition)

export interface MachineProfile {
  machine_id?: string
  os_type?: string
  distro?: string
  package_manager?: string
  available_tools?: string[]
  architecture?: string
}

export interface ManPagesSummary {
  status?: string
  message?: string
  successful?: number
  processed?: number
  current_man_page_files?: number
  total_available_tools?: number
  integration_date?: string
  available_commands?: string[]
}

export interface ProgressState {
  currentTask: string
  taskDetail: string
  overallProgress: number
  taskProgress: number
  status: 'waiting' | 'running' | 'success' | 'error'
  messages: ProgressMessage[]
}

export interface ProgressMessage {
  text: string
  type: 'info' | 'success' | 'warning' | 'error'
  timestamp: number
}

export function useKnowledgeBase() {
  // ==================== API CALLS ====================
  // NOTE: Now using shared parseApiResponse from @/utils/apiResponseHelpers
  // Removed duplicate parseApiResponse implementation (was 40 lines)

  /**
   * Fetch knowledge base statistics
   */
  const fetchStats = async (): Promise<KnowledgeStats | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/stats')

      if (!response) {
        throw new Error('Failed to fetch stats: No response from server');
      }

      const data = await parseApiResponse(response)
      return data as KnowledgeStats
    } catch (error) {
      logger.error('Error fetching stats:', error)
      throw error
    }
  }

  /**
   * Fetch all categories with counts
   * Returns list of categories with document counts for filtering
   * @throws Error if API request fails (consistent with other API functions)
   */
  const fetchCategories = async (): Promise<KnowledgeCategoryItem[]> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/categories')

      if (!response) {
        throw new Error('Failed to fetch categories: No response from server')
      }

      const data = await parseApiResponse(response) as CategoriesListResponse

      // Validate response structure
      if (!data || !Array.isArray(data.categories)) {
        throw new Error('Invalid categories response format')
      }

      return data.categories
    } catch (error) {
      logger.error('Error fetching categories:', error)
      throw error // Throw consistently with other API functions
    }
  }

  /**
   * Fetch knowledge by category
   */
  const fetchCategory = async (category: string): Promise<CategoryResponse> => {
    try {
      const response = await apiClient.get(`/api/knowledge_base/category/${category}`)

      if (!response) {
        throw new Error('Failed to fetch category: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error fetching category:', error)
      throw error
    }
  }

  /**
   * Fetch facts grouped by category for browsing
   * Uses GET /api/knowledge_base/facts/by_category endpoint
   * @param category - Optional category filter (null for all categories)
   * @param limit - Maximum number of facts per category (default: 100)
   * @returns CategorizedFactsResponse with facts grouped by category
   */
  const getCategorizedFacts = async (
    category: string | null = null,
    limit: number = 100
  ): Promise<CategorizedFactsResponse> => {
    try {
      const params = new URLSearchParams()
      if (category) {
        params.append('category', category)
      }
      params.append('limit', String(limit))

      const url = `/api/knowledge_base/facts/by_category?${params.toString()}`
      const response = await apiClient.get(url)

      if (!response) {
        throw new Error('Failed to fetch categorized facts: No response from server')
      }

      const data = await parseApiResponse(response) as CategorizedFactsResponse

      // Validate response structure
      if (!data || typeof data.categories !== 'object') {
        throw new Error('Invalid categorized facts response format')
      }

      logger.debug(`Fetched categorized facts: ${data.total_facts} total facts across ${Object.keys(data.categories).length} categories`)

      return data
    } catch (error) {
      logger.error('Error fetching categorized facts:', error)
      throw error
    }
  }

  /**
   * Build category filter options from categorized facts
   * Helper method to create CategoryFilterOption[] for UI components
   * @param categorizedFacts - Response from getCategorizedFacts
   * @returns Array of CategoryFilterOption for use in dropdowns/tabs
   */
  const buildCategoryFilterOptions = (
    categorizedFacts: CategorizedFactsResponse
  ): CategoryFilterOption[] => {
    const options: CategoryFilterOption[] = [
      {
        value: null,
        label: 'All Categories',
        icon: 'fas fa-th-large',
        count: categorizedFacts.total_facts
      }
    ]

    // Add each category as an option
    for (const [categoryName, facts] of Object.entries(categorizedFacts.categories)) {
      options.push({
        value: categoryName,
        label: formatCategoryHelper(categoryName),
        icon: getCategoryIcon(categoryName),
        count: facts.length
      })
    }

    // Sort by count (descending), keeping "All" at the top
    options.sort((a, b) => {
      if (a.value === null) return -1
      if (b.value === null) return 1
      return b.count - a.count
    })

    return options
  }

  /**
   * Search knowledge base (basic)
   */
  const searchKnowledge = async (query: string): Promise<SearchResponse> => {
    try {
      // Issue #552: Backend expects POST for search
      const response = await apiClient.post('/api/knowledge_base/search', { query })

      if (!response) {
        throw new Error('Search failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error searching knowledge:', error)
      throw error
    }
  }

  /**
   * Advanced search with full options (Issue #555)
   *
   * Uses the consolidated search endpoint with all available features:
   * - mode: 'semantic' | 'keyword' | 'hybrid' | 'auto'
   * - enable_rag: Enable RAG synthesis for responses
   * - enable_reranking: Enable cross-encoder reranking
   * - tags: Filter by tags
   * - min_score: Minimum similarity threshold
   * - category: Filter by category
   */
  interface AdvancedSearchOptions {
    query: string
    top_k?: number
    mode?: 'semantic' | 'keyword' | 'hybrid' | 'auto'
    enable_rag?: boolean
    enable_reranking?: boolean
    reformulate_query?: boolean
    tags?: string[]
    tags_match_any?: boolean
    min_score?: number
    category?: string
    offset?: number
  }

  const advancedSearch = async (options: AdvancedSearchOptions): Promise<SearchResponse> => {
    try {
      const response = await apiClient.post('/api/knowledge_base/search', options)

      if (!response) {
        throw new Error('Advanced search failed: No response from server')
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error in advanced search:', error)
      throw error
    }
  }

  /**
   * Add new fact to knowledge base
   */
  const addFact = async (fact: {
    content: string
    category: string
    metadata?: Record<string, unknown>
  }): Promise<AddFactResponse> => {
    try {
      const response = await apiClient.post('/api/knowledge_base/facts', fact)

      if (!response) {
        throw new Error('Failed to add fact: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error adding fact:', error)
      throw error
    }
  }

  /**
   * Upload knowledge base file
   */
  const uploadKnowledgeFile = async (formData: FormData): Promise<UploadResponse> => {
    try {
      const url = await appConfig.getApiUrl('/api/knowledge_base/upload')

      const response = await fetchWithAuth(url, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        logger.error('File upload failed with status:', response.status)
        const errorText = await response.text()
        logger.error('Error response:', errorText)
        throw new Error(`Upload failed: ${response.status} ${response.statusText}`)
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error uploading file:', error)
      throw error
    }
  }

  /**
   * Fetch machine profiles
   */
  const fetchMachineProfiles = async (): Promise<MachineProfile[]> => {
    try {
      // Issue #552: Fixed path - backend uses singular /api/knowledge_base/machine_profile
      const response = await apiClient.get('/api/knowledge_base/machine_profile')

      if (!response) {
        throw new Error('Failed to fetch machine profiles: No response from server');
      }

      const data = await parseApiResponse(response)
      return Array.isArray(data) ? data : []
    } catch (error) {
      logger.error('Error fetching machine profiles:', error)
      return []
    }
  }

  /**
   * Fetch man pages summary
   */
  const fetchManPagesSummary = async (): Promise<ManPagesSummary | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/man_pages/summary')

      if (!response) {
        throw new Error('Failed to fetch man pages summary: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error fetching man pages summary:', error)
      return null
    }
  }

  /**
   * Integrate man pages for a specific machine
   */
  const integrateManPages = async (machineId: string): Promise<IntegrationResponse> => {
    try {
      const response = await apiClient.post('/api/knowledge_base/man_pages/integrate', {
        machine_id: machineId
      })

      if (!response) {
        throw new Error('Integration failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error integrating man pages:', error)
      throw error
    }
  }

  /**
   * Get vectorization status
   */
  const getVectorizationStatus = async (): Promise<VectorizationStatusResponse> => {
    try {
      // Issue #552: Fixed path - backend uses /api/knowledge_base/vectorize_facts/status
      const response = await apiClient.get('/api/knowledge_base/vectorize_facts/status')

      if (!response) {
        throw new Error('Failed to get vectorization status: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('Error getting vectorization status:', error)
      throw error
    }
  }

  /**
   * Generate vector embeddings for all existing facts using batched processing (legacy/manual)
   * Enhanced with comprehensive error handling and response validation
   * @param batchSize - Number of facts to process per batch (default: 50)
   * @param batchDelay - Delay in seconds between batches (default: 0.5)
   * @param skipExisting - Skip facts that already have vectors (default: true)
   */
  const vectorizeFacts = async (
    batchSize: number = 50,
    batchDelay: number = 0.5,
    skipExisting: boolean = true
  ): Promise<VectorizationResponse> => {
    try {
      // Get knowledge-specific timeout (300s for vectorization operations)
      const knowledgeTimeout = appConfig.getTimeout('knowledge')

      const response = await apiClient.post('/api/knowledge_base/vectorize_facts', {
        batch_size: batchSize,
        batch_delay: batchDelay,
        skip_existing: skipExisting
      }, { timeout: knowledgeTimeout })

      logger.debug('[vectorizeFacts] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        headers: Object.fromEntries(response.headers.entries())
      })

      if (!response) {
        throw new Error('Vectorization failed: No response from server');
      }

      // Parse successful response
      const data = await parseApiResponse(response)

      return data
    } catch (error) {
      logger.error('[vectorizeFacts] Error occurred:', error)

      // Enhanced error with more context
      if (error instanceof Error) {
        throw error // Re-throw with original message
      } else {
        throw new Error(`Vectorization failed: ${String(error)}`)
      }
    }
  }

  /**
   * Initialize machine knowledge for a specific host
   * POST /api/knowledge_base/machine_knowledge/initialize
   */
  const initializeMachineKnowledge = async (machineId: string): Promise<MachineKnowledgeResponse> => {
    try {

      const response = await apiClient.post('/api/knowledge_base/machine_knowledge/initialize', {
        machine_id: machineId
      })

      logger.debug('[initializeMachineKnowledge] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Machine knowledge initialization failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('[initializeMachineKnowledge] Error:', error)
      throw error
    }
  }

  /**
   * Refresh system knowledge (rescan and update all system information) - ASYNC JOB
   * POST /api/knowledge_base/refresh_system_knowledge
   *
   * Returns immediately with task_id. Use pollJobStatus to check completion.
   */
  const refreshSystemKnowledge = async (): Promise<SystemKnowledgeResponse> => {
    try {

      const response = await apiClient.post('/api/knowledge_base/refresh_system_knowledge', {})

      logger.debug('[refreshSystemKnowledge] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('System knowledge refresh failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('[refreshSystemKnowledge] Error:', error)
      throw error
    }
  }

  /**
   * Poll status of a background job (e.g., knowledge refresh, reindexing)
   * GET /api/knowledge_base/job_status/{task_id}
   *
   * Returns current status: PENDING, PROGRESS, SUCCESS, or FAILURE
   */
  const pollJobStatus = async (taskId: string): Promise<any> => {
    try {
      const response = await apiClient.get(`/api/knowledge_base/job_status/${taskId}`)

      logger.debug('[pollJobStatus] Response received:', {
        ok: response.ok,
        status: response.status,
        taskId
      })

      if (!response) {
        throw new Error('Job status check failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('[pollJobStatus] Error:', error)
      throw error
    }
  }

  /**
   * Populate man pages for a specific machine
   * POST /api/knowledge_base/populate_man_pages
   */
  const populateManPages = async (machineId: string): Promise<ManPagesPopulateResponse> => {
    try {

      const response = await apiClient.post('/api/knowledge_base/populate_man_pages', {
        machine_id: machineId
      })

      logger.debug('[populateManPages] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Man pages population failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('[populateManPages] Error:', error)
      throw error
    }
  }

  /**
   * Populate AutoBot documentation
   * POST /api/knowledge_base/populate_autobot_docs
   */
  const populateAutoBotDocs = async (): Promise<AutoBotDocsResponse> => {
    try {

      const response = await apiClient.post('/api/knowledge_base/populate_autobot_docs', {})

      logger.debug('[populateAutoBotDocs] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('AutoBot docs population failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data
    } catch (error) {
      logger.error('[populateAutoBotDocs] Error:', error)
      throw error
    }
  }

  /**
   * Fetch machine profile for a specific machine
   * GET /api/knowledge_base/machine_profile?machine_id=<id>
   */
  const fetchMachineProfile = async (machineId: string): Promise<MachineProfile | null> => {
    try {

      const response = await apiClient.get(
        `/api/knowledge_base/machine_profile?machine_id=${encodeURIComponent(machineId)}`
      )

      logger.debug('[fetchMachineProfile] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Machine profile fetch failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data as MachineProfile
    } catch (error) {
      logger.error('[fetchMachineProfile] Error:', error)
      return null
    }
  }

  /**
   * Fetch basic knowledge base statistics
   * GET /api/knowledge_base/stats/basic
   */
  const fetchBasicStats = async (): Promise<KnowledgeStats | null> => {
    try {

      const response = await apiClient.get('/api/knowledge_base/stats/basic')

      logger.debug('[fetchBasicStats] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Basic stats fetch failed: No response from server');
      }

      const data = await parseApiResponse(response)
      return data as KnowledgeStats
    } catch (error) {
      logger.error('[fetchBasicStats] Error:', error)
      return null
    }
  }

  // ==================== FORMATTING FUNCTIONS ====================
  // NOTE: Now using shared formatHelpers from @/utils/formatHelpers
  // Removed duplicate formatDate, formatCategory implementations (was 23 lines)

  /**
   * Get icon for category
   */
  const getCategoryIcon = (category: string): string => {
    const categoryLower = category.toLowerCase()

    if (categoryLower.includes('architecture') || categoryLower.includes('design')) {
      return 'fas fa-drafting-compass'
    }
    if (categoryLower.includes('implementation') || categoryLower.includes('code')) {
      return 'fas fa-code'
    }
    if (categoryLower.includes('security')) {
      return 'fas fa-shield-alt'
    }
    if (categoryLower.includes('operations') || categoryLower.includes('devops')) {
      return 'fas fa-cogs'
    }
    if (categoryLower.includes('research') || categoryLower.includes('analysis')) {
      return 'fas fa-flask'
    }
    if (categoryLower.includes('reports') || categoryLower.includes('documentation')) {
      return 'fas fa-file-alt'
    }
    if (categoryLower.includes('archives') || categoryLower.includes('history')) {
      return 'fas fa-archive'
    }
    if (categoryLower.includes('project') || categoryLower.includes('planning')) {
      return 'fas fa-project-diagram'
    }

    return 'fas fa-folder'
  }

  /**
   * Get icon for document type
   */
  const getTypeIcon = (type: string): string => {
    const typeLower = type.toLowerCase()

    if (typeLower.includes('pdf')) return 'fas fa-file-pdf'
    if (typeLower.includes('word') || typeLower.includes('doc')) return 'fas fa-file-word'
    if (typeLower.includes('excel') || typeLower.includes('xls')) return 'fas fa-file-excel'
    if (typeLower.includes('image') || typeLower.includes('png') || typeLower.includes('jpg')) return 'fas fa-file-image'
    if (typeLower.includes('video')) return 'fas fa-file-video'
    if (typeLower.includes('audio')) return 'fas fa-file-audio'
    if (typeLower.includes('json') || typeLower.includes('code')) return 'fas fa-file-code'
    if (typeLower.includes('csv')) return 'fas fa-file-csv'
    if (typeLower.includes('text') || typeLower.includes('txt')) return 'fas fa-file-alt'
    if (typeLower.includes('markdown') || typeLower.includes('md')) return 'fas fa-file-alt'

    return 'fas fa-file'
  }

  /**
   * Get icon for file based on name and type
   * Icon mapping centralized in @/utils/iconMappings
   * Color classes added for visual distinction in knowledge base
   */
  const getFileIcon = (name: string, isDir: boolean = false): string => {
    if (isDir) {
      return 'fas fa-folder'
    }

    const icon = getFileIconUtil(name, false)
    const extension = name.split('.').pop()?.toLowerCase() || ''

    // Map extensions to color classes for visual distinction
    const colorMap: Record<string, string> = {
      // Code files - blue/green
      'js': 'text-blue-500',
      'ts': 'text-blue-500',
      'jsx': 'text-blue-500',
      'tsx': 'text-blue-500',
      'vue': 'text-blue-500',
      'py': 'text-green-500',
      'rb': 'text-green-500',
      'go': 'text-green-500',
      'java': 'text-green-500',
      'c': 'text-green-500',
      'cpp': 'text-green-500',
      'h': 'text-green-500',
      // Data files - orange
      'json': 'text-orange-500',
      'yaml': 'text-orange-500',
      'yml': 'text-orange-500',
      'toml': 'text-orange-500',
      // Documents - varied
      'md': 'text-gray-600',
      'txt': 'text-gray-600',
      'pdf': 'text-red-600',
      'doc': 'text-blue-600',
      'docx': 'text-blue-600',
      'xls': 'text-green-600',
      'xlsx': 'text-green-600',
      'csv': 'text-green-600',
      // Images - purple
      'png': 'text-purple-500',
      'jpg': 'text-purple-500',
      'jpeg': 'text-purple-500',
      'gif': 'text-purple-500',
      'svg': 'text-purple-500',
      'webp': 'text-purple-500',
      // Archives - yellow
      'zip': 'text-yellow-600',
      'tar': 'text-yellow-600',
      'gz': 'text-yellow-600',
      'rar': 'text-yellow-600',
      '7z': 'text-yellow-600'
    }

    const color = colorMap[extension] || 'text-gray-600'
    return `${icon} ${color}`
  }

  const getOSBadgeClass = (osType: string): string => {
    switch (osType) {
      case 'linux': return 'badge-success'
      case 'windows': return 'badge-info'
      case 'macos': return 'badge-warning'
      default: return 'badge-secondary'
    }
  }

  const getMessageIcon = (type: string): string => {
    const icons: Record<string, string> = {
      'info': 'fas fa-info-circle text-blue-500',
      'success': 'fas fa-check-circle text-green-500',
      'warning': 'fas fa-exclamation-triangle text-yellow-500',
      'error': 'fas fa-times-circle text-red-500'
    }
    return icons[type] || icons.info
  }

  const formatTime = (timestamp: string | Date): string => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  }

  // NOTE: formatFileSize removed (was 7 lines) - now using formatFileSizeHelper from @/utils/formatHelpers

  // ==================== EXPORTS ====================

  return {
    // API calls
    fetchStats,
    fetchCategories,
    fetchCategory,
    searchKnowledge,
    advancedSearch,  // Issue #555: Consolidated search with all options
    addFact,
    uploadKnowledgeFile,
    fetchMachineProfiles,
    fetchManPagesSummary,
    integrateManPages,
    getVectorizationStatus,
    vectorizeFacts,
    // New API calls
    initializeMachineKnowledge,
    refreshSystemKnowledge,
    pollJobStatus,  // NEW: Poll background job status
    populateManPages,
    populateAutoBotDocs,
    fetchMachineProfile,
    fetchBasicStats,
    // Category filtering (Issue #161)
    getCategorizedFacts,
    buildCategoryFilterOptions,
    // Formatting helpers (using shared utilities)
    formatDate: formatDateHelper,
    formatCategory: formatCategoryHelper,
    formatCategoryName: formatCategoryHelper, // Alias for backward compatibility
    formatFileSize: formatFileSizeHelper,
    // Icon helpers
    getCategoryIcon,
    getTypeIcon,
    getFileIcon,
    getOSBadgeClass,
    getMessageIcon,
    formatTime,
    formatDateOnly: formatDateHelper, // Alias for backward compatibility
    // Helper function
    parseApiResponse
  }
}
