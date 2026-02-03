import { vi, type Mock } from 'vitest'
import { createMockApiResponse } from '../utils/test-utils'
import { NetworkConstants } from '@/constants/network'

// Mock API client that matches the real ApiClient interface
export class MockApiClient {
  public get: Mock
  public post: Mock
  public put: Mock
  public delete: Mock
  public patch: Mock

  constructor() {
    this.get = vi.fn()
    this.post = vi.fn()
    this.put = vi.fn()
    this.delete = vi.fn()
    this.patch = vi.fn()
  }

  // Helper methods to configure mock responses
  mockGet(endpoint: string, response: any) {
    this.get.mockImplementation((url: string) => {
      if (url === endpoint) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(response),
        })
      }
      return Promise.reject(new Error(`Unexpected GET request to ${url}`))
    })
  }

  mockPost(endpoint: string, response: any) {
    this.post.mockImplementation((url: string) => {
      if (url === endpoint) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(response),
        })
      }
      return Promise.reject(new Error(`Unexpected POST request to ${url}`))
    })
  }

  mockError(method: 'get' | 'post' | 'put' | 'delete' | 'patch', endpoint: string, status = 500) {
    this[method].mockImplementation((url: string) => {
      if (url === endpoint) {
        return Promise.reject(new Error(`HTTP ${status}`))
      }
      return Promise.reject(new Error(`Unexpected ${method.toUpperCase()} request to ${url}`))
    })
  }

  // Reset all mocks
  reset() {
    this.get.mockReset()
    this.post.mockReset()
    this.put.mockReset()
    this.delete.mockReset()
    this.patch.mockReset()
  }

  // Setup default successful responses
  setupDefaults() {
    // Chat endpoints
    // Issue #552: Fixed paths to match backend endpoints
    this.mockPost('/api/chat', createMockApiResponse({
      message: { content: 'Mock response', sender: 'assistant' },
      chatId: 'mock-chat-id',
    }))

    this.mockGet('/api/chat/sessions', createMockApiResponse({
      sessions: [
        { chatId: 'chat-1', name: 'Test Chat 1', messages: [] },
        { chatId: 'chat-2', name: 'Test Chat 2', messages: [] },
      ],
    }))

    // System endpoints
    this.mockGet('/api/system/health', createMockApiResponse({
      status: 'healthy',
      version: '1.0.0',
    }))

    // Settings endpoints
    this.mockGet('/api/settings', createMockApiResponse({
      settings: {
        chat: { auto_scroll: true, max_messages: 100 },
        backend: { host: NetworkConstants.LOCALHOST_NAME, port: NetworkConstants.BACKEND_PORT },
      },
    }))

    // Workflow endpoints
    this.mockGet('/api/workflow/workflows', createMockApiResponse({
      workflows: [
        { id: 'workflow-1', name: 'Test Workflow', status: 'running' },
      ],
    }))
  }
}

// Factory function to create mock API service
export const createMockApiService = () => {
  const mockClient = new MockApiClient()
  mockClient.setupDefaults()

  return {
    client: mockClient,
    
    // Core HTTP methods
    async get(endpoint: string) {
      const response = await mockClient.get(endpoint)
      return await response.json()
    },

    async post(endpoint: string, data?: any) {
      const response = await mockClient.post(endpoint, data)
      return await response.json()
    },

    async put(endpoint: string, data?: any) {
      const response = await mockClient.put(endpoint, data)
      return await response.json()
    },

    async delete(endpoint: string) {
      const response = await mockClient.delete(endpoint)
      return await response.json()
    },

    // Chat API methods
    async sendMessage(message: string, options = {}) {
      return this.post('/api/chat', { message, ...options })
    },

    // Workflow API methods
    async getWorkflows() {
      return this.get('/api/workflow/workflows')
    },

    async getWorkflowDetails(workflowId: string) {
      return this.get(`/api/workflow/workflow/${workflowId}`)
    },

    async getWorkflowStatus(workflowId: string) {
      return this.get(`/api/workflow/workflow/${workflowId}/status`)
    },

    async approveWorkflowStep(workflowId: string, stepId: string) {
      return this.post(`/api/workflow/workflow/${workflowId}/approve`, { stepId })
    },

    async cancelWorkflow(workflowId: string) {
      return this.delete(`/api/workflow/workflow/${workflowId}`)
    },

    // Settings API methods
    async getSettings() {
      return this.get('/api/settings')
    },

    async saveSettings(settings: any) {
      return this.post('/api/settings', settings)
    },

    // System API methods
    async getSystemHealth() {
      return this.get('/api/system/health')
    },

    async getSystemInfo() {
      return this.get('/api/system/info')
    },

    // Terminal API methods
    // Issue #552: Fixed paths to use /api/agent-terminal/*
    async executeCommand(command: string, options = {}) {
      return this.post('/api/agent-terminal/execute', { command, ...options })
    },

    async interruptProcess() {
      return this.post('/api/agent-terminal/execute', { interrupt: true })
    },

    async killAllProcesses() {
      return this.post('/api/agent-terminal/execute', { kill: true })
    },

    // Chat history methods
    // Issue #552: Fixed paths to use /api/chat/sessions
    async getChatHistory() {
      return this.get('/api/chat/sessions')
    },

    async getChatMessages(chatId: string) {
      return this.get(`/api/chat/sessions/${chatId}`)
    },

    async deleteChatHistory(chatId: string) {
      return this.delete(`/api/chat/sessions/${chatId}`)
    },

    // Knowledge base methods
    async searchKnowledgeBase(query: string, limit = 10) {
      return this.post('/api/knowledge_base/search', { query, limit })
    },
  }
}