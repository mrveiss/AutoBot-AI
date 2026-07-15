// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Vue Composable for API Client Access
 *
 * @deprecated This composable family has been superseded. GH#7446 audit found zero
 * active callers outside legacy test mocks — do not add new callers.
 *
 * ## Decision rule: which API surface to use
 *
 * | Need                                            | Use                                                      |
 * |-------------------------------------------------|----------------------------------------------------------|
 * | Reactive GET with loading/error/data refs       | `useApiResource` → `useFetchEndpoint` (canonical layer)  |
 * | Imperative POST / PUT / DELETE                  | `useApiClient()` from `@/plugins/api`                    |
 * | One-off authenticated GET (no reactivity)       | `fetchWithAuth` from `@/utils/fetchWithAuth`             |
 * | Error wrapping + notifications for any call     | `useAsyncHandler` from `@/composables/useErrorHandler`   |
 *
 * ### useApi vs useApiResource vs useFetchEndpoint
 *
 * - `useApi` (this file) — legacy inject-based accessor. Deprecated, no new callers.
 * - `useApiResource` — lower-level reactive wrapper around any `async () => T` fetcher.
 *   Race-condition safe, AbortController integrated. Used internally by useFetchEndpoint.
 * - `useFetchEndpoint` — canonical GET data-loader built on useApiResource. Handles URL
 *   resolution, auth, and source-scoping. **Use this for all new reactive data loading.**
 *
 * Sunset: Q3 2026. See GH#6487 for migration history, GH#7446 for consolidation audit.
 */

import { inject } from 'vue'
import type { ApiClientType } from '../plugins/api'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

// Create scoped logger for useApi
const logger = createLogger('useApi')

/**
 * Composable to access the centralized API client
 *
 * @deprecated Use `useApiClient()` from `@/plugins/api` for imperative HTTP calls,
 * or `useFetchEndpoint` from `@/composables/api/useFetchEndpoint` for data loading.
 *
 * @returns {ApiClientType} The configured API client instance
 * @throws {Error} If API client is not available (plugin not installed)
 */
export function useApi(): ApiClientType {
  const apiClient = inject<ApiClientType>('apiClient')

  if (!apiClient) {
    throw new Error(
      'API client not found. Make sure the API plugin is installed in your Vue app:\n' +
      'app.use(ApiPlugin, { baseURL: "your-api-url" })'
    )
  }

  return apiClient
}

/**
 * Composable for API calls with built-in error handling and loading states
 *
 * @deprecated Use `useFetchEndpoint({ onError, fallbackData })` from `@/composables/api/useFetchEndpoint`.
 *
 * @returns Object with API client and utility functions
 */
export function useApiWithState() {
  const api = useApi()

  return {
    api,

    /**
     * Wrapper for API calls with standardized error handling
     *
     * @param apiCall - Function that returns a Promise (API call)
     * @param options - Configuration options
     * @returns Promise with standardized error handling
     */
    async withErrorHandling<T>(
      apiCall: () => Promise<T>,
      options: {
        showErrorToast?: boolean
        fallbackValue?: T
        errorMessage?: string
        silent?: boolean
      } = {}
    ): Promise<T | null> {
      const {
        showErrorToast = true,
        fallbackValue = null,
        errorMessage = 'An error occurred while fetching data',
        silent = false
      } = options

      try {
        return await apiCall()
      } catch (error: unknown) {
        logger.error('API call failed:', error)

        if (showErrorToast && !silent) {
          // Issue #156 Fix: Extract error properties with type guards
          interface HttpErrorLike { response?: { data?: { detail?: string }; status?: number }; message?: string }
          const errorObj = error as HttpErrorLike
          const errMsg = error instanceof Error ? error.message : ''

          // Use subtle error notification instead of intrusive popup
          const fullErrorMessage = errorObj.response?.data?.detail || errMsg || errorMessage

          // Check if this is a network/server error
          const isServerError = (errorObj.response?.status ?? 0) >= 500 || errMsg.includes('HTTP 500')
          const isNetworkError = errMsg.includes('Failed to fetch') || errMsg.includes('Network Error')

          // Determine severity
          const severity = (isServerError || isNetworkError) ? 'warning' : 'error'

          // Show subtle notification
          showSubtleErrorNotification(
            isServerError ? 'Server Error' : isNetworkError ? 'Connection Error' : 'API Error',
            fullErrorMessage,
            severity
          )
        }

        return fallbackValue as T
      }
    },

    /**
     * Helper to check API connection status
     *
     * @returns Promise<boolean> - true if API is reachable
     */
    async checkConnection(): Promise<boolean> {
      try {
        await api.checkHealth()
        return true
      } catch {
        return false
      }
    },

    /**
     * Helper to get API health status
     *
     * @returns Promise with health information
     */
    async getHealthStatus() {
      return this.withErrorHandling(
        () => api.checkHealth(),
        {
          errorMessage: 'Failed to get API health status',
          silent: true // Health checks shouldn't show user notifications
        }
      )
    }
  }
}

