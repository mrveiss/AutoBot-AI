/**
 * Vue Composable for API Client Access
 *
 * This composable provides a clean way to access the centralized API client
 * in Vue 3 Composition API, with TypeScript support and error handling.
 */

import { inject } from 'vue'
import type { ApiClientType } from '../plugins/api'

/**
 * Composable to access the centralized API client
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
      } = {}
    ): Promise<T | null> {
      const {
        showErrorToast = true,
        fallbackValue = null,
        errorMessage = 'An error occurred while fetching data'
      } = options

      try {
        return await apiCall()
      } catch (error) {
        console.error('API call failed:', error)

        if (showErrorToast) {
          // You can integrate with your toast/notification system here
          console.error(errorMessage, error)
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
        { errorMessage: 'Failed to get API health status' }
      )
    }
  }
}

/**
 * Composable for chat-related API calls
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
        () => api.sendChatMessage(message, options),
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
        () => api.resetChat(),
        { errorMessage: 'Failed to reset chat' }
      )
    },

    /**
     * Save chat messages
     */
    async saveChatMessages(chatId: string, messages: any[]) {
      return withErrorHandling(
        () => api.saveChatMessages(chatId, messages),
        { errorMessage: 'Failed to save chat messages' }
      )
    }
  }
}

/**
 * Composable for settings-related API calls
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
    async updateSettings(settings: Record<string, any>) {
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
        () => api.getBackendSettings(),
        {
          errorMessage: 'Failed to load backend settings',
          fallbackValue: {}
        }
      )
    },

    /**
     * Update backend settings
     */
    async updateBackendSettings(settings: Record<string, any>) {
      return withErrorHandling(
        () => api.saveBackendSettings(settings),
        { errorMessage: 'Failed to update backend settings' }
      )
    }
  }
}

/**
 * Composable for knowledge base API calls
 */
export function useKnowledgeApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Search knowledge base
     */
    async search(query: string, limit = 10) {
      return withErrorHandling(
        () => api.searchKnowledge(query, limit),
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
        () => api.addTextToKnowledge(text, title, source),
        { errorMessage: 'Failed to add text to knowledge base' }
      )
    },

    /**
     * Add URL to knowledge base
     */
    async addUrl(url: string, method = 'fetch') {
      return withErrorHandling(
        () => api.addUrlToKnowledge(url, method),
        { errorMessage: 'Failed to add URL to knowledge base' }
      )
    },

    /**
     * Add file to knowledge base
     */
    async addFile(file: File) {
      return withErrorHandling(
        () => api.addFileToKnowledge(file),
        { errorMessage: 'Failed to add file to knowledge base' }
      )
    }
  }
}

/**
 * Composable for connection testing and status
 */
export function useConnectionStatus() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * Test API connection
     */
    async testConnection() {
      return withErrorHandling(
        () => api.testConnection(),
        {
          errorMessage: 'Connection test failed',
          fallbackValue: { connected: false, error: 'Connection test failed' }
        }
      )
    },

    /**
     * Get current base URL
     */
    getBaseUrl() {
      return api.getBaseUrl()
    },

    /**
     * Update base URL
     */
    setBaseUrl(url: string) {
      api.setBaseUrl(url)
    },

    /**
     * Update timeout
     */
    setTimeout(timeout: number) {
      api.setTimeout(timeout)
    }
  }
}

/**
 * Composable for file management operations
 */
export function useFileApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * List files in directory
     */
    async listFiles(path = '') {
      return withErrorHandling(
        () => api.listFiles(path),
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
        () => api.uploadFile(file, path, overwrite),
        { errorMessage: 'Failed to upload file' }
      )
    },

    /**
     * View file content
     */
    async viewFile(path: string) {
      return withErrorHandling(
        () => api.viewFile(path),
        { errorMessage: 'Failed to view file' }
      )
    },

    /**
     * Delete file
     */
    async deleteFile(path: string) {
      return withErrorHandling(
        () => api.deleteFile(path),
        { errorMessage: 'Failed to delete file' }
      )
    },

    /**
     * Download file
     */
    async downloadFile(path: string) {
      return withErrorHandling(
        () => api.downloadFile(path),
        { errorMessage: 'Failed to download file' }
      )
    },

    /**
     * Create directory
     */
    async createDirectory(path = '', name: string) {
      return withErrorHandling(
        () => api.createDirectory(path, name),
        { errorMessage: 'Failed to create directory' }
      )
    },

    /**
     * Get file system statistics
     */
    async getFileStats() {
      return withErrorHandling(
        () => api.getFileStats(),
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
