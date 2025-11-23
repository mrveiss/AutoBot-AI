import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { apiService } from '../api.js'
// Issue #156 Fix: Corrected Python-style import to TypeScript syntax
import { NetworkConstants, ServiceURLs } from '@/constants/network'
import {
  createMockApiResponse,
  createMockChatMessage,
  createMockChatSession,
  createMockWorkflow,
  createMockSettings,
} from '../../test/utils/test-utils'

// Setup MSW server for integration tests
const server = setupServer()

const API_BASE = ServiceURLs.BACKEND_LOCAL

describe('API Service Integration Tests', () => {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: 'warn' })
  })

  afterAll(() => {
    server.close()
  })

  beforeEach(() => {
    server.resetHandlers()
  })

  describe('Chat API Integration', () => {
    it('sends message and receives response', async () => {
      const mockResponse = createMockApiResponse({
        message: createMockChatMessage({
          content: 'Test response from API',
          sender: 'assistant',
        }),
        chatId: 'test-chat-123',
      })

      server.use(
        http.post(`${API_BASE}/api/chat`, () => {
          return HttpResponse.json(mockResponse)
        })
      )

      const result = await apiService.sendMessage('Hello, test message!')

      expect(result.success).toBe(true)
      expect(result.data.message.content).toBe('Test response from API')
      expect(result.data.message.sender).toBe('assistant')
    })

    it('handles chat API errors gracefully', async () => {
      server.use(
        http.post(`${API_BASE}/api/chat`, () => {
          return new HttpResponse(null, { status: 500 })
        })
      )

      await expect(apiService.sendMessage('Test message')).rejects.toThrow()
    })

    it('handles network timeouts', async () => {
      server.use(
        http.post(`${API_BASE}/api/chat`, () => {
          return new Promise(() => {
            // Never resolves to simulate timeout
          })
        })
      )

      // This should timeout based on the ApiClient timeout configuration
      await expect(apiService.sendMessage('Test message')).rejects.toThrow(/timeout/i)
    }, 35000) // Longer timeout for this test

    it('retrieves chat history successfully', async () => {
      const mockSessions = [
        createMockChatSession({ name: 'Session 1' }),
        createMockChatSession({ name: 'Session 2' }),
      ]

      server.use(
        http.get(`${API_BASE}/api/chat/history`, () => {
          return HttpResponse.json(
            createMockApiResponse({ sessions: mockSessions })
          )
        })
      )

      const result = await apiService.getChatHistory()

      expect(result.success).toBe(true)
      // Issue #156 Fix: getChatHistory() returns ApiResponse<ChatMessage[]>, not { sessions: [] }
      expect(result.data).toBeDefined()
      expect(result.data).toHaveLength(2)
    })

    it('retrieves specific chat messages', async () => {
      const mockMessages = [
        createMockChatMessage({ content: 'Hello', sender: 'user' }),
        createMockChatMessage({ content: 'Hi there!', sender: 'assistant' }),
      ]

      server.use(
        http.get(`${API_BASE}/api/chat/history/chat-123`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              chatId: 'chat-123',
              messages: mockMessages,
            })
          )
        })
      )

      const result = await apiService.getChatMessages('chat-123')

      expect(result.success).toBe(true)
      // Issue #156 Fix: getChatMessages() returns ApiResponse<{ history: ChatMessage[] }>, not { messages, chatId }
      expect(result.data).toBeDefined()
      expect(result.data!.history).toHaveLength(2)
    })

    it('deletes chat history successfully', async () => {
      server.use(
        http.delete(`${API_BASE}/api/chat/history/chat-123`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              deleted: true,
              chatId: 'chat-123',
            })
          )
        })
      )

      const result = await apiService.deleteChatHistory('chat-123')

      expect(result.success).toBe(true)
      expect(result.data.deleted).toBe(true)
      expect(result.data.chatId).toBe('chat-123')
    })
  })

  describe('Workflow API Integration', () => {
    it('retrieves workflows successfully', async () => {
      const mockWorkflows = [
        createMockWorkflow({ name: 'Workflow 1', status: 'running' }),
        createMockWorkflow({ name: 'Workflow 2', status: 'completed' }),
      ]

      server.use(
        http.get(`${API_BASE}/api/workflow/workflows`, () => {
          return HttpResponse.json(
            createMockApiResponse({ workflows: mockWorkflows })
          )
        })
      )

      const result = await apiService.getWorkflows()

      expect(result.success).toBe(true)
      expect(result.data.workflows).toHaveLength(2)
      expect(result.data.workflows[0].status).toBe('running')
    })

    it('retrieves workflow details', async () => {
      const mockWorkflow = createMockWorkflow({
        id: 'workflow-123',
        steps: [
          { id: 1, name: 'Step 1', status: 'completed' },
          { id: 2, name: 'Step 2', status: 'running' },
        ],
      })

      server.use(
        http.get(`${API_BASE}/api/workflow/workflow/workflow-123`, () => {
          return HttpResponse.json(
            createMockApiResponse({ workflow: mockWorkflow })
          )
        })
      )

      const result = await apiService.getWorkflowDetails('workflow-123')

      expect(result.success).toBe(true)
      expect(result.data.workflow.id).toBe('workflow-123')
      expect(result.data.workflow.steps).toHaveLength(2)
    })

    it('approves workflow step', async () => {
      server.use(
        http.post(`${API_BASE}/api/workflow/workflow/workflow-123/approve`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              workflowId: 'workflow-123',
              approved: true,
            })
          )
        })
      )

      // Issue #156 Fix: approveWorkflowStep expects WorkflowApproval object, not string
      const result = await apiService.approveWorkflowStep('workflow-123', {
        workflowId: 'workflow-123',
        stepId: 'step-2',
        approved: true
      })

      expect(result.success).toBe(true)
      expect(result.data.approved).toBe(true)
    })

    it('cancels workflow', async () => {
      server.use(
        http.delete(`${API_BASE}/api/workflow/workflow/workflow-123`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              workflowId: 'workflow-123',
              cancelled: true,
            })
          )
        })
      )

      const result = await apiService.cancelWorkflow('workflow-123')

      expect(result.success).toBe(true)
      expect(result.data.cancelled).toBe(true)
    })
  })

  describe('Settings API Integration', () => {
    it('retrieves settings successfully', async () => {
      const mockSettings = createMockSettings()

      server.use(
        http.get(`${API_BASE}/api/settings`, () => {
          return HttpResponse.json(
            createMockApiResponse({ settings: mockSettings })
          )
        })
      )

      const result = await apiService.getSettings()

      expect(result.success).toBe(true)
      expect(result.data.settings.chat.auto_scroll).toBe(true)
      expect(result.data.settings.backend.host).toBe('localhost')
    })

    it('saves settings successfully', async () => {
      const settingsToSave = createMockSettings({
        chat: { auto_scroll: false, max_messages: 200 }
      })

      server.use(
        http.post(`${API_BASE}/api/settings`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              settings: settingsToSave,
              saved: true,
            })
          )
        })
      )

      const result = await apiService.saveSettings(settingsToSave)

      expect(result.success).toBe(true)
      expect(result.data.saved).toBe(true)
    })

    it('handles settings validation errors', async () => {
      server.use(
        http.post(`${API_BASE}/api/settings`, () => {
          return new HttpResponse(null, {
            status: 400,
            headers: { 'Content-Type': 'application/json' }
          })
        })
      )

      await expect(
        apiService.saveSettings({ invalid: 'settings' })
      ).rejects.toThrow()
    })
  })

  describe('System API Integration', () => {
    it('retrieves system health', async () => {
      server.use(
        http.get(`${API_BASE}/api/system/health`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              status: 'healthy',
              version: '1.0.0',
              uptime: 3600,
              services: {
                database: 'connected',
                redis: 'connected',
                llm: 'available',
              },
            })
          )
        })
      )

      const result = await apiService.getSystemHealth()

      expect(result.success).toBe(true)
      expect(result.data.status).toBe('healthy')
      expect(result.data.services.database).toBe('connected')
    })

    it('retrieves system information', async () => {
      server.use(
        http.get(`${API_BASE}/api/system/info`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              version: '1.0.0',
              environment: 'test',
              features: ['chat', 'workflow', 'terminal'],
              build: {
                date: '2024-01-01',
                commit: 'abc123',
              },
            })
          )
        })
      )

      const result = await apiService.getSystemInfo()

      expect(result.success).toBe(true)
      expect(result.data.features).toContain('chat')
      expect(result.data.features).toContain('workflow')
    })

    it('handles system API errors', async () => {
      server.use(
        http.get(`${API_BASE}/api/system/health`, () => {
          return new HttpResponse(null, { status: 503 })
        })
      )

      await expect(apiService.getSystemHealth()).rejects.toThrow()
    })
  })

  describe('Terminal API Integration', () => {
    it('executes command successfully', async () => {
      server.use(
        http.post(`${API_BASE}/api/terminal/execute`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              command: 'ls -la',
              output: 'total 48\ndrwxr-xr-x  6 user user 4096 Jan 1 12:00 .',
              exitCode: 0,
              duration: 150,
            })
          )
        })
      )

      const result = await apiService.executeCommand('ls -la')

      expect(result.success).toBe(true)
      expect(result.data.command).toBe('ls -la')
      expect(result.data.exitCode).toBe(0)
    })

    it('handles command execution errors', async () => {
      server.use(
        http.post(`${API_BASE}/api/terminal/execute`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              command: 'invalid-command',
              output: 'command not found: invalid-command',
              exitCode: 127,
              error: true,
            })
          )
        })
      )

      const result = await apiService.executeCommand('invalid-command')

      expect(result.success).toBe(true) // API call succeeded
      expect(result.data.exitCode).toBe(127) // But command failed
      expect(result.data.error).toBe(true)
    })

    it('interrupts process successfully', async () => {
      server.use(
        http.post(`${API_BASE}/api/terminal/interrupt`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              interrupted: true,
              signal: 'SIGINT',
              message: 'Process interrupted',
            })
          )
        })
      )

      const result = await apiService.interruptProcess()

      expect(result.success).toBe(true)
      expect(result.data.interrupted).toBe(true)
      expect(result.data.signal).toBe('SIGINT')
    })

    it('kills all processes successfully', async () => {
      server.use(
        http.post(`${API_BASE}/api/terminal/kill`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              killed: true,
              processCount: 3,
              message: 'All processes terminated',
            })
          )
        })
      )

      const result = await apiService.killAllProcesses()

      expect(result.success).toBe(true)
      expect(result.data.killed).toBe(true)
      expect(result.data.processCount).toBe(3)
    })
  })

  describe('Knowledge Base API Integration', () => {
    it('searches knowledge base successfully', async () => {
      server.use(
        http.post(`${API_BASE}/api/knowledge_base/search`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              query: 'test search',
              results: [
                {
                  id: '1',
                  content: 'Test knowledge base result',
                  score: 0.95,
                  metadata: { source: 'test-doc.md' },
                },
                {
                  id: '2',
                  content: 'Another relevant result',
                  score: 0.87,
                  metadata: { source: 'guide.md' },
                },
              ],
              total: 2,
            })
          )
        })
      )

      const result = await apiService.searchKnowledgeBase('test search', 10)

      expect(result.success).toBe(true)
      expect(result.data.results).toHaveLength(2)
      expect(result.data.results[0].score).toBe(0.95)
    })

    it('handles empty search results', async () => {
      server.use(
        http.post(`${API_BASE}/api/knowledge_base/search`, () => {
          return HttpResponse.json(
            createMockApiResponse({
              query: 'no matches',
              results: [],
              total: 0,
            })
          )
        })
      )

      const result = await apiService.searchKnowledgeBase('no matches')

      expect(result.success).toBe(true)
      expect(result.data.results).toHaveLength(0)
      expect(result.data.total).toBe(0)
    })
  })

  describe('Error Handling and Resilience', () => {
    it('handles network connectivity issues', async () => {
      server.use(
        http.get(`${API_BASE}/api/system/health`, () => {
          return HttpResponse.error()
        })
      )

      await expect(apiService.getSystemHealth()).rejects.toThrow()
    })

    it('handles malformed JSON responses', async () => {
      server.use(
        http.get(`${API_BASE}/api/system/health`, () => {
          return new HttpResponse('invalid json{', {
            headers: { 'Content-Type': 'application/json' }
          })
        })
      )

      await expect(apiService.getSystemHealth()).rejects.toThrow()
    })

    it('handles partial API failures gracefully', async () => {
      let callCount = 0

      server.use(
        http.get(`${API_BASE}/api/system/health`, () => {
          callCount++
          if (callCount === 1) {
            return new HttpResponse(null, { status: 500 })
          }
          return HttpResponse.json(
            createMockApiResponse({ status: 'healthy' })
          )
        })
      )

      // First call should fail
      await expect(apiService.getSystemHealth()).rejects.toThrow()

      // Second call should succeed (simulating recovery)
      const result = await apiService.getSystemHealth()
      expect(result.success).toBe(true)
    })

    it('handles rate limiting', async () => {
      server.use(
        http.post(`${API_BASE}/api/chat`, () => {
          return new HttpResponse(null, {
            status: 429,
            headers: { 'Retry-After': '60' }
          })
        })
      )

      await expect(
        apiService.sendMessage('Rate limited message')
      ).rejects.toThrow()
    })
  })

  describe('Performance and Load Testing', () => {
    it('handles multiple concurrent requests', async () => {
      server.use(
        http.get(`${API_BASE}/api/system/health`, () => {
          return HttpResponse.json(
            createMockApiResponse({ status: 'healthy' })
          )
        })
      )

      const promises = Array.from({ length: 10 }, () =>
        apiService.getSystemHealth()
      )

      const results = await Promise.all(promises)

      expect(results).toHaveLength(10)
      results.forEach(result => {
        expect(result.success).toBe(true)
        expect(result.data.status).toBe('healthy')
      })
    })

    it('handles large response payloads', async () => {
      const largeData = {
        messages: Array.from({ length: 1000 }, (_, i) =>
          createMockChatMessage({ content: `Message ${i}` })
        )
      }

      server.use(
        http.get(`${API_BASE}/api/chat/history/large-chat`, () => {
          return HttpResponse.json(
            createMockApiResponse(largeData)
          )
        })
      )

      const result = await apiService.getChatMessages('large-chat')

      expect(result.success).toBe(true)
      // Issue #156 Fix: getChatMessages() returns ApiResponse<{ history: ChatMessage[] }>, not { messages }
      expect(result.data).toBeDefined()
      expect(result.data!.history).toHaveLength(1000)
    })
  })
})
