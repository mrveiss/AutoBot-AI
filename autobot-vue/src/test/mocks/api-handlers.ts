import { http, HttpResponse } from 'msw'
// Issue #156 Fix: Corrected Python-style import to TypeScript syntax
import { NetworkConstants, ServiceURLs } from '@/constants/network'
import {
  createMockApiResponse,
  createMockChatMessage,
  createMockChatSession,
  createMockWorkflow,
  createMockSettings,
} from '../utils/test-utils'

// Base URL for API endpoints
const API_BASE = process.env.VITE_API_BASE_URL || ServiceURLs.BACKEND_LOCAL

export const handlers = [
  // Chat API endpoints
  http.post(`${API_BASE}/api/chat`, async ({ request }) => {
    const body = await request.json() as any
    const mockMessage = createMockChatMessage({
      content: `Echo: ${body.message}`,
      sender: 'assistant',
    })
    
    return HttpResponse.json(
      createMockApiResponse({
        message: mockMessage,
        chatId: body.chatId || 'test-chat-id',
      })
    )
  }),

  http.get(`${API_BASE}/api/chat/history`, () => {
    const mockSessions = [
      createMockChatSession({ name: 'Test Chat 1' }),
      createMockChatSession({ name: 'Test Chat 2' }),
    ]
    
    return HttpResponse.json(
      createMockApiResponse({ sessions: mockSessions })
    )
  }),

  http.get(`${API_BASE}/api/chat/history/:chatId`, ({ params }) => {
    const messages = [
      createMockChatMessage({ content: 'Hello', sender: 'user' }),
      createMockChatMessage({ content: 'Hi there!', sender: 'assistant' }),
    ]
    
    return HttpResponse.json(
      createMockApiResponse({
        chatId: params.chatId,
        messages,
      })
    )
  }),

  http.delete(`${API_BASE}/api/chat/history/:chatId`, ({ params }) => {
    return HttpResponse.json(
      createMockApiResponse({
        deleted: true,
        chatId: params.chatId,
      })
    )
  }),

  // Workflow API endpoints
  http.get(`${API_BASE}/api/workflow/workflows`, () => {
    const mockWorkflows = [
      createMockWorkflow({ name: 'Test Workflow 1', status: 'running' }),
      createMockWorkflow({ name: 'Test Workflow 2', status: 'completed' }),
    ]
    
    return HttpResponse.json(
      createMockApiResponse({ workflows: mockWorkflows })
    )
  }),

  http.get(`${API_BASE}/api/workflow/workflow/:id`, ({ params }) => {
    const mockWorkflow = createMockWorkflow({
      id: params.id,
      steps: [
        { id: 1, name: 'Step 1', status: 'completed' },
        { id: 2, name: 'Step 2', status: 'running' },
      ],
    })
    
    return HttpResponse.json(
      createMockApiResponse({ workflow: mockWorkflow })
    )
  }),

  http.get(`${API_BASE}/api/workflow/workflow/:id/status`, ({ params }) => {
    return HttpResponse.json(
      createMockApiResponse({
        workflowId: params.id,
        status: 'running',
        currentStep: 2,
        totalSteps: 5,
      })
    )
  }),

  http.post(`${API_BASE}/api/workflow/workflow/:id/approve`, ({ params }) => {
    return HttpResponse.json(
      createMockApiResponse({
        workflowId: params.id,
        approved: true,
      })
    )
  }),

  http.delete(`${API_BASE}/api/workflow/workflow/:id`, ({ params }) => {
    return HttpResponse.json(
      createMockApiResponse({
        workflowId: params.id,
        cancelled: true,
      })
    )
  }),

  // Settings API endpoints
  http.get(`${API_BASE}/api/settings`, () => {
    return HttpResponse.json(
      createMockApiResponse({ settings: createMockSettings() })
    )
  }),

  http.post(`${API_BASE}/api/settings`, async ({ request }) => {
    const settings = await request.json()
    return HttpResponse.json(
      createMockApiResponse({ settings, saved: true })
    )
  }),

  // System API endpoints
  http.get(`${API_BASE}/api/system/health`, () => {
    return HttpResponse.json(
      createMockApiResponse({
        status: 'healthy',
        version: '1.0.0',
        uptime: 3600,
        timestamp: Date.now(),
      })
    )
  }),

  http.get(`${API_BASE}/api/system/info`, () => {
    return HttpResponse.json(
      createMockApiResponse({
        version: '1.0.0',
        environment: 'test',
        features: ['chat', 'workflow', 'terminal'],
      })
    )
  }),

  // Terminal API endpoints
  http.post(`${API_BASE}/api/terminal/execute`, async ({ request }) => {
    const body = await request.json() as any
    return HttpResponse.json(
      createMockApiResponse({
        command: body.command,
        output: `Executed: ${body.command}`,
        exitCode: 0,
      })
    )
  }),

  http.post(`${API_BASE}/api/terminal/interrupt`, () => {
    return HttpResponse.json(
      createMockApiResponse({
        interrupted: true,
        message: 'Process interrupted',
      })
    )
  }),

  http.post(`${API_BASE}/api/terminal/kill`, () => {
    return HttpResponse.json(
      createMockApiResponse({
        killed: true,
        message: 'All processes terminated',
      })
    )
  }),

  // Knowledge Base API endpoints
  http.post(`${API_BASE}/api/knowledge_base/search`, async ({ request }) => {
    const body = await request.json() as any
    return HttpResponse.json(
      createMockApiResponse({
        query: body.query,
        results: [
          {
            id: '1',
            content: `Search result for: ${body.query}`,
            score: 0.95,
            metadata: { source: 'test-doc' },
          },
        ],
      })
    )
  }),

  // File system API endpoints
  http.get(`${API_BASE}/api/files`, () => {
    return HttpResponse.json(
      createMockApiResponse({
        files: [
          { name: 'test.txt', type: 'file', size: 1024 },
          { name: 'folder', type: 'directory', size: null },
        ],
      })
    )
  }),

  // Error handlers
  http.get(`${API_BASE}/api/error/500`, () => {
    return new HttpResponse(null, { status: 500 })
  }),

  http.get(`${API_BASE}/api/error/404`, () => {
    return new HttpResponse(null, { status: 404 })
  }),

  http.get(`${API_BASE}/api/error/timeout`, () => {
    return new Promise(() => {
      // Never resolves to simulate timeout
    })
  }),
]

// Handlers for different test scenarios
export const errorHandlers = [
  http.post(`${API_BASE}/api/chat`, () => {
    return new HttpResponse(null, { status: 500 })
  }),

  http.get(`${API_BASE}/api/chat/history`, () => {
    return new HttpResponse(null, { status: 503 })
  }),
]

export const slowResponseHandlers = [
  http.post(`${API_BASE}/api/chat`, async () => {
    await new Promise(resolve => setTimeout(resolve, 2000))
    return HttpResponse.json(
      createMockApiResponse({
        message: createMockChatMessage({ content: 'Delayed response' }),
      })
    )
  }),
]