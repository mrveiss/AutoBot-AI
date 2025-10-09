/**
 * useKnowledgeBase Composable
 *
 * Shared functions for knowledge base management across all knowledge manager components.
 * This composable eliminates duplicate code and provides a consistent API interface.
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'

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
  const parseResponse = async (response: any): Promise<any> => {
    try {
      // Check if response is already parsed data
      if (response && typeof response === 'object' && typeof response.json !== 'function') {
        return response
      }

      // Check if response has json() method (fetch Response object)
      if (typeof response.json === 'function') {
        // Clone the response to avoid consuming the body if we need to debug
        const clonedResponse = response.clone()

        try {
          const data = await response.json()
          return data
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
      return response
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

      // Check response status
      if (!response.ok) {
        console.error('Stats fetch failed with status:', response.status)
        const errorText = await response.text()
        console.error('Error response:', errorText)
        throw new Error(`Failed to fetch stats: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
      return data
    } catch (error) {
      console.error('Error fetching stats:', error)
      throw error
    }
  }

  /**
   * Fetch knowledge by category
   */
  const fetchCategory = async (category: string): Promise<any> => {
    try {
      const response = await apiClient.get(`/api/knowledge_base/category/${category}`)

      if (!response.ok) {
        console.error('Category fetch failed with status:', response.status)
        throw new Error(`Failed to fetch category: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
      return data
    } catch (error) {
      console.error('Error fetching category:', error)
      throw error
    }
  }

  /**
   * Search knowledge base
   */
  const searchKnowledge = async (query: string): Promise<any> => {
    try {
      const response = await apiClient.get(`/api/knowledge_base/search?query=${encodeURIComponent(query)}`)

      if (!response.ok) {
        console.error('Search failed with status:', response.status)
        throw new Error(`Search failed: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
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
    metadata?: Record<string, any>
  }): Promise<any> => {
    try {
      const response = await apiClient.post('/api/knowledge_base/facts', fact)

      if (!response.ok) {
        console.error('Add fact failed with status:', response.status)
        const errorText = await response.text()
        console.error('Error response:', errorText)
        throw new Error(`Failed to add fact: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
      return data
    } catch (error) {
      console.error('Error adding fact:', error)
      throw error
    }
  }

  /**
   * Upload knowledge base file
   */
  const uploadKnowledgeFile = async (formData: FormData): Promise<any> => {
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

      const data = await parseResponse(response)
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

      if (!response.ok) {
        console.error('Machine profiles fetch failed with status:', response.status)
        throw new Error(`Failed to fetch machine profiles: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
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

      if (!response.ok) {
        console.error('Man pages summary fetch failed with status:', response.status)
        throw new Error(`Failed to fetch man pages summary: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
      return data
    } catch (error) {
      console.error('Error fetching man pages summary:', error)
      return null
    }
  }

  /**
   * Integrate man pages for a specific machine
   */
  const integrateManPages = async (machineId: string): Promise<any> => {
    try {
      const response = await apiClient.post('/api/knowledge_base/man_pages/integrate', {
        machine_id: machineId
      })

      if (!response.ok) {
        console.error('Man pages integration failed with status:', response.status)
        const errorText = await response.text()
        console.error('Error response:', errorText)
        throw new Error(`Integration failed: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
      return data
    } catch (error) {
      console.error('Error integrating man pages:', error)
      throw error
    }
  }

  /**
   * Get vectorization status
   */
  const getVectorizationStatus = async (): Promise<any> => {
    try {
      const response = await apiClient.get('/api/knowledge_base/vectorization/status')

      if (!response.ok) {
        console.error('Vectorization status fetch failed with status:', response.status)
        throw new Error(`Failed to get vectorization status: ${response.status} ${response.statusText}`)
      }

      const data = await parseResponse(response)
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
  ) => {
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

      // Check response status BEFORE parsing
      if (!response.ok) {
        console.error('[vectorizeFacts] Request failed with status:', response.status)

        // Try to get error details from response
        let errorMessage = `Vectorization failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[vectorizeFacts] Error response text:', errorText)

          // Try to parse error as JSON
          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            // Not JSON, use text as-is
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[vectorizeFacts] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      // Parse successful response
      console.log('[vectorizeFacts] Parsing successful response...')
      const data = await parseResponse(response)
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
  const initializeMachineKnowledge = async (machineId: string): Promise<any> => {
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

      if (!response.ok) {
        console.error('[initializeMachineKnowledge] Request failed with status:', response.status)

        let errorMessage = `Machine knowledge initialization failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[initializeMachineKnowledge] Error response text:', errorText)

          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[initializeMachineKnowledge] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      const data = await parseResponse(response)
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
  const refreshSystemKnowledge = async (): Promise<any> => {
    try {
      console.log('[refreshSystemKnowledge] Starting refresh request...')

      const response = await apiClient.post('/api/knowledge_base/refresh_system_knowledge', {})

      console.log('[refreshSystemKnowledge] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response.ok) {
        console.error('[refreshSystemKnowledge] Request failed with status:', response.status)

        let errorMessage = `System knowledge refresh failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[refreshSystemKnowledge] Error response text:', errorText)

          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[refreshSystemKnowledge] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      const data = await parseResponse(response)
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
  const populateManPages = async (machineId: string): Promise<any> => {
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

      if (!response.ok) {
        console.error('[populateManPages] Request failed with status:', response.status)

        let errorMessage = `Man pages population failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[populateManPages] Error response text:', errorText)

          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[populateManPages] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      const data = await parseResponse(response)
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
  const populateAutoBotDocs = async (): Promise<any> => {
    try {
      console.log('[populateAutoBotDocs] Starting documentation population request...')

      const response = await apiClient.post('/api/knowledge_base/populate_autobot_docs', {})

      console.log('[populateAutoBotDocs] Response received:', {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText
      })

      if (!response.ok) {
        console.error('[populateAutoBotDocs] Request failed with status:', response.status)

        let errorMessage = `AutoBot docs population failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[populateAutoBotDocs] Error response text:', errorText)

          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[populateAutoBotDocs] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      const data = await parseResponse(response)
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

      if (!response.ok) {
        console.error('[fetchMachineProfile] Request failed with status:', response.status)

        let errorMessage = `Machine profile fetch failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[fetchMachineProfile] Error response text:', errorText)

          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[fetchMachineProfile] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      const data = await parseResponse(response)
      console.log('[fetchMachineProfile] Success:', data)
      return data
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

      if (!response.ok) {
        console.error('[fetchBasicStats] Request failed with status:', response.status)

        let errorMessage = `Basic stats fetch failed: ${response.status} ${response.statusText}`
        try {
          const errorText = await response.text()
          console.error('[fetchBasicStats] Error response text:', errorText)

          try {
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch {
            if (errorText) {
              errorMessage = errorText
            }
          }
        } catch (textError) {
          console.error('[fetchBasicStats] Could not read error response:', textError)
        }

        throw new Error(errorMessage)
      }

      const data = await parseResponse(response)
      console.log('[fetchBasicStats] Success:', data)
      return data
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
    // Helper function
    parseResponse
  }
}