/**
 * Composable for chat-related API calls
 *
 * @deprecated Use `useFetchEndpoint` for data loading or `useApiClient()` for imperative calls.
 *
 * @returns Object with chat-specific API methods
 */
export function useChatApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Send a chat message
     */
    async sendMessage(message: string, options: { sessionId?: string } = {}) {
      return withErrorHandling(
        // #9724: ChatMessageOptions has no `sessionId` field — the previous
        // pass-through silently dropped the session id (message went to a
        // null session). Map it to the supported `chatId` field.
        () => api.sendChatMessage(message, { chatId: options.sessionId }),
        { errorMessage: 'Failed to send message' }
      )
    },

    /**
     * Get chat list
     */
    async getChatList() {
      return withErrorHandling(
        () => api.getChatList(),
        {
          errorMessage: 'Failed to load chat list',
          fallbackValue: { chats: [] }
        }
      )
    },

    /**
     * Get chat messages
     */
    async getChatMessages(chatId: string) {
      return withErrorHandling(
        () => api.getChatMessages(chatId),
        {
          errorMessage: 'Failed to load chat messages',
          fallbackValue: { history: [] }
        }
      )
    },

    /**
     * Create new chat
     */
    async createNewChat() {
      return withErrorHandling(
        () => api.createNewChat(),
        { errorMessage: 'Failed to create new chat' }
      )
    },

    /**
     * Delete chat
     */
    async deleteChat(chatId: string) {
      return withErrorHandling(
        () => api.deleteChat(chatId),
        { errorMessage: 'Failed to delete chat' }
      )
    },

    /**
     * Reset chat
     */
    async resetChat() {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have resetChat(), use direct HTTP call
        async () => {
          return await api.post<unknown>(`${getApiBase()}/chat/reset`)
        },
        { errorMessage: 'Failed to reset chat' }
      )
    },

    /**
     * Save chat messages
     */
    async saveChatMessages(chatId: string, messages: Record<string, unknown>[]) {
      return withErrorHandling(
        () => api.saveChatMessages(chatId, messages),
        { errorMessage: 'Failed to save chat - connection issue. Your messages are safely stored locally.' }
      )
    }
  }
}

/**
 * Composable for settings-related API calls
 *
 * @deprecated Use `useFetchEndpoint` for data loading or `useApiClient()` for imperative calls.
 *
 * @returns Object with settings-specific API methods
 */
export function useSettingsApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Get current settings
     */
    async getSettings() {
      return withErrorHandling(
        () => api.getSettings(),
        {
          errorMessage: 'Failed to load settings',
          fallbackValue: {}
        }
      )
    },

    /**
     * Update settings
     */
    async updateSettings(settings: Record<string, unknown>) {
      return withErrorHandling(
        () => api.saveSettings(settings),
        { errorMessage: 'Failed to update settings' }
      )
    },

    /**
     * Get backend settings
     */
    async getBackendSettings() {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have getBackendSettings(), use direct HTTP call
        async () => {
          return await api.get<unknown>(`${getApiBase()}/settings/backend`)
        },
        {
          errorMessage: 'Failed to load backend settings',
          fallbackValue: {}
        }
      )
    },

    /**
     * Update backend settings
     */
    async updateBackendSettings(settings: Record<string, unknown>) {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have saveBackendSettings(), use direct HTTP call
        async () => {
          return await api.post<unknown>(`${getApiBase()}/settings/backend`, settings)
        },
        { errorMessage: 'Failed to update backend settings' }
      )
    }
  }
}

/**
 * Composable for knowledge base API calls
 *
 * @deprecated Use `useFetchEndpoint` for data loading or `useApiClient()` for imperative calls.
 */
export function useKnowledgeApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Search knowledge base
     */
    async search(query: string, limit = 10) {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have searchKnowledge(), use direct HTTP call
        async () => {
          return await api.get<unknown>(`${getApiBase()}/knowledge/search?query=${encodeURIComponent(query)}&limit=${limit}`)
        },
        {
          errorMessage: 'Failed to search knowledge base',
          fallbackValue: { results: [] }
        }
      )
    },

    /**
     * Add text to knowledge base
     */
    async addText(text: string, title?: string, source?: string) {
      return withErrorHandling(
        // Issue #549 Fix: Use correct path /api/knowledge_base/facts
        async () => {
          return await api.post<unknown>(`${getApiBase()}/knowledge_base/facts`, { content: text, title, source })
        },
        { errorMessage: 'Failed to add text to knowledge base' }
      )
    },

    /**
     * Add URL to knowledge base
     */
    async addUrl(url: string, method = 'fetch') {
      return withErrorHandling(
        // Issue #549 Fix: Use correct path /api/knowledge_base/url
        async () => {
          return await api.post<unknown>(`${getApiBase()}/knowledge_base/url`, { url, method })
        },
        { errorMessage: 'Failed to add URL to knowledge base' }
      )
    },

    /**
     * Add file to knowledge base
     */
    async addFile(file: File) {
      return withErrorHandling(
        // Issue #549 Fix: Use correct path /api/knowledge_base/upload
        async () => {
          const formData = new FormData()
          formData.append('file', file)
          return await api.post<unknown>(`${getApiBase()}/knowledge_base/upload`, formData)
        },
        { errorMessage: 'Failed to add file to knowledge base' }
      )
    }
  }
}

