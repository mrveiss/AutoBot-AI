// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Batch API Service - Optimized service for batching multiple API calls
 * Updated to use correct ApiClient singleton with proper error handling
 *
 * #16465: fallbackChatInitialization() used to also fetch ApiClient.getSettings()
 * (the global admin config endpoint, admin-gated since #16240) on every chat load
 * for every user -- but its result was never read anywhere by the only real
 * caller (ChatInterface.vue's initializeChatInterface), so it was fetched only to
 * be discarded, and always failed for non-admins post-#16240. Removed rather than
 * routed elsewhere: nothing consumed it, so there was no capability to preserve.
 * loadChatInitData() (a separate, unrelated method with the same admin-gated
 * call) was removed outright -- zero real callers, only its own test's mock.
 *
 * #18765: GETs no longer fan out as N browser requests. They go to ONE server call,
 * POST /api/batch-jobs/load, which dispatches each through the ASGI app with the
 * caller's own credentials, so every target route's own auth gate runs and its own
 * status lands in that item's slot. Only the server's allow-list of read-only GETs
 * is batchable; mutating methods keep going through the ApiClient one by one.
 */

import apiClient from '@/utils/ApiClient';
import type { ApiClient } from '@/utils/ApiClient';
import { createLogger } from '@/utils/debugUtils';
import { extractErrorMessage } from '@/utils/errorExtract';
import { getApiBase } from '@/config/ssot-config';
import type { operations } from '@/types/generated/api';

// Request/response shape of POST /api/batch-jobs/load, derived from the generated OpenAPI types.
type BatchLoadOp = operations['batch_load_api_batch_jobs_load_post'];
type BatchLoadRequest = BatchLoadOp['requestBody']['content']['application/json'];
type BatchLoadResponse = BatchLoadOp['responses'][200]['content']['application/json'];
// One result slot, in request order (api/batch_dispatch.py). The generated type carries the list
// as `unknown`, so the slot is named here.
interface BatchLoadItem {
  endpoint: string | null;
  method: string;
  status: number;
  body: unknown;
  error: string | null;
  timing: number;
  /** The loader would not dispatch this path (not allow-listed); the caller runs it directly. */
  refused?: boolean;
}

// Create scoped logger for BatchApiService
const logger = createLogger('BatchApiService');

// Type definitions
interface ApiResponse<T = unknown> {
  // data is null when the API call failed (distinguishes from data:[] which means
  // the backend returned 0 items successfully). See issue #4353.
  data?: T | null;
  error?: string;
  // Issue #4352: intentional_empty signals the backend confirmed 0 sessions
  // (vs. an API failure that returns empty data). Frontend uses this to decide
  // whether to clear local sessions or preserve them as a defensive fallback.
  intentional_empty?: boolean;
}

interface FallbackResults {
  chat_sessions: ApiResponse<Record<string, unknown>[]>;
  system_health: ApiResponse<Record<string, unknown>>;
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

  private extractSessionsList(response: unknown): unknown[] | null {
    if (Array.isArray(response)) return response;
    const r = response as Record<string, unknown> | null;
    const data = r?.data as Record<string, unknown> | undefined;
    // Prefer explicit sessions key; fall through to data object only if it is an array
    const sessions = data?.sessions ?? r?.sessions;
    if (sessions !== undefined) return sessions as unknown[];
    if (Array.isArray(data)) return data;
    // Response has no recognisable session structure — signal parse failure
    return null;
  }

  /** Issue #4352: Extract intentional_empty flag from backend chat-sessions response. */
  private extractIntentionalEmpty(response: unknown): boolean {
    if (!response || typeof response !== 'object') return false;
    const r = response as Record<string, unknown>;
    // Backend returns: { sessions, count, intentional_empty } (no extra .data wrapper)
    const data = r.data as Record<string, unknown> | undefined;
    return Boolean(data?.intentional_empty ?? r.intentional_empty);
  }

  /** Issue #4353: Build chat_sessions ApiResponse, distinguishing API errors from
   *  valid empty-session lists. Returns { error } when the API call failed or the
   *  response has no recognisable sessions structure; returns { data, intentional_empty }
   *  when the backend positively confirmed the sessions list (including empty). */
  private buildChatSessionsResult(
    result: PromiseSettledResult<Record<string, unknown>>
  ): ApiResponse<Record<string, unknown>[]> {
    if (result.status === 'rejected') {
      const reason = (result as PromiseRejectedResult).reason;
      return { data: null, error: reason?.message || 'api_failed' };
    }

    const sessions = this.extractSessionsList(result.value);
    if (sessions === null) {
      // Fulfilled but response structure unrecognisable — treat as silent API failure
      logger.warn('getChatList response has no sessions structure; treating as api_failed');
      return { data: null, error: 'api_failed' };
    }

    return {
      data: sessions as Record<string, unknown>[],
      intentional_empty: this.extractIntentionalEmpty(result.value),
    };
  }

  /** Re-express a batch slot as the settled-promise shape the result builders consume. */
  private toSettled(result: BatchResult): PromiseSettledResult<Record<string, unknown>> {
    return result.success
      ? { status: 'fulfilled', value: result.data as Record<string, unknown> }
      : { status: 'rejected', reason: new Error(result.error || 'api_failed') };
  }

  async fallbackChatInitialization(): Promise<FallbackResults> {
    logger.info('Using parallel chat initialization with individual API calls');

    const base = getApiBase();
    const [chatSessionsBatch, systemHealthBatch] = await this.batchRequests([
      { endpoint: `${base}/chat/sessions`, method: 'GET' },
      { endpoint: `${base}/system/health`, method: 'GET' }
    ]);
    const chatSessionsResult = this.toSettled(chatSessionsBatch);
    const systemHealthResult = this.toSettled(systemHealthBatch);

    const chatSessionsApiResult = this.buildChatSessionsResult(chatSessionsResult);

    const results: FallbackResults = {
      chat_sessions: chatSessionsApiResult,

      system_health: systemHealthResult.status === 'fulfilled'
        ? { data: systemHealthResult.value as Record<string, unknown> }
        : { error: (systemHealthResult as PromiseRejectedResult).reason?.message || 'Failed to load' }
    };

    // BUG4/BUG5: these are returned as `error` fields above and surfaced by the
    // caller (ChatInterface) — keep them at debug so the same failure isn't
    // double-logged at WARN from multiple layers.
    if (chatSessionsResult.status === 'rejected') {
      logger.debug('Chat sessions unavailable:', (chatSessionsResult as PromiseRejectedResult).reason?.message);
    }
    if (systemHealthResult.status === 'rejected') {
      logger.debug('System health unavailable:', (systemHealthResult as PromiseRejectedResult).reason?.message);
    }

    logger.info('Parallel chat initialization completed');
    return results;
  }

  /** One server call for all GETs (#18765); mutating methods go through the ApiClient one by one. */
  async batchRequests(requests: BatchRequest[]): Promise<BatchResult[]> {
    logger.info(`Processing ${requests.length} requests in parallel`);

    const getIdx = requests.map((r, i) => (r.method.toUpperCase() === 'GET' ? i : -1)).filter(i => i >= 0);
    const results: BatchResult[] = [];

    const [batched] = await Promise.all([
      this.loadGetsViaServer(getIdx.map(i => requests[i])),
      ...requests.map(async (request, i) => {
        if (request.method.toUpperCase() !== 'GET') results[i] = await this.runDirect(request);
      })
    ]);
    // A slot the loader refused (not allow-listed) is fetched directly, as before #18765.
    await Promise.all(getIdx.map(async (reqIdx, n) => {
      results[reqIdx] = batched[n] ?? await this.runDirect(requests[reqIdx]);
    }));
    return results;
  }

  /**
   * The server allow-list matches its own `/api/...` paths, so a configured client base
   * (VITE_API_BASE_PATH, e.g. a proxy prefix or an absolute URL) is swapped back for `/api`.
   * `request.endpoint` itself stays as the caller wrote it, since callers look results up by it.
   */
  private toServerPath(endpoint: string): string {
    const base = getApiBase();
    return base !== '/api' && endpoint.startsWith(`${base}/`) ? `/api${endpoint.slice(base.length)}` : endpoint;
  }

  /** One result per GET, or null for a slot the loader refused to dispatch. */
  private async loadGetsViaServer(requests: BatchRequest[]): Promise<(BatchResult | null)[]> {
    if (requests.length === 0) return [];
    const payload: BatchLoadRequest = {
      requests: requests.map(r => ({ endpoint: this.toServerPath(r.endpoint), method: 'GET' }))
    };
    try {
      // Typed from the generated contract (BatchLoadOp), not an inline call-site generic.
      const response = (await this.apiClient.post(`${getApiBase()}/batch-jobs/load`, payload)) as BatchLoadResponse;
      const items = (response.results ?? []) as BatchLoadItem[];
      return requests.map((r, n) => (items[n]?.refused ? null : this.toBatchResult(r, items[n])));
    } catch (error: unknown) {
      const message = extractErrorMessage(error, 'Unknown error');
      logger.warn('Batch load failed:', message);
      return requests.map(r => ({ endpoint: r.endpoint, method: r.method, success: false, error: message }));
    }
  }

  private toBatchResult(request: BatchRequest, item: BatchLoadItem | undefined): BatchResult {
    const ok = item !== undefined && item.status < 400;
    if (!ok) logger.warn(`Failed request ${request.method} ${request.endpoint}:`, item?.error ?? 'no result');
    return {
      endpoint: request.endpoint,
      method: request.method,
      success: ok,
      ...(ok ? { data: item.body } : { error: item?.error ?? 'api_failed' })
    };
  }

  private async runDirect(request: BatchRequest): Promise<BatchResult> {
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
      return { endpoint, method, success: true, data: response };
    } catch (error: unknown) {
      logger.warn(`Failed request ${method} ${endpoint}:`, extractErrorMessage(error, 'Unknown error'));
      return { endpoint, method, success: false, error: extractErrorMessage(error, 'Unknown error') };
    }
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
      { endpoint: `${getApiBase()}/chats`, method: 'GET', priority: 3 },
      { endpoint: `${getApiBase()}/chat/health`, method: 'GET', priority: 2 },
      { endpoint: `${getApiBase()}/health`, method: 'GET', priority: 1 }
    ];

    const results = await this.batchRequests(essentialRequests);

    // Issue #4537: use explicit success/failure checks per the null-vs-empty contract
    // established in #4353. The || operator treated null (API error) the same as missing
    // data, silently firing the fallback instead of surfacing the error.
    const chatsResult = results.find(r => r.endpoint === `${getApiBase()}/chats`);
    const chatHealthResult = results.find(r => r.endpoint === `${getApiBase()}/chat/health`);
    const systemHealthResult = results.find(r => r.endpoint === `${getApiBase()}/health`);

    const chatSessions: ApiResponse<Record<string, unknown>[]> = chatsResult?.success
      ? { data: this.extractSessionsList(chatsResult.data) as Record<string, unknown>[] }
      : { data: null, error: chatsResult?.error ?? 'api_failed' };

    if (!chatsResult?.success) {
      logger.warn('loadEssentialChatData: /chats request failed:', chatsResult?.error);
    }

    return {
      chat_sessions: chatSessions,
      chat_health: chatHealthResult?.success
        ? { data: chatHealthResult.data }
        : { data: null, error: chatHealthResult?.error ?? 'api_failed' },
      system_health: systemHealthResult?.success
        ? { data: systemHealthResult.data }
        : { data: null, error: systemHealthResult?.error ?? 'api_failed' }
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
