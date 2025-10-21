/**
 * useKnowledgeBase Composable
 *
 * Shared functions for knowledge base management across all knowledge manager components.
 * This composable eliminates duplicate code and provides a consistent API interface.
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'
import type {
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

export interface KnowledgeStats {
  total_facts?: number
  total_vectors?: number
  categories?: Record<string, number> | string[]
}

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
  // ==================== HELPER FUNCTIONS ====================

  /**
   * Safely parse JSON from response - handles both Response objects and already-parsed data
   * Enhanced with better error handling and logging
   */
  const parseResponse = async <T = any>(response: unknown): Promise<T> => {
    try {
      // Check if response is already parsed data
      if (response && typeof response === 'object' && (response as Response).json === undefined) {
        return response as T
      }

      // Check if response has json() method (fetch Response object)
      if (typeof (response as Response).json === 'function') {
        // Clone the response to avoid consuming the body if we need to debug
        const clonedResponse = (response as Response).clone()

        try {
          const data = await (response as Response).json()
          return data as T
        } catch (jsonError) {
          // If JSON parsing fails, try to get text for debugging
          console.error('Failed to parse JSON response:', jsonError)
          try {
            const text = await clonedResponse.text()
            console.error('Response text:', text)
          } catch (textError) {
            console.error('Failed to get response text:', textError)
          }
          throw new Error('Invalid JSON response from server')
        }
      }

      // Fallback: return as-is
      return response as T
    } catch (error) {
      console.error('Error in parseResponse:', error)
      throw error
    }
  }

  // ==================== API CALLS ====================

  /**
   * Fetch knowledge base statistics
   */
  const fetchStats = async (): Promise<KnowledgeStats | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/stats')

      if (!response) {
        throw new Error('Failed to fetch stats: No response from server');
      }

      const data = await parseResponse<KnowledgeStatsResponse>(response)
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

      const data = await parseResponse<CategoryResponse>(response)
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

      const data = await parseResponse<SearchResponse>(response)
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

      const data = await parseResponse<AddFactResponse>(response)
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

      const data = await parseResponse<UploadResponse>(response)
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

      const data = await parseResponse<MachineProfileResponse[]>(response)
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

      const data = await parseResponse<ManPagesSummaryResponse>(response)
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

      const data = await parseResponse<IntegrationResponse>(response)
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

      const data = await parseResponse<VectorizationStatusResponse>(response)
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
      console.log('[vectorizeFacts] Starting vectorization request...')
      console.log('[vectorizeFacts] Parameters:', { batchSize, batchDelay, skipExisting })

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
      console.log('[vectorizeFacts] Parsing successful response...')
      const data = await parseResponse<VectorizationResponse>(response)
      console.log('[vectorizeFacts] Parsed response data:', data)

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
      console.log('[initializeMachineKnowledge] Starting initialization request...')
      console.log('[initializeMachineKnowledge] Machine ID:', machineId)

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

      const data = await parseResponse<MachineKnowledgeResponse>(response)
      console.log('[initializeMachineKnowledge] Success:', data)
      return data
    } catch (error) {
      console.error('[initializeMachineKnowledge] Error:', error)
      throw error
    }
  }

  /**
   * Refresh system knowledge (rescan and update all system information)
   * POST /api/knowledge_base/refresh_system_knowledge
   */
  const refreshSystemKnowledge = async (): Promise<SystemKnowledgeResponse> => {
    try {
      console.log('[refreshSystemKnowledge] Starting refresh request...')

      const response = await apiClient.post('/api/knowledge_base/refresh_system_knowledge', {})

      console.log('[refreshSystemKnowledge] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('System knowledge refresh failed: No response from server');
      }

      const data = await parseResponse<SystemKnowledgeResponse>(response)
      console.log('[refreshSystemKnowledge] Success:', data)
      return data
    } catch (error) {
      console.error('[refreshSystemKnowledge] Error:', error)
      throw error
    }
  }

  /**
   * Populate man pages for a specific machine
   * POST /api/knowledge_base/populate_man_pages
   */
  const populateManPages = async (machineId: string): Promise<ManPagesPopulateResponse> => {
    try {
      console.log('[populateManPages] Starting population request...')
      console.log('[populateManPages] Machine ID:', machineId)

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

      const data = await parseResponse<ManPagesPopulateResponse>(response)
      console.log('[populateManPages] Success:', data)
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
      console.log('[populateAutoBotDocs] Starting documentation population request...')

      const response = await apiClient.post('/api/knowledge_base/populate_autobot_docs', {})

      console.log('[populateAutoBotDocs] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('AutoBot docs population failed: No response from server');
      }

      const data = await parseResponse<AutoBotDocsResponse>(response)
      console.log('[populateAutoBotDocs] Success:', data)
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
      console.log('[fetchMachineProfile] Fetching profile for machine:', machineId)

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

      const data = await parseResponse<MachineProfileResponse>(response)
      console.log('[fetchMachineProfile] Success:', data)
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
      console.log('[fetchBasicStats] Fetching basic stats...')

      const response = await apiClient.get('/api/knowledge_base/stats/basic')

      console.log('[fetchBasicStats] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response) {
        throw new Error('Basic stats fetch failed: No response from server');
      }

      const data = await parseResponse<BasicStatsResponse>(response)
      console.log('[fetchBasicStats] Success:', data)
      return data as KnowledgeStats
    } catch (error) {
      console.error('[fetchBasicStats] Error:', error)
      return null
    }
  }

  // ==================== FORMATTING FUNCTIONS ====================

  /**
   * Format date string to localized date
   */
  const formatDate = (dateString: string | Date | undefined): string => {
    if (!dateString) return ''

    try {
      const date = typeof dateString === 'string' ? new Date(dateString) : dateString
      return date.toLocaleDateString()
    } catch {
      return ''
    }
  }

  /**
   * Format category name for display
   */
  const formatCategory = (category: string): string => {
    return category
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

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

  /**
   * Format file size in human-readable format
   */
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

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
    populateManPages,
    populateAutoBotDocs,
    fetchMachineProfile,
    fetchBasicStats,
    // Formatting helpers
    formatDate,
    formatCategory,
    formatCategoryName: formatCategory, // Alias for backward compatibility
    formatFileSize,
    // Icon helpers
    getCategoryIcon,
    getTypeIcon,
    getFileIcon,
    formatDateOnly: formatDate, // Alias for backward compatibility
    // Helper function
    parseResponse
  }
}
