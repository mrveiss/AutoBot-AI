/**
 * useKnowledgeBase Composable
 *
 * Shared functions for knowledge base management across all knowledge manager components.
 * This composable eliminates duplicate code and provides a consistent API interface.
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import {
  formatDate as formatDateHelper,
  formatFileSize as formatFileSizeHelper,
  formatCategoryName as formatCategoryHelper
} from '@/utils/formatHelpers'
import appConfig from '@/config/AppConfig.js'
import type {
  KnowledgeStats,
  KnowledgeStatsResponse,
  CategoryResponse,
  SearchResponse,
  AddFactResponse,
  UploadResponse,
  MachineProfileResponse,
  ManPagesSummaryResponse,
  IntegrationResponse,
  VectorizationStatusResponse,
  VectorizationResponse,
  MachineKnowledgeResponse,
  SystemKnowledgeResponse,
  ManPagesPopulateResponse,
  AutoBotDocsResponse,
  BasicStatsResponse
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

      const data = await parseApiResponse<KnowledgeStatsResponse>(response)
      return data as KnowledgeStats
    } catch (error) {
      console.error('Error fetching stats:', error)
      throw error
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

      const data = await parseApiResponse<CategoryResponse>(response)
      return data
    } catch (error) {
      console.error('Error fetching category:', error)
      throw error
    }
  }

  /**
   * Search knowledge base
   */
  const searchKnowledge = async (query: string): Promise<SearchResponse> => {
    try {
      const response = await apiClient.get(`/api/knowledge_base/search?query=${encodeURIComponent(query)}`)

      if (!response) {
        throw new Error('Search failed: No response from server');
      }

      const data = await parseApiResponse<SearchResponse>(response)
      return data
    } catch (error) {
      console.error('Error searching knowledge:', error)
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

      const data = await parseApiResponse<AddFactResponse>(response)
      return data
    } catch (error) {
      console.error('Error adding fact:', error)
      throw error
    }
  }

  /**
   * Upload knowledge base file
   */
  const uploadKnowledgeFile = async (formData: FormData): Promise<UploadResponse> => {
    try {
      const url = await appConfig.getApiUrl('/api/knowledge_base/upload')

      const response = await fetch(url, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        console.error('File upload failed with status:', response.status)
        const errorText = await response.text()
        console.error('Error response:', errorText)
        throw new Error(`Upload failed: ${response.status} ${response.statusText}`)
      }

      const data = await parseApiResponse<UploadResponse>(response)
      return data
    } catch (error) {
      console.error('Error uploading file:', error)
      throw error
    }
  }

  /**
   * Fetch machine profiles
   */
  const fetchMachineProfiles = async (): Promise<MachineProfile[]> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/machine_profiles')

      if (!response) {
        throw new Error('Failed to fetch machine profiles: No response from server');
      }

      const data = await parseApiResponse<MachineProfileResponse[]>(response)
      return Array.isArray(data) ? data : []
    } catch (error) {
      console.error('Error fetching machine profiles:', error)
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

      const data = await parseApiResponse<ManPagesSummaryResponse>(response)
      return data
    } catch (error) {
      console.error('Error fetching man pages summary:', error)
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

      const data = await parseApiResponse<IntegrationResponse>(response)
      return data
    } catch (error) {
      console.error('Error integrating man pages:', error)
      throw error
    }
  }

  /**
   * Get vectorization status
   */
  const getVectorizationStatus = async (): Promise<VectorizationStatusResponse> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/vectorization/status')

      if (!response) {
        throw new Error('Failed to get vectorization status: No response from server');
      }

      const data = await parseApiResponse<VectorizationStatusResponse>(response)
      return data
    } catch (error) {
      console.error('Error getting vectorization status:', error)
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

      const response = await apiClient.post('/api/knowledge_base/vectorize_facts', {
        batch_size: batchSize,
        batch_delay: batchDelay,
        skip_existing: skipExisting
      })

      console.log('[vectorizeFacts] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        headers: Object.fromEntries(response.headers.entries())
      })

      if (!response) {
        throw new Error('Vectorization failed: No response from server');
      }

      // Parse successful response
      const data = await parseApiResponse<VectorizationResponse>(response)

      return data
    } catch (error) {
      console.error('[vectorizeFacts] Error occurred:', error)

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

      console.log('[initializeMachineKnowledge] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Machine knowledge initialization failed: No response from server');
      }

      const data = await parseApiResponse<MachineKnowledgeResponse>(response)
      return data
    } catch (error) {
      console.error('[initializeMachineKnowledge] Error:', error)
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

      console.log('[refreshSystemKnowledge] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('System knowledge refresh failed: No response from server');
      }

      const data = await parseApiResponse<SystemKnowledgeResponse>(response)
      return data
    } catch (error) {
      console.error('[refreshSystemKnowledge] Error:', error)
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

      console.log('[pollJobStatus] Response received:', {
        ok: response.ok,
        status: response.status,
        taskId
      })

      if (!response) {
        throw new Error('Job status check failed: No response from server');
      }

      const data = await parseApiResponse<any>(response)
      return data
    } catch (error) {
      console.error('[pollJobStatus] Error:', error)
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

      console.log('[populateManPages] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Man pages population failed: No response from server');
      }

      const data = await parseApiResponse<ManPagesPopulateResponse>(response)
      return data
    } catch (error) {
      console.error('[populateManPages] Error:', error)
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

      console.log('[populateAutoBotDocs] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('AutoBot docs population failed: No response from server');
      }

      const data = await parseApiResponse<AutoBotDocsResponse>(response)
      return data
    } catch (error) {
      console.error('[populateAutoBotDocs] Error:', error)
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

      console.log('[fetchMachineProfile] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Machine profile fetch failed: No response from server');
      }

      const data = await parseApiResponse<MachineProfileResponse>(response)
      return data as MachineProfile
    } catch (error) {
      console.error('[fetchMachineProfile] Error:', error)
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

      console.log('[fetchBasicStats] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Basic stats fetch failed: No response from server');
      }

      const data = await parseApiResponse<BasicStatsResponse>(response)
      return data as KnowledgeStats
    } catch (error) {
      console.error('[fetchBasicStats] Error:', error)
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
   */
  const getFileIcon = (name: string, isDir: boolean = false): string => {
    if (isDir) {
      return 'fas fa-folder'
    }

    const extension = name.split('.').pop()?.toLowerCase() || ''

    // Code files
    if (['js', 'ts', 'jsx', 'tsx', 'vue'].includes(extension)) {
      return 'fas fa-file-code text-blue-500'
    }
    if (['py', 'rb', 'go', 'java', 'c', 'cpp', 'h'].includes(extension)) {
      return 'fas fa-file-code text-green-500'
    }

    // Documents
    if (['md', 'txt'].includes(extension)) return 'fas fa-file-alt text-gray-600'
    if (['pdf'].includes(extension)) return 'fas fa-file-pdf text-red-600'
    if (['doc', 'docx'].includes(extension)) return 'fas fa-file-word text-blue-600'
    if (['xls', 'xlsx'].includes(extension)) return 'fas fa-file-excel text-green-600'

    // Data files
    if (['json', 'yaml', 'yml', 'toml'].includes(extension)) {
      return 'fas fa-file-code text-orange-500'
    }
    if (['csv'].includes(extension)) return 'fas fa-file-csv text-green-600'

    // Images
    if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(extension)) {
      return 'fas fa-file-image text-purple-500'
    }

    // Archives
    if (['zip', 'tar', 'gz', 'rar', '7z'].includes(extension)) {
      return 'fas fa-file-archive text-yellow-600'
    }

    return 'fas fa-file text-gray-600'
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
    fetchCategory,
    searchKnowledge,
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
