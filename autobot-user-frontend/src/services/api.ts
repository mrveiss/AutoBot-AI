// API Service Layer - TypeScript version with proper typing
import type {
  ApiResponse,
  ChatMessage,
  ChatSession,
  WorkflowApproval
} from '@/types/api'
import apiClient from '@/utils/ApiClient'
import type { RequestOptions } from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for ApiService
const logger = createLogger('ApiService')

/**
 * API Service - provides typed methods for interacting with AutoBot backend
 */
class ApiService {
  private client: typeof apiClient

  constructor() {
    this.client = apiClient
  }

  // Core HTTP methods - ApiClient already returns parsed JSON
  // FIXED: ApiClient.get/post/put/delete return parsed JSON data, NOT Response objects
  // Removed double-parsing (.json() call) that was causing "response.json is not a function" errors
  // Issue #701: Added options parameter to support params and responseType
  async get<T>(endpoint: string, options?: RequestOptions & { params?: Record<string, unknown> }): Promise<T> {
    // Handle query params if provided
    let url = endpoint
    if (options?.params) {
      const searchParams = new URLSearchParams()
      for (const [key, value] of Object.entries(options.params)) {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value))
        }
      }
      const queryString = searchParams.toString()
      if (queryString) {
        url = `${endpoint}${endpoint.includes('?') ? '&' : '?'}${queryString}`
      }
    }
    return await this.client.get(url, options) as T
  }

  async post<T>(endpoint: string, data: unknown, options?: RequestOptions & { params?: Record<string, unknown> }): Promise<T> {
    // Handle query params if provided
    let url = endpoint
    if (options?.params) {
      const searchParams = new URLSearchParams()
      for (const [key, value] of Object.entries(options.params)) {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value))
        }
      }
      const queryString = searchParams.toString()
      if (queryString) {
        url = `${endpoint}${endpoint.includes('?') ? '&' : '?'}${queryString}`
      }
    }
    return await this.client.post(url, data, options) as T
  }

  async put<T>(endpoint: string, data: unknown): Promise<T> {
    return await this.client.put(endpoint, data) as T
  }

  async delete<T>(endpoint: string): Promise<T> {
    return await this.client.delete(endpoint) as T
  }

  // Chat API - Updated to match backend specs
  async sendMessage(message: string, options: Record<string, any> = {}): Promise<ApiResponse> {
    return this.post('/api/chats/' + (options.chatId || 'default') + '/message', {
      message,
      ...options
    })
  }

  async getChatHistory(): Promise<ApiResponse<ChatMessage[]>> {
    // Issue #552: Fixed path - backend uses /api/chat/sessions
    return this.get('/api/chat/sessions')
  }

  async getChatSessions(): Promise<ApiResponse<ChatSession[]>> {
    // Issue #552: Fixed path - backend uses /api/chat/sessions
    return this.get('/api/chat/sessions')
  }

  async getChatMessages(chatId: string): Promise<ApiResponse<{ history: ChatMessage[] }>> {
    // Issue #552: Fixed path - backend uses /api/chat/sessions/{id}
    return this.get(`/api/chat/sessions/${chatId}`)
  }

  async deleteChatHistory(chatId: string): Promise<ApiResponse> {
    return this.delete(`/api/chats/${chatId}`)
  }

  // Workflow API methods - Updated to match backend specs
  async getWorkflows(): Promise<ApiResponse> {
    return this.get('/api/workflow/workflows')
  }

  async getWorkflowDetails(workflowId: string): Promise<ApiResponse> {
    return this.get(`/api/workflow/workflow/${workflowId}`)
  }

  async getWorkflowStatus(workflowId: string): Promise<ApiResponse> {
    return this.get(`/api/workflow/workflow/${workflowId}/status`)
  }

  async approveWorkflowStep(workflowId: string, approval: WorkflowApproval): Promise<ApiResponse> {
    return this.post(`/api/workflow/workflow/${workflowId}/approve`, approval)
  }

  async executeWorkflow(request: { message: string; [key: string]: any }): Promise<ApiResponse> {
    return this.post('/api/workflow/execute', request)
  }

  async cancelWorkflow(workflowId: string): Promise<ApiResponse> {
    return this.delete(`/api/workflow/workflow/${workflowId}`)
  }

  async getPendingApprovals(workflowId: string): Promise<ApiResponse> {
    return this.get(`/api/workflow/workflow/${workflowId}/pending_approvals`)
  }

  // Research Agent API methods - Updated to match backend specs
  // Issue #552: Fixed paths to match backend /api/research/comprehensive and /api/ai-stack/research/
  async performResearch(query: string, focus = 'general', maxResults = 5): Promise<ApiResponse> {
    return this.post('/api/research/comprehensive', {
      query,
      focus,
      max_results: maxResults
    })
  }

  async researchTools(query: string): Promise<ApiResponse> {
    // Use AI stack research endpoint for tool research
    return this.post('/api/ai-stack/research/web', {
      query,
      focus: 'installation_usage'
    })
  }

  async getInstallationGuide(toolName: string): Promise<ApiResponse> {
    // Use AI stack for installation guides
    return this.post('/api/ai-stack/research/comprehensive', {
      query: `installation guide for ${toolName}`,
      focus: 'installation'
    })
  }

  // Settings API - Updated to match backend specs
  async getSettings(): Promise<ApiResponse> {
    return this.get('/api/settings/')
  }

  async updateSettings(settings: Record<string, any>): Promise<ApiResponse> {
    return this.post('/api/settings/', settings)
  }

  async saveSettings(settings: Record<string, any>): Promise<ApiResponse> {
    return this.updateSettings(settings)
  }

  // System API - Updated to match backend specs
  async getSystemStatus(): Promise<ApiResponse> {
    // Issue #552: /api/system/status doesn't exist, use /api/system/info instead
    return this.get('/api/system/info')
  }

  async getSystemHealth(): Promise<ApiResponse> {
    return this.get('/api/health')
  }

  async getSystemInfo(): Promise<ApiResponse> {
    return this.get('/api/system/info')
  }

  // Terminal API - Updated to match backend specs
  // Issue #552: Fixed paths - backend uses /api/agent-terminal/*
  async executeCommand(command: string, options: Record<string, any> = {}): Promise<ApiResponse> {
    return this.post('/api/agent-terminal/execute', { command, ...options })
  }

  async interruptProcess(): Promise<ApiResponse> {
    // Issue #552: Backend uses session-based interrupt
    // Note: This may need a session_id parameter for proper implementation
    return this.post('/api/agent-terminal/execute', { interrupt: true })
  }

  async killAllProcesses(): Promise<ApiResponse> {
    // Issue #552: Backend uses session-based delete
    // Note: This may need a session_id parameter for proper implementation
    return this.post('/api/agent-terminal/execute', { kill: true })
  }

  // Knowledge Base API - Updated to match backend specs
  // Issue #552: Fixed paths to use hyphen instead of underscore
  async searchKnowledge(query: string, limit = 5): Promise<ApiResponse> {
    return this.post('/api/chat-knowledge/search', {
      query,
      n_results: limit
    })
  }

  async searchKnowledgeBase(query: string, limit = 5): Promise<ApiResponse> {
    return this.searchKnowledge(query, limit)
  }

  async addKnowledge(content: string, metadata: Record<string, any> = {}): Promise<ApiResponse> {
    // Issue #552: Fixed path - backend uses /api/chat-knowledge/knowledge/add_temporary
    return this.post('/api/chat-knowledge/knowledge/add_temporary', {
      content,
      metadata
    })
  }

  // Chat Knowledge Management - New endpoints per backend specs
  // Issue #552: Fixed paths to use hyphen instead of underscore
  async getChatKnowledgeContext(chatId: string): Promise<ApiResponse> {
    return this.get(`/api/chat-knowledge/context/${chatId}`)
  }

  async associateFileWithChat(data: {
    chat_id: string;
    file_path: string;
    association_type: string;
    metadata?: Record<string, any>;
  }): Promise<ApiResponse> {
    return this.post('/api/chat-knowledge/files/associate', data)
  }

  async getKnowledgeBaseStats(): Promise<ApiResponse> {
    return this.get('/api/knowledge_base/stats/basic')
  }

  // NOTE: The following methods are not implemented in backend and have been removed:
  // - getCategoryDocuments() - endpoint /api/knowledge_base/category/{path}/documents does not exist
  // - getDocumentContent() - endpoint /api/knowledge_base/document/content does not exist
  // Use /api/knowledge_base/search with category filters instead

  // Monitoring & Health - Updated to working endpoints with graceful fallbacks
  async getServiceHealth(): Promise<ApiResponse> {
    // FIXED: Use correct endpoint with graceful fallback
    // Old: '/api/services/health' -> New: '/api/monitoring/services/health'
    try {
      const response = await this.get<ApiResponse>('/api/monitoring/services/health');
      return response;
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      logger.warn('[ApiService] Service health check failed, using fallback:', errorMessage);
      return {
        success: false,
        error: errorMessage,
        data: {
          services: {
            backend: { status: 'warning', health: 'Status Unknown' },
            redis: { status: 'warning', health: 'Status Unknown' },
            ollama: { status: 'warning', health: 'Status Unknown' }
          }
        }
      } as ApiResponse;
    }
  }

  async getSystemMetrics(): Promise<ApiResponse> {
    // Issue #552: Fixed path - backend uses /api/service-monitor/resources
    return this.get('/api/service-monitor/resources')
  }
}

// Create and export singleton instance
export const apiService = new ApiService()
export default apiService
