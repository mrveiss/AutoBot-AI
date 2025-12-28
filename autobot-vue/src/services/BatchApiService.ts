/**
 * Batch API Service - Optimized service for batching multiple API calls
 * Updated to use correct ApiClient singleton with proper error handling
 */

import apiClient from '@/utils/ApiClient.ts';
import type { ApiClient } from '@/utils/ApiClient.ts';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for BatchApiService
const logger = createLogger('BatchApiService');

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
   * Load chat interface data using individual API calls.
   * Note: Batch endpoint doesn't exist, so we use parallel individual calls instead.
   */
  async initializeChatInterface(): Promise<any> {
    // Debug level - this is expected behavior, not a warning condition
    logger.debug('Using individual API calls for chat initialization');
    return await this.fallbackChatInitialization();
  }

  /**
   * Load chat initialization data for a specific session using individual calls.
   * Note: Batch endpoint doesn't exist, so we use parallel individual calls instead.
   */
  async loadChatInitData(sessionId: string): Promise<ChatInitData> {
    logger.debug('Loading chat init data for session:', sessionId);

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
        logger.warn('Could not load user preferences:', error);
      }

      return {
        messages: messages.messages || [],
        session_info,
        user_preferences
      };
    } catch (error) {
      logger.error('Failed to load chat init data:', error);
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
    logger.info('Using fallback chat initialization with individual API calls');

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
      logger.warn('Failed to load chat sessions:', error.message);
      results.chat_sessions = { error: error.message, sessions: [] };
    }

    // Load system health with error handling
    try {
      results.system_health = await this.apiClient.getSystemHealth();
    } catch (error: any) {
      logger.warn('Failed to load system health:', error.message);
      results.system_health = { error: error.message, status: 'unknown' };
    }

    // Load service health with error handling
    try {
      results.service_health = await this.apiClient.getServiceHealth();
    } catch (error: any) {
      logger.warn('Failed to load service health:', error.message);
      results.service_health = { error: error.message, services: [] };
    }

    // Load settings with error handling
    try {
      results.settings = await this.apiClient.getSettings();
    } catch (error: any) {
      logger.warn('Failed to load settings:', error.message);
      results.settings = { error: error.message };
    }

    logger.info('Fallback chat initialization completed');
    return results;
  }

  /**
   * Batch multiple API requests using Promise.allSettled
   * This replaces the non-existent batch endpoints with parallel individual calls
   */
  async batchRequests(requests: BatchRequest[]): Promise<any[]> {
    logger.info(`Processing ${requests.length} requests in parallel`);

    const promises = requests.map(async (request) => {
      // Issue #156 Fix: Move destructuring outside try block so catch block can access variables
      const { endpoint, method, data } = request;

      try {
        let response;

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
        logger.warn(`Failed request ${method} ${endpoint}:`, error.message);
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
        logger.warn('System health check failed, loading minimal data');
        return {
          chat_sessions: { sessions: [] },
          health_status: healthCheck || { status: 'unknown' },
          error: 'System health check failed'
        };
      }

      // If healthy, load full chat data
      return await this.loadEssentialChatData();
    } catch (error) {
      logger.error('Failed to load chat with health checks:', error);
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