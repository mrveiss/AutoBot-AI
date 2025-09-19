/**
 * Batch API Service for optimized loading
 * Combines multiple API calls into single requests to reduce round trips
 */

import { ApiClient } from '@/utils/ApiClient'

// TypeScript interfaces
export interface BatchRequest {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: any;
  headers?: Record<string, string>;
}

export interface BatchResponse {
  success: boolean;
  data: any;
  error?: string;
}

export interface BatchEndpoint {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  params?: Record<string, any>;
}

export interface ChatInitData {
  messages: any[];
  sessionInfo: any;
  knowledgeStats: any;
  systemStatus: any;
}

export interface FallbackResults {
  chat_sessions: any;
  system_health: any;
  service_health: any;
  kb_stats: {
    total_documents: number;
    total_chunks: number;
    categories: any[];
    total_facts: number;
  };
}

class BatchApiService {
  private apiClient: ApiClient;

  constructor() {
    this.apiClient = new ApiClient();
  }

  /**
   * Execute multiple API requests in parallel via batch endpoint
   */
  async batchLoad(requests: BatchRequest[]): Promise<BatchResponse[]> {
    try {
      console.log('🚀 Executing batch load with', requests.length, 'requests');

      const response = await this.apiClient.post('/api/batch/load', {
        requests
      });

      console.log('✅ Batch load completed:', response);
      return response;

    } catch (error) {
      console.error('❌ Batch load failed:', error);
      throw error;
    }
  }

  /**
   * Optimized chat initialization that loads everything needed for chat interface
   */
  async initializeChatInterface(): Promise<any> {
    try {
      console.log('🚀 Initializing chat interface via batch API');

      const response = await this.apiClient.post('/api/batch/chat-init');

      console.log('✅ Chat interface initialization completed:', response);
      return response;

    } catch (error) {
      console.error('❌ Chat initialization failed:', error);
      // Fallback to individual API calls if batch fails
      return await this.fallbackChatInitialization();
    }
  }

  /**
   * Load chat initialization data for a specific session
   */
  async loadChatInitData(sessionId: string): Promise<ChatInitData> {
    try {
      const response = await this.apiClient.get(`/api/batch/chat-init/${sessionId}`);
      return response;
    } catch (error) {
      console.error('Failed to load chat init data:', error);
      // Return default structure
      return {
        messages: [],
        sessionInfo: { id: sessionId, created: Date.now() },
        knowledgeStats: { total_documents: 0, total_chunks: 0 },
        systemStatus: { status: 'unknown' }
      };
    }
  }

  /**
   * Fallback initialization using individual API calls
   */
  async fallbackChatInitialization(): Promise<FallbackResults> {
    console.log('🔄 Using fallback chat initialization');

    const results: Partial<FallbackResults> = {};

    try {
      // Load chat sessions
      try {
        results.chat_sessions = await this.apiClient.get('/api/chat/chats');
      } catch (error: any) {
        console.warn('Failed to load chat sessions:', error);
        results.chat_sessions = { error: error.message };
      }

      // Load system health
      try {
        results.system_health = await this.apiClient.get('/api/health');
      } catch (error: any) {
        console.warn('Failed to load system health:', error);
        results.system_health = { error: error.message };
      }

      // Load service health
      try {
        results.service_health = await this.apiClient.get('/api/services/health');
      } catch (error: any) {
        console.warn('Failed to load service health:', error);
        results.service_health = { error: error.message };
      }

      // Mock KB stats since it's simplified in batch
      results.kb_stats = {
        total_documents: 0,
        total_chunks: 0,
        categories: [],
        total_facts: 0
      };

    } catch (error) {
      console.error('Fallback initialization failed:', error);
      throw error;
    }

    return results as FallbackResults;
  }

  /**
   * Build batch request configuration
   */
  buildBatchRequest(endpoints: BatchEndpoint[]): BatchRequest[] {
    return endpoints.map(endpoint => ({
      url: endpoint.url,
      method: endpoint.method || 'GET',
      data: endpoint.params || {}
    }));
  }

  /**
   * Load initial page data for any component
   */
  async loadInitialPageData(endpoints: BatchEndpoint[]): Promise<BatchResponse[]> {
    const requests = this.buildBatchRequest(endpoints);
    return await this.batchLoad(requests);
  }
}

// Create singleton instance
const batchApiService = new BatchApiService();

export default batchApiService;
export { BatchApiService };