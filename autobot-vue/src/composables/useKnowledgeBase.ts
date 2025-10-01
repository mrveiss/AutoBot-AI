/**
 * useKnowledgeBase Composable
 *
 * Shared functions for knowledge base management across all knowledge manager components.
 * This composable eliminates duplicate code and provides a consistent API interface.
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'

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
  // ==================== API CALLS ====================

  /**
   * Fetch knowledge base statistics
   */
  const fetchStats = async (): Promise<KnowledgeStats | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/stats')
      return response.data || response
    } catch (error) {
      console.error('Failed to fetch KB stats:', error)
      return null
    }
  }

  /**
   * Fetch basic knowledge base statistics
   */
  const fetchBasicStats = async (): Promise<KnowledgeStats | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/stats/basic')
      return response
    } catch (error) {
      console.error('Failed to fetch basic KB stats:', error)
      return null
    }
  }

  /**
   * Fetch machine profile information
   */
  const fetchMachineProfile = async (): Promise<MachineProfile | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/machine_profile')

      if (response && response.status === 'success') {
        return response.machine_profile
      }
      return null
    } catch (error) {
      console.error('Error fetching machine profile:', error)
      return null
    }
  }

  /**
   * Fetch man pages integration summary
   */
  const fetchManPagesSummary = async (): Promise<ManPagesSummary | null> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/man_pages/summary')

      if (response && response.status === 'success') {
        return response.man_pages_summary
      }
      return { status: 'not_integrated', message: 'Backend restart required' }
    } catch (error) {
      console.error('Error fetching man pages summary:', error)
      return { status: 'error', message: 'Connection failed' }
    }
  }

  /**
   * Initialize machine knowledge
   */
  const initializeMachineKnowledge = async (force: boolean = false) => {
    try {
      const response = await apiClient.post('/knowledge_base/machine_knowledge/initialize', {
        force
      })
      return response
    } catch (error) {
      console.error('Error initializing machine knowledge:', error)
      throw error
    }
  }

  /**
   * Integrate man pages
   */
  const integrateManPages = async () => {
    try {
      const response = await apiClient.post('/api/knowledge_base/man_pages/integrate')
      return response
    } catch (error) {
      console.error('Error integrating man pages:', error)
      throw error
    }
  }

  /**
   * Search man pages
   */
  const searchManPages = async (query: string) => {
    try {
      const response = await apiClient.get('/api/knowledge_base/man_pages/search', {
        params: { query }
      })
      return response
    } catch (error) {
      console.error('Error searching man pages:', error)
      throw error
    }
  }

  /**
   * Refresh system knowledge
   */
  const refreshSystemKnowledge = async () => {
    try {
      const response = await apiClient.post('/knowledge_base/refresh_system_knowledge', {})
      return response
    } catch (error) {
      console.error('Error refreshing system knowledge:', error)
      throw error
    }
  }

  /**
   * Populate man pages
   */
  const populateManPages = async () => {
    try {
      const response = await apiClient.post('/knowledge_base/populate_man_pages', {})
      return response
    } catch (error) {
      console.error('Error populating man pages:', error)
      throw error
    }
  }

  /**
   * Populate AutoBot documentation
   */
  const populateAutoBotDocs = async () => {
    try {
      const response = await apiClient.post('/knowledge_base/populate_autobot_docs', {})
      return response
    } catch (error) {
      console.error('Error populating AutoBot docs:', error)
      throw error
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
      return date.toLocaleString()
    } catch {
      return String(dateString)
    }
  }

  /**
   * Format date to locale date only (no time)
   */
  const formatDateOnly = (dateString: string | Date | undefined): string => {
    if (!dateString) return ''

    try {
      const date = typeof dateString === 'string' ? new Date(dateString) : dateString
      return date.toLocaleDateString()
    } catch {
      return String(dateString)
    }
  }

  /**
   * Format category name from snake_case to Title Case
   */
  const formatCategoryName = (category: string): string => {
    if (!category) return ''
    return category
      .split('_')
      .map(word => word && word.length > 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word)
      .join(' ')
  }

  /**
   * Format file size from bytes to human-readable format
   */
  const formatFileSize = (bytes: number | undefined): string => {
    if (!bytes) return 'Unknown size'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  /**
   * Format file size (compact version)
   */
  const formatFileSizeCompact = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  }

  /**
   * Format object key to Title Case (e.g., "total_facts" -> "Total Facts")
   */
  const formatKey = (key: string): string => {
    return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  }

  /**
   * Format timestamp to time string
   */
  const formatTime = (timestamp: number): string => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  }

  // ==================== UTILITY FUNCTIONS ====================

  /**
   * Get CSS class for OS type badge
   */
  const getOSBadgeClass = (osType?: string): string => {
    switch (osType) {
      case 'linux': return 'badge-success'
      case 'windows': return 'badge-info'
      case 'macos': return 'badge-warning'
      default: return 'badge-secondary'
    }
  }

  /**
   * Get icon class for category
   */
  const getCategoryIcon = (category: string): string => {
    const icons: Record<string, string> = {
      'system_commands': 'fas fa-terminal',
      'commands': 'fas fa-terminal',
      'troubleshooting': 'fas fa-wrench',
      'network': 'fas fa-network-wired',
      'file_system': 'fas fa-folder',
      'process': 'fas fa-cogs',
      'security': 'fas fa-shield-alt'
    }
    return icons[category] || 'fas fa-book'
  }

  /**
   * Get icon class for file type
   */
  const getFileIcon = (fileName: string, isFolder: boolean = false): string => {
    if (isFolder) return 'fas fa-folder'

    const name = fileName.toLowerCase()
    if (name.endsWith('.md') || name.endsWith('.markdown')) return 'fas fa-file-alt'
    if (name.endsWith('.txt')) return 'fas fa-file-alt'
    if (name.endsWith('.json')) return 'fas fa-file-code'
    if (name.endsWith('.pdf')) return 'fas fa-file-pdf'
    if (name.endsWith('.doc') || name.endsWith('.docx')) return 'fas fa-file-word'

    return 'fas fa-file'
  }

  /**
   * Get icon class for document type
   */
  const getTypeIcon = (type: string): string => {
    const icons: Record<string, string> = {
      'document': 'fas fa-file-alt',
      'webpage': 'fas fa-globe',
      'api': 'fas fa-code',
      'upload': 'fas fa-upload'
    }
    return icons[type] || 'fas fa-file'
  }

  /**
   * Get icon class for progress message type
   */
  const getMessageIcon = (type: string): string => {
    const icons: Record<string, string> = {
      'info': 'fas fa-info-circle text-blue-500',
      'success': 'fas fa-check-circle text-green-500',
      'warning': 'fas fa-exclamation-triangle text-yellow-500',
      'error': 'fas fa-times-circle text-red-500'
    }
    return icons[type] || icons.info
  }

  /**
   * Get icon class for progress status
   */
  const getProgressIcon = (status: string): string => {
    switch (status) {
      case 'success': return 'fa-check-circle'
      case 'error': return 'fa-exclamation-circle'
      case 'warning': return 'fa-exclamation-triangle'
      default: return 'fa-info-circle'
    }
  }

  // ==================== PROGRESS TRACKING ====================

  /**
   * Create a reactive progress state
   */
  const createProgressState = () => {
    return ref<ProgressState>({
      currentTask: '',
      taskDetail: '',
      overallProgress: 0,
      taskProgress: 0,
      status: 'waiting',
      messages: []
    })
  }

  /**
   * Add a progress message to the state
   */
  const addProgressMessage = (
    progressState: ProgressState,
    text: string,
    type: 'info' | 'success' | 'warning' | 'error' = 'info'
  ) => {
    const message: ProgressMessage = {
      text,
      type,
      timestamp: Date.now()
    }
    progressState.messages.push(message)

    // Keep only last 10 messages
    if (progressState.messages.length > 10) {
      progressState.messages = progressState.messages.slice(-10)
    }
  }

  /**
   * Update progress state
   */
  const updateProgress = (
    progressState: ProgressState,
    currentTask: string,
    overallProgress: number,
    taskDetail: string = '',
    taskProgress: number = 0,
    status: 'waiting' | 'running' | 'success' | 'error' = 'running'
  ) => {
    progressState.currentTask = currentTask
    progressState.taskDetail = taskDetail
    progressState.overallProgress = overallProgress
    progressState.taskProgress = taskProgress
    progressState.status = status
  }

  /**
   * Reset progress state
   */
  const resetProgress = (progressState: ProgressState) => {
    progressState.currentTask = ''
    progressState.taskDetail = ''
    progressState.overallProgress = 0
    progressState.taskProgress = 0
    progressState.status = 'waiting'
    progressState.messages = []
  }

  // ==================== RETURN ALL FUNCTIONS ====================

  return {
    // API calls
    fetchStats,
    fetchBasicStats,
    fetchMachineProfile,
    fetchManPagesSummary,
    initializeMachineKnowledge,
    integrateManPages,
    searchManPages,
    refreshSystemKnowledge,
    populateManPages,
    populateAutoBotDocs,

    // Formatting functions
    formatDate,
    formatDateOnly,
    formatCategoryName,
    formatFileSize,
    formatFileSizeCompact,
    formatKey,
    formatTime,

    // Utility functions
    getOSBadgeClass,
    getCategoryIcon,
    getFileIcon,
    getTypeIcon,
    getMessageIcon,
    getProgressIcon,

    // Progress tracking
    createProgressState,
    addProgressMessage,
    updateProgress,
    resetProgress
  }
}
