// API Service Layer - TypeScript version with proper typing
import type {
  ApiResponse,
  ChatMessage,
  ChatSession,
  WorkflowApproval
} from '@/types/api'
import type { UserResponse, TeamResponse } from '@/types/api-contract'
import apiClient from '@/utils/ApiClient'
import type { RequestOptions } from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

// Create scoped logger for ApiService
const logger = createLogger('ApiService')

// Session collaboration response types
export interface ParticipantResponse {
  user_id: string
  permission: string
  is_owner: boolean
  online?: boolean
}

export interface SessionParticipantsResponse {
  session_id: string
  owner_id: string
  participants: ParticipantResponse[]
  total_count: number
}

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
    return this.post(`${getApiBase()}/chats/` + (options.chatId || 'default') + '/message', {
      message,
      ...options
    })
  }

  async getChatHistory(): Promise<ApiResponse<ChatMessage[]>> {
    return this.get(`${getApiBase()}/chat/sessions`)
  }

  async getChatSessions(): Promise<ApiResponse<ChatSession[]>> {
    return this.get(`${getApiBase()}/chat/sessions`)
  }

  async getChatMessages(chatId: string): Promise<ApiResponse<{ history: ChatMessage[] }>> {
    return this.get(`${getApiBase()}/chat/sessions/${chatId}`)
  }

  async deleteChatHistory(chatId: string): Promise<ApiResponse> {
    return this.delete(`${getApiBase()}/chats/${chatId}`)
  }

  // Session Collaboration API (Issue #3986)
  async getSessionParticipants(sessionId: string): Promise<SessionParticipantsResponse> {
    return this.get<SessionParticipantsResponse>(`${getApiBase()}/sessions/${sessionId}/participants`)
  }

  // Workflow API
  async getWorkflows(): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/workflow/workflows`)
  }

  async getWorkflowDetails(workflowId: string): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/workflow/workflow/${workflowId}`)
  }

  async getWorkflowStatus(workflowId: string): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/workflow/workflow/${workflowId}/status`)
  }

  async approveWorkflowStep(workflowId: string, approval: WorkflowApproval): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/workflow/workflow/${workflowId}/approve`, approval)
  }

  async executeWorkflow(request: { message: string; [key: string]: unknown }): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/workflow/execute`, request)
  }

  async cancelWorkflow(workflowId: string): Promise<ApiResponse> {
    return this.delete(`${getApiBase()}/workflow/workflow/${workflowId}`)
  }

  async getPendingApprovals(workflowId: string): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/workflow/workflow/${workflowId}/pending_approvals`)
  }

  // Research Agent API
  async performResearch(query: string, focus = 'general', maxResults = 5): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/research/comprehensive`, {
      query,
      focus,
      max_results: maxResults
    })
  }

  async researchTools(query: string): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/ai-stack/research/web`, {
      query,
      focus: 'installation_usage'
    })
  }

  async getInstallationGuide(toolName: string): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/ai-stack/research/comprehensive`, {
      query: `installation guide for ${toolName}`,
      focus: 'installation'
    })
  }

  // Settings API
  async getSettings(): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/settings/`)
  }

  async updateSettings(settings: Record<string, unknown>): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/settings/`, settings)
  }

  async saveSettings(settings: Record<string, unknown>): Promise<ApiResponse> {
    return this.updateSettings(settings)
  }

  // System API
  async getSystemStatus(): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/system/info`)
  }

  async getSystemHealth(): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/health`)
  }

  async getSystemInfo(): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/system/info`)
  }

  // Terminal API
  async executeCommand(command: string, options: Record<string, unknown> = {}): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/agent-terminal/execute`, { command, ...options })
  }

  async interruptProcess(): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/agent-terminal/execute`, { interrupt: true })
  }

  async killAllProcesses(): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/agent-terminal/execute`, { kill: true })
  }

  // Knowledge Base API
  async searchKnowledge(query: string, limit = 5): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/chat-knowledge/search`, {
      query,
      n_results: limit
    })
  }

  async searchKnowledgeBase(query: string, limit = 5): Promise<ApiResponse> {
    return this.searchKnowledge(query, limit)
  }

  async addKnowledge(content: string, metadata: Record<string, unknown> = {}): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/chat-knowledge/knowledge/add_temporary`, {
      content,
      metadata
    })
  }

  async getChatKnowledgeContext(chatId: string): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/chat-knowledge/context/${chatId}`)
  }

  async associateFileWithChat(data: {
    chat_id: string;
    file_path: string;
    association_type: string;
    metadata?: Record<string, unknown>;
  }): Promise<ApiResponse> {
    return this.post(`${getApiBase()}/chat-knowledge/files/associate`, data)
  }

  async getKnowledgeBaseStats(): Promise<ApiResponse> {
    return this.get(`${getApiBase()}/knowledge_base/stats/basic`)
  }

  // Monitoring & Health
  async getServiceHealth(): Promise<ApiResponse> {
    try {
      const response = await this.get<ApiResponse>(`${getApiBase()}/monitoring/services/health`);
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
    return this.get(`${getApiBase()}/service-monitor/resources`)
  }

  // User Management API
  async getUserById(userId: string): Promise<UserResponse> {
    return this.get(`${getApiBase()}/user-management/users/${userId}`)
  }

  async getGroupById(groupId: string): Promise<TeamResponse> {
    return this.get(`${getApiBase()}/user-management/teams/${groupId}`)
  }
}

export const apiService = new ApiService()
export default apiService
