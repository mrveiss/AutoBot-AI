/**
 * Batch API Service - Optimized service for batching multiple API calls
 * Updated to use correct ApiClient singleton with proper error handling
 */

import apiClient from '@/utils/ApiClient';
import type { ApiClient } from '@/utils/ApiClient';
import { createLogger } from '@/utils/debugUtils';
import { extractErrorMessage } from '@/utils/errorExtract';

// Create scoped logger for BatchApiService
const logger = createLogger('BatchApiService');

// Type definitions
interface ChatMessage {
  id: string;
  content: string;
  sender: string;
  timestamp: string;
}

interface ChatInitData {
  messages: ChatMessage[];
  session_info: Record<string, unknown>;
  user_preferences: Record<string, unknown>;
}

interface FallbackResults {
  chat_sessions: Record<string, unknown> | Record<string, unknown>[];
  system_health: Record<string, unknown>;
  settings: Record<string, unknown>;
}

interface BatchRequest {
  endpoint: string;
  method: string;
  data?: unknown;
  priority?: number;
}

interface BatchResult {
  endpoint: string;
  method: string;
  success: boolean;
  data?: unknown;
  error?: string;
}

export class BatchApiService {
  private apiClient: ApiClient;
  private requestQueue: BatchRequest[] = [];
  private processing = false;

  constructor(client?: ApiClient) {
    // Use provided client or the singleton instance
    this.apiClient = client || apiClient;
  }

  async initializeChatInterface(): Promise<FallbackResults> {
    logger.debug('Using individual API calls for chat initialization');
    return await this.fallbackChatInitialization();
  }

  async loadChatInitData(sessionId: string): Promise<ChatInitData> {
    logger.debug('Loading chat init data for session:', sessionId);

    try {
      const messages = await this.apiClient.getChatMessages(sessionId);

      const session_info = { id: sessionId };

      let user_preferences: Record<string, unknown> = {};
      try {
        const settings = await this.apiClient.getSettings();
        user_preferences = (settings as Record<string, unknown>).user_preferences as Record<string, unknown> || {};
      } catch (error) {
        logger.warn('Could not load user preferences:', error);
      }

      return {
        messages: (messages as Record<string, unknown>).messages as ChatMessage[] || [],
        session_info,
        user_preferences
      };
    } catch (error) {
      logger.error('Failed to load chat init data:', error);
      return {
        messages: [],
        session_info: { id: sessionId },
        user_preferences: {}
      };
    }
  }

  private extractSessionsList(response: unknown): unknown[] {
    if (Array.isArray(response)) return response;
    const r = response as Record<string, unknown> | null;
    const data = r?.data as Record<string, unknown> | undefined;
    return (data?.sessions || data || (r as Record<string, unknown>)?.sessions || []) as unknown[];
  }

  async fallbackChatInitialization(): Promise<FallbackResults> {
    logger.info('Using parallel chat initialization with individual API calls');

    const [
      chatSessionsResult,
      systemHealthResult,
      settingsResult
    ] = await Promise.allSettled([
      this.apiClient.getChatList(),
      this.apiClient.getSystemHealth(),
      this.apiClient.getSettings()
    ]);

    const results: FallbackResults = {
      chat_sessions: chatSessionsResult.status === 'fulfilled'
        ? this.extractSessionsList(chatSessionsResult.value)
        : { error: (chatSessionsResult as PromiseRejectedResult).reason?.message || 'Failed to load', sessions: [] },

      system_health: systemHealthResult.status === 'fulfilled'
        ? systemHealthResult.value as Record<string, unknown>
        : { error: (systemHealthResult as PromiseRejectedResult).reason?.message || 'Failed to load', status: 'unknown' },

      settings: settingsResult.status === 'fulfilled'
        ? settingsResult.value as Record<string, unknown>
        : { error: (settingsResult as PromiseRejectedResult).reason?.message || 'Failed to load' }
    };

    if (chatSessionsResult.status === 'rejected') {
      logger.warn('Failed to load chat sessions:', (chatSessionsResult as PromiseRejectedResult).reason?.message);
    }
    if (systemHealthResult.status === 'rejected') {
      logger.warn('Failed to load system health:', (systemHealthResult as PromiseRejectedResult).reason?.message);
    }
    if (settingsResult.status === 'rejected') {
      logger.warn('Failed to load settings:', (settingsResult as PromiseRejectedResult).reason?.message);
    }

    logger.info('Parallel chat initialization completed');
    return results;
  }

  async batchRequests(requests: BatchRequest[]): Promise<BatchResult[]> {
    logger.info(`Processing ${requests.length} requests in parallel`);

    const promises = requests.map(async (request): Promise<BatchResult> => {
      const { endpoint, method, data } = request;

      try {
        let response: unknown;

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
      } catch (error: unknown) {
        logger.warn(`Failed request ${method} ${endpoint}:`, extractErrorMessage(error, 'Unknown error'));
        return {
          endpoint,
          method,
          success: false,
          error: extractErrorMessage(error, 'Unknown error')
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

  queueRequest(endpoint: string, method: string, data?: unknown, priority: number = 0): void {
    this.requestQueue.push({ endpoint, method, data, priority });

    this.requestQueue.sort((a, b) => (b.priority || 0) - (a.priority || 0));
  }

  async processQueue(): Promise<BatchResult[]> {
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

  clearQueue(): void {
    this.requestQueue = [];
  }

  getQueueStatus(): { length: number; processing: boolean } {
    return {
      length: this.requestQueue.length,
      processing: this.processing
    };
  }

  async loadEssentialChatData(): Promise<Record<string, unknown>> {
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

  async loadChatWithHealthChecks(): Promise<Record<string, unknown>> {
    try {
      const healthCheck = await this.apiClient.checkHealth();

      const isHealthy = healthCheck === true;

      if (!isHealthy) {
        logger.warn('System health check failed, loading minimal data');
        return {
          chat_sessions: { sessions: [] },
          health_status: { status: 'unknown' },
          error: 'System health check failed'
        };
      }

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