/**
 * Composable for connection testing and status
 *
 * @deprecated Use `useApiClient()` from `@/plugins/api` for direct API access.
 */
export function useConnectionStatus() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Test API connection
     */
    async testConnection() {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have testConnection(), use checkHealth() instead
        async () => {
          const result = await api.checkHealth()
          // Issue #156 Fix: Use null as string | null to allow both null and string in error property
          return { connected: true, result, error: null as string | null }
        },
        {
          errorMessage: 'Connection test failed',
          fallbackValue: { connected: false, result: false, error: 'Connection test failed' },
          silent: true // Connection tests shouldn't show user notifications
        }
      )
    },

    /**
     * Get current base URL
     */
    getBaseUrl() {
      // Use public getConfiguration() to read the private baseUrl field
      return String(api.getConfiguration().baseUrl || '')
    },

    /**
     * Update base URL
     */
    setBaseUrl(url: string) {
      // Use public setBaseUrl() method
      api.setBaseUrl(url)
    },

    /**
     * Update timeout
     */
    setTimeout(timeout: number) {
      // Use public setTimeout() method
      api.setTimeout(timeout)
    }
  }
}

/**
 * Composable for file management operations
 *
 * @deprecated Use `useFetchEndpoint` for data loading or `useApiClient()` for imperative calls.
 */
export function useFileApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * List files in directory
     */
    async listFiles(path = '') {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have listFiles(), use direct HTTP call
        async () => {
          return await api.get<unknown>(`${getApiBase()}/files/list?path=${encodeURIComponent(path)}`)
        },
        {
          errorMessage: 'Failed to list files',
          fallbackValue: {
            current_path: path,
            files: [],
            total_files: 0,
            total_directories: 0,
            total_size: 0
          }
        }
      )
    },

    /**
     * Upload file
     */
    async uploadFile(file: File, path = '', overwrite = false) {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have uploadFile(), use direct HTTP call
        async () => {
          const formData = new FormData()
          formData.append('file', file)
          formData.append('path', path)
          formData.append('overwrite', String(overwrite))
          return await api.post<unknown>(`${getApiBase()}/files/upload`, formData)
        },
        { errorMessage: 'Failed to upload file' }
      )
    },

    /**
     * View file content
     */
    async viewFile(path: string) {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have viewFile(), use direct HTTP call
        async () => {
          return await api.get<unknown>(`${getApiBase()}/files/view?path=${encodeURIComponent(path)}`)
        },
        { errorMessage: 'Failed to view file' }
      )
    },

    /**
     * Delete file
     */
    async deleteFile(path: string) {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have deleteFile(), use direct HTTP call
        async () => {
          return await api.delete<unknown>(`${getApiBase()}/files?path=${encodeURIComponent(path)}`)
        },
        { errorMessage: 'Failed to delete file' }
      )
    },

    /**
     * Download file
     */
    async downloadFile(path: string) {
      return withErrorHandling(
        // Issue #552: Fixed path - backend uses path param /download/{path}, not query param
        // #7274: file downloads need raw Response (.blob()), bypass JSON-parsing convenience
        async () => {
          const response = await api.rawRequest(`${getApiBase()}/files/download/${encodeURIComponent(path)}`, { method: 'GET' })
          return await response.blob()
        },
        { errorMessage: 'Failed to download file' }
      )
    },

    /**
     * Create directory
     */
    async createDirectory(path = '', name: string) {
      return withErrorHandling(
        // Issue #549 Fix: Use correct path /api/files/create_directory with FormData
        async () => {
          const formData = new FormData()
          formData.append('path', path)
          formData.append('name', name)
          return await api.post<unknown>(`${getApiBase()}/files/create_directory`, formData)
        },
        { errorMessage: 'Failed to create directory' }
      )
    },

    /**
     * Get file system statistics
     */
    async getFileStats() {
      return withErrorHandling(
        // Issue #156 Fix: ApiClient doesn't have getFileStats(), use direct HTTP call
        async () => {
          return await api.get<unknown>(`${getApiBase()}/files/stats`)
        },
        {
          errorMessage: 'Failed to get file statistics',
          fallbackValue: {
            sandbox_root: '',
            total_files: 0,
            total_directories: 0,
            total_size: 0,
            total_size_mb: 0,
            max_file_size_mb: 50,
            allowed_extensions: []
          }
        }
      )
    }
  }
}
