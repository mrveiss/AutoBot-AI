// API Service Layer - Provides typed interface to backend services
import apiClient from '@/utils/ApiClient'

/**
 * API Service - provides methods for interacting with AutoBot backend
 */
class ApiService {
  constructor() {
    this.client = apiClient
  }

  // Core HTTP methods with JSON parsing
  async get(endpoint) {
    const response = await this.client.get(endpoint)
    return await response.json()
  }

  async post(endpoint, data) {
    const response = await this.client.post(endpoint, data)
    return await response.json()
  }

  async put(endpoint, data) {
    const response = await this.client.put(endpoint, data)
    return await response.json()
  }

  async delete(endpoint) {
    const response = await this.client.delete(endpoint)
    return await response.json()
  }

  // Chat API
  async sendMessage(message, options = {}) {
    return this.post('/api/chat', { message, ...options })
  }

  async getChatHistory() {
    return this.get('/api/history')
  }

  async getChatSessions() {
    return this.get('/api/list_sessions')
  }

  async getChatMessages(chatId) {
    return this.get(`/api/load_session/${chatId}`)
  }

  async deleteChatHistory(chatId) {
    return this.delete(`/api/chats/${chatId}`)
  }

  // Workflow API methods
  async getWorkflows() {
    return this.get('/api/workflow/workflows')
  }

  async getWorkflowDetails(workflowId) {
    return this.get(`/api/workflow/workflow/${workflowId}`)
  }

  async getWorkflowStatus(workflowId) {
    return this.get(`/api/workflow/workflow/${workflowId}/status`)
  }

  async approveWorkflowStep(workflowId, approval) {
    return this.post(`/api/workflow/workflow/${workflowId}/approve`, approval)
  }

  async executeWorkflow(request) {
    return this.post('/api/workflow/execute', request)
  }

  async cancelWorkflow(workflowId) {
    return this.delete(`/api/workflow/workflow/${workflowId}`)
  }

  async getPendingApprovals(workflowId) {
    return this.get(`/api/workflow/workflow/${workflowId}/pending_approvals`)
  }

  // Research Agent API methods
  async performResearch(query, focus = 'general', maxResults = 5) {
    return this.post('/api/research/research', {
      query,
      focus,
      max_results: maxResults
    })
  }

  async researchTools(query) {
    return this.post('/api/research/research/tools', {
      query,
      focus: 'installation_usage'
    })
  }

  async getInstallationGuide(toolName) {
    return this.get(`/api/research/installation/${toolName}`)
  }

  // Settings API
  async getSettings() {
    return this.get('/api/settings/')
  }

  async updateSettings(settings) {
    return this.post('/api/settings/', settings)
  }

  async saveSettings(settings) {
    return this.updateSettings(settings)
  }

  // System API
  async getSystemStatus() {
    return this.get('/api/system/status')
  }

  async getSystemHealth() {
    return this.get('/api/system/health')
  }

  async getSystemInfo() {
    return this.get('/api/system/info')
  }

  // Terminal API
  async executeCommand(command, options = {}) {
    return this.post('/api/terminal/execute', { command, ...options })
  }

  async interruptProcess() {
    return this.post('/api/terminal/interrupt')
  }

  async killAllProcesses() {
    return this.post('/api/terminal/kill')
  }

  // Knowledge Base API
  async searchKnowledge(query, limit = 5) {
    return this.post('/api/knowledge_base/search', {
      query,
      n_results: limit
    })
  }

  async searchKnowledgeBase(query, limit = 5) {
    return this.searchKnowledge(query, limit)
  }

  async addKnowledge(content, metadata = {}) {
    return this.post('/api/knowledge_base/add', {
      content,
      metadata
    })
  }
}

// Create and export singleton instance
export const apiService = new ApiService()
export default apiService
