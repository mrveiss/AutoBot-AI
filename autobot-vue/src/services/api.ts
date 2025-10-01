// API Service Layer - TypeScript version with proper typing
import type { 
  ApiResponse, 
  ChatMessage, 
  ChatSession, 
  WorkflowApproval 
} from '@/types/api'
import apiClient from '@/utils/ApiClient'
import apiEndpointMapper from '@/utils/ApiEndpointMapper.js'

/**
 * API Service - provides typed methods for interacting with AutoBot backend
 */
class ApiService {
  private client: typeof apiClient

  constructor() {
    this.client = apiClient
  }

  // Core HTTP methods with JSON parsing
  async get<T = any>(endpoint: string): Promise<T> {
    const response = await this.client.get(endpoint)
    return await response.json()
  }

  async post<T = any>(endpoint: string, data?: any): Promise<T> {
    const response = await this.client.post(endpoint, data)
    return await response.json()
  }

  async put<T = any>(endpoint: string, data?: any): Promise<T> {
    const response = await this.client.put(endpoint, data)
    return await response.json()
  }

  async delete<T = any>(endpoint: string): Promise<T> {
    const response = await this.client.delete(endpoint)
    return await response.json()
  }

  // Chat API - Updated to match backend specs
  async sendMessage(message: string, options: Record<string, any> = {}): Promise<ApiResponse> {
    return this.post('/api/chats/' + (options.chatId || 'default') + '/message', {
      message,
      ...options
    })
  }

  async getChatHistory(): Promise<ApiResponse<ChatMessage[]>> {
    return this.get('/api/history')
  }

  async getChatSessions(): Promise<ApiResponse<ChatSession[]>> {
    return this.get('/api/list_sessions')
  }

  async getChatMessages(chatId: string): Promise<ApiResponse<{ history: ChatMessage[] }>> {
    return this.get(`/api/load_session/${chatId}`)
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
  async performResearch(query: string, focus = 'general', maxResults = 5): Promise<ApiResponse> {
    return this.post('/api/research/research', {
      query,
      focus,
      max_results: maxResults
    })
  }

  async researchTools(query: string): Promise<ApiResponse> {
    return this.post('/api/research/research/tools', {
      query,
      focus: 'installation_usage'
    })
  }

  async getInstallationGuide(toolName: string): Promise<ApiResponse> {
    return this.get(`/api/research/installation/${toolName}`)
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
    return this.get('/api/system/status')
  }

  async getSystemHealth(): Promise<ApiResponse> {
    return this.get('/api/system/health')
  }

  async getSystemInfo(): Promise<ApiResponse> {
    return this.get('/api/system/info')
  }

  // Terminal API - Updated to match backend specs
  async executeCommand(command: string, options: Record<string, any> = {}): Promise<ApiResponse> {
    return this.post('/api/terminal/execute', { command, ...options })
  }

  async interruptProcess(): Promise<ApiResponse> {
    return this.post('/api/terminal/interrupt')
  }

  async killAllProcesses(): Promise<ApiResponse> {
    return this.post('/api/terminal/kill')
  }

  // Knowledge Base API - Updated to match backend specs
  async searchKnowledge(query: string, limit = 5): Promise<ApiResponse> {
    return this.post('/api/chat_knowledge/search', {
      query,
      n_results: limit
    })
  }

  async searchKnowledgeBase(query: string, limit = 5): Promise<ApiResponse> {
    return this.searchKnowledge(query, limit)
  }

  async addKnowledge(content: string, metadata: Record<string, any> = {}): Promise<ApiResponse> {
    return this.post('/api/chat_knowledge/add', {
      content,
      metadata
    })
  }

  // Chat Knowledge Management - New endpoints per backend specs
  async getChatKnowledgeContext(chatId: string): Promise<ApiResponse> {
    return this.get(`/api/chat_knowledge/context/${chatId}`)
  }

  async associateFileWithChat(data: {
    chat_id: string;
    file_path: string;
    association_type: string;
    metadata?: Record<string, any>;
  }): Promise<ApiResponse> {
    return this.post('/api/chat_knowledge/files/associate', data)
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
      const response = await apiEndpointMapper.fetchWithFallback('/api/services/health', { timeout: 10000 });
      return await response.json();
    } catch (error) {
      console.warn('[ApiService] Service health check failed, using fallback:', error);
      return {
        success: false,
        error: error.message,
        fallback: true,
        data: {
          services: {
            backend: { status: 'warning', health: 'Status Unknown' },
            redis: { status: 'warning', health: 'Status Unknown' },
            ollama: { status: 'warning', health: 'Status Unknown' }
          }
        }
      };
    }
  }

  async getSystemMetrics(): Promise<ApiResponse> {
    return this.get('/api/resources')
  }
}

// Create and export singleton instance
export const apiService = new ApiService()
export default apiService