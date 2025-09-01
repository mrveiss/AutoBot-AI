/**
 * Batch API Service for optimized loading
 * Combines multiple API calls into single requests to reduce round trips
 */

import { ApiClient } from '@/utils/ApiClient.js'

class BatchApiService {
  constructor() {
    this.apiClient = new ApiClient()
  }

  /**
   * Execute multiple API requests in parallel via batch endpoint
   */
  async batchLoad(requests) {
    try {
      console.log('🚀 Executing batch load with', requests.length, 'requests')
      
      const response = await this.apiClient.post('/api/batch/load', {
        requests
      })
      
      console.log('✅ Batch load completed:', response)
      return response
      
    } catch (error) {
      console.error('❌ Batch load failed:', error)
      throw error
    }
  }

  /**
   * Optimized chat initialization that loads everything needed for chat interface
   */
  async initializeChatInterface() {
    try {
      console.log('🚀 Initializing chat interface via batch API')
      
      const response = await this.apiClient.post('/api/batch/chat-init')
      
      console.log('✅ Chat interface initialization completed:', response)
      return response
      
    } catch (error) {
      console.error('❌ Chat initialization failed:', error)
      // Fallback to individual API calls if batch fails
      return await this.fallbackChatInitialization()
    }
  }

  /**
   * Fallback initialization using individual API calls
   */
  async fallbackChatInitialization() {
    console.log('🔄 Using fallback chat initialization')
    
    const results = {}
    
    try {
      // Load chat sessions
      try {
        results.chat_sessions = await this.apiClient.get('/api/chat/chats')
      } catch (error) {
        console.warn('Failed to load chat sessions:', error)
        results.chat_sessions = { error: error.message }
      }

      // Load system health
      try {
        results.system_health = await this.apiClient.get('/api/system/health')
      } catch (error) {
        console.warn('Failed to load system health:', error)
        results.system_health = { error: error.message }
      }

      // Load service health
      try {
        results.service_health = await this.apiClient.get('/api/monitoring/services/health')
      } catch (error) {
        console.warn('Failed to load service health:', error)
        results.service_health = { error: error.message }
      }

      // Mock KB stats since it's simplified in batch
      results.kb_stats = {
        total_documents: 0,
        total_chunks: 0,
        categories: [],
        total_facts: 0
      }

    } catch (error) {
      console.error('Fallback initialization failed:', error)
      throw error
    }

    return results
  }

  /**
   * Build batch request configuration
   */
  buildBatchRequest(endpoints) {
    return endpoints.map(endpoint => ({
      endpoint: endpoint.url,
      method: endpoint.method || 'GET',
      params: endpoint.params || {}
    }))
  }

  /**
   * Load initial page data for any component
   */
  async loadInitialPageData(endpoints) {
    const requests = this.buildBatchRequest(endpoints)
    return await this.batchLoad(requests)
  }
}

// Create singleton instance
const batchApiService = new BatchApiService()

export default batchApiService
export { BatchApiService }