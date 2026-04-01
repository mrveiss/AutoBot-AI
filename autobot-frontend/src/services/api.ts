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

class ApiService {
  private client: typeof apiClient

  constructor() {
    this.client = apiClient
  }

  // Core HTTP methods - ApiClient already returns parsed JSON
  async get<T>(endpoint: string, options?: RequestOptions & { params?: Record<string, unknown> }): Promise<T> {
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

  // Chat API
  async sendMessage(message: string, options: Record<string, unknown> = {}): Promise<ApiResponse> {
    return this.post('/api/chats/' + (options.chatId || 'default') + '/message', {
      message,
      ...options
    })
  }

  async getChatHistory(): Promise<ApiResponse<ChatMessage[]>> {
    return this.get('/api/chat/sessions')
  }

  async getChatSessions(): Promise<ApiResponse<ChatSession[]>> {
    return this.get('/api/chat/sessions')
  }

  async getChatMessages(chatId: string): Promise<ApiResponse<{ history: ChatMessage[] }>> {
    return this.get(`/api/chat/sessions/${chatId}`)
  }

  async deleteChatHistory(chatId: string): Promise<ApiResponse> {
    return this.delete(`/api/chats/${chatId}`)
  }

  // Workflow API
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

  async executeWorkflow(request: { message: string; [key: string]: unknown }): Promise<ApiResponse> {
    return this.post('/api/workflow/execute', request)
  }

  async cancelWorkflow(workflowId: string): Promise<ApiResponse> {
    return this.delete(`/api/workflow/workflow/${workflowId}`)
  }

  async getPendingApprovals(workflowId: string): Promise<ApiResponse> {
    return this.get(`/api/workflow/workflow/${workflowId}/pending_approvals`)
  }

  // Research Agent API
  async performResearch(query: string, focus = 'general', maxResults = 5): Promise<ApiResponse> {
    return this.post('/api/research/comprehensive', {
      query,
      focus,
      max_results: maxResults
    })
  }

  async researchTools(query: string): Promise<ApiResponse> {
    return this.post('/api/ai-stack/research/web', {
      query,
      focus: 'installation_usage'
    })
  }

  async getInstallationGuide(toolName: string): Promise<ApiResponse> {
    return this.post('/api/ai-stack/research/comprehensive', {
      query: `installation guide for ${toolName}`,
      focus: 'installation'
    })
  }

  // Settings API
  async getSettings(): Promise<ApiResponse> {
    return this.get('/api/settings/')
  }

  async updateSettings(settings: Record<string, unknown>): Promise<ApiResponse> {
    return this.post('/api/settings/', settings)
  }

  async saveSettings(settings: Record<string, unknown>): Promise<ApiResponse> {
    return this.updateSettings(settings)
  }

  // System API
  async getSystemStatus(): Promise<ApiResponse> {
    return this.get('/api/system/info')
  }

  async getSystemHealth(): Promise<ApiResponse> {
    return this.get('/api/health')
  }

  async getSystemInfo(): Promise<ApiResponse> {
    return this.get('/api/system/info')
  }

  // Terminal API
  async executeCommand(command: string, options: Record<string, unknown> = {}): Promise<ApiResponse> {
    return this.post('/api/agent-terminal/execute', { command, ...options })
  }

  async interruptProcess(): Promise<ApiResponse> {
    return this.post('/api/agent-terminal/execute', { interrupt: true })
  }

  async killAllProcesses(): Promise<ApiResponse> {
    return this.post('/api/agent-terminal/execute', { kill: true })
  }

  // Knowledge Base API
  async searchKnowledge(query: string, limit = 5): Promise<ApiResponse> {
    return this.post('/api/chat-knowledge/search', {
      query,
      n_results: limit
    })
  }

  async searchKnowledgeBase(query: string, limit = 5): Promise<ApiResponse> {
    return this.searchKnowledge(query, limit)
  }

  async addKnowledge(content: string, metadata: Record<string, unknown> = {}): Promise<ApiResponse> {
    return this.post('/api/chat-knowledge/knowledge/add_temporary', {
      content,
      metadata
    })
  }

  async getChatKnowledgeContext(chatId: string): Promise<ApiResponse> {
    return this.get(`/api/chat-knowledge/context/${chatId}`)
  }

  async associateFileWithChat(data: {
    chat_id: string;
    file_path: string;
    association_type: string;
    metadata?: Record<string, unknown>;
  }): Promise<ApiResponse> {
    return this.post('/api/chat-knowledge/files/associate', data)
  }

  async getKnowledgeBaseStats(): Promise<ApiResponse> {
    return this.get('/api/knowledge_base/stats/basic')
  }

  // Monitoring & Health
  async getServiceHealth(): Promise<ApiResponse> {
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
    return this.get('/api/service-monitor/resources')
  }
}

export const apiService = new ApiService()
export default apiService
