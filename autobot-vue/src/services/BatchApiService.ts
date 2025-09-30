/**
 * Batch API Service - Optimized service for batching multiple API calls
 * Updated to use correct ApiClient singleton with proper error handling
 */

import apiClient from '@/utils/ApiClient.ts';
import type { ApiClient } from '@/utils/ApiClient.ts';

// Type definitions
interface ChatInitData {
  messages: any[];
  session_info: any;
  user_preferences: any;
}

interface FallbackResults {
  chat_sessions: any;
  system_health: any;
  service_health: any;
  settings: any;
}

interface BatchRequest {
  endpoint: string;
  method: string;
  data?: any;
  priority?: number;
}

export class BatchApiService {
  private apiClient: ApiClient;
  private requestQueue: BatchRequest[] = [];
  private processing = false;

  constructor(client?: ApiClient) {
    // Use provided client or the singleton instance
    this.apiClient = client || apiClient;
  }

  /**
   * DEPRECATED: Backend doesn't have /api/batch/chat-init endpoint
   * Using fallback method to load chat interface data
   */
  async initializeChatInterface(): Promise<any> {
    console.warn('Batch chat initialization endpoint does not exist. Using fallback individual API calls.');
    return await this.fallbackChatInitialization();
  }

  /**
   * DEPRECATED: Backend doesn't have /api/batch/chat-init/{sessionId} endpoint
   * Load chat initialization data for a specific session using individual calls
   */
  async loadChatInitData(sessionId: string): Promise<ChatInitData> {
    console.warn('Batch chat init data endpoint does not exist. Using individual API calls.');

    try {
      // Get session messages
      const messages = await this.apiClient.getChatMessages(sessionId);

      // Get basic session info (this would need to be implemented if needed)
      const session_info = { id: sessionId };

      // Get user preferences from settings
      let user_preferences = {};
      try {
        const settings = await this.apiClient.getSettings();
        user_preferences = settings.user_preferences || {};
      } catch (error) {
        console.warn('Could not load user preferences:', error);
      }

      return {
        messages: messages.messages || [],
        session_info,
        user_preferences
      };
    } catch (error) {
      console.error('Failed to load chat init data:', error);
      // Return default structure
      return {
        messages: [],
        session_info: { id: sessionId },
        user_preferences: {}
      };
    }
  }

  /**
   * Fallback chat initialization using individual API calls with graceful error handling
   */
  async fallbackChatInitialization(): Promise<FallbackResults> {
    console.log('🔄 Using fallback chat initialization with individual API calls');

    const results: FallbackResults = {
      chat_sessions: { sessions: [] },
      system_health: { status: 'unknown' },
      service_health: { services: [] },
      settings: {}
    };

    // Load chat sessions using correct endpoint with error handling
    try {
      results.chat_sessions = await this.apiClient.getChatList();
    } catch (error: any) {
      console.warn('Failed to load chat sessions:', error.message);
      results.chat_sessions = { error: error.message, sessions: [] };
    }

    // Load system health with error handling
    try {
      results.system_health = await this.apiClient.getSystemHealth();
    } catch (error: any) {
      console.warn('Failed to load system health:', error.message);
      results.system_health = { error: error.message, status: 'unknown' };
    }

    // Load service health with error handling
    try {
      results.service_health = await this.apiClient.getServiceHealth();
    } catch (error: any) {
      console.warn('Failed to load service health:', error.message);
      results.service_health = { error: error.message, services: [] };
    }

    // Load settings with error handling
    try {
      results.settings = await this.apiClient.getSettings();
    } catch (error: any) {
      console.warn('Failed to load settings:', error.message);
      results.settings = { error: error.message };
    }

    console.log('✅ Fallback chat initialization completed');
    return results;
  }

  /**
   * Batch multiple API requests using Promise.allSettled
   * This replaces the non-existent batch endpoints with parallel individual calls
   */
  async batchRequests(requests: BatchRequest[]): Promise<any[]> {
    console.log(`🚀 Processing ${requests.length} requests in parallel`);

    const promises = requests.map(async (request) => {
      try {
        let response;
        const { endpoint, method, data } = request;

        switch (method.toUpperCase()) {
          case 'GET':
            response = await this.apiClient.get(endpoint);
            break;
          case 'POST':
            response = await this.apiClient.post(endpoint, data);
            break;
          case 'PUT':
            response = await this.apiClient.put(endpoint, data);
            break;
          case 'DELETE':
            response = await this.apiClient.delete(endpoint);
            break;
          default:
            throw new Error(`Unsupported method: ${method}`);
        }

        return {
          endpoint,
          method,
          success: true,
          data: response
        };
      } catch (error: any) {
        console.warn(`Failed request ${method} ${endpoint}:`, error.message);
        return {
          endpoint,
          method,
          success: false,
          error: error.message
        };
      }
    });

    const results = await Promise.allSettled(promises);

    return results.map((result, index) => {
      if (result.status === 'fulfilled') {
        return result.value;
      } else {
        return {
          endpoint: requests[index].endpoint,
          method: requests[index].method,
          success: false,
          error: result.reason?.message || String(result.reason)
        };
      }
    });
  }

  /**
   * Add request to queue for batch processing
   */
  queueRequest(endpoint: string, method: string, data?: any, priority: number = 0): void {
    this.requestQueue.push({ endpoint, method, data, priority });

    // Sort by priority (higher priority first)
    this.requestQueue.sort((a, b) => (b.priority || 0) - (a.priority || 0));
  }

  /**
   * Process queued requests in batch
   */
  async processQueue(): Promise<any[]> {
    if (this.processing || this.requestQueue.length === 0) {
      return [];
    }

    this.processing = true;
    const requests = [...this.requestQueue];
    this.requestQueue = [];

    try {
      const results = await this.batchRequests(requests);
      return results;
    } finally {
      this.processing = false;
    }
  }

  /**
   * Clear the request queue
   */
  clearQueue(): void {
    this.requestQueue = [];
  }

  /**
   * Get queue status
   */
  getQueueStatus(): { length: number; processing: boolean } {
    return {
      length: this.requestQueue.length,
      processing: this.processing
    };
  }

  /**
   * Optimized method to load essential chat data with graceful degradation
   */
  async loadEssentialChatData(): Promise<any> {
    const essentialRequests: BatchRequest[] = [
      { endpoint: '/api/chats', method: 'GET', priority: 3 },
      { endpoint: '/api/chat/health', method: 'GET', priority: 2 },
      { endpoint: '/api/health', method: 'GET', priority: 1 }
    ];

    const results = await this.batchRequests(essentialRequests);

    return {
      chat_sessions: results.find(r => r.endpoint === '/api/chats' && r.success)?.data || { sessions: [] },
      chat_health: results.find(r => r.endpoint === '/api/chat/health' && r.success)?.data || { status: 'unknown' },
      system_health: results.find(r => r.endpoint === '/api/health' && r.success)?.data || { status: 'unknown' }
    };
  }

  /**
   * Load chat interface with health checks and graceful degradation
   */
  async loadChatWithHealthChecks(): Promise<any> {
    try {
      // First, check if the system is healthy
      const healthCheck = await this.apiClient.checkHealth();

      if (!healthCheck || healthCheck.status !== 'healthy') {
        console.warn('System health check failed, loading minimal data');
        return {
          chat_sessions: { sessions: [] },
          health_status: healthCheck || { status: 'unknown' },
          error: 'System health check failed'
        };
      }

      // If healthy, load full chat data
      return await this.loadEssentialChatData();
    } catch (error) {
      console.error('Failed to load chat with health checks:', error);
      return {
        chat_sessions: { sessions: [] },
        error: (error as Error).message
      };
    }
  }
}

// Export singleton instance using the correct ApiClient singleton
export const batchApiService = new BatchApiService(apiClient);
export default batchApiService;