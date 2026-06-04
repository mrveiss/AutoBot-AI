// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()
const mockRawRequest = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete, rawRequest: mockRawRequest }),
}))

describe('useTranscriberApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Projects', () => {
    it('listProjects calls GET /api/transcriber/projects', async () => {
      mockGet.mockResolvedValue([])
      const api = useTranscriberApi()
      await api.listProjects()
      expect(mockGet).toHaveBeenCalledWith('/api/transcriber/projects')
    })

    it('getProject calls GET /api/transcriber/projects/:id', async () => {
      mockGet.mockResolvedValue({ id: 1, name: 'Test', description: 'Desc' })
      const api = useTranscriberApi()
      await api.getProject(1)
      expect(mockGet).toHaveBeenCalledWith('/api/transcriber/projects/1')
    })

    it('createProject calls POST /api/transcriber/projects', async () => {
      mockPost.mockResolvedValue({ id: 1, name: 'P', description: '' })
      const api = useTranscriberApi()
      await api.createProject('P', '')
      expect(mockPost).toHaveBeenCalledWith('/api/transcriber/projects', { name: 'P', description: '' })
    })

    it('updateProject calls PATCH /api/transcriber/projects/:id', async () => {
      mockPatch.mockResolvedValue({ id: 1, name: 'Updated', description: 'New desc' })
      const api = useTranscriberApi()
      await api.updateProject(1, 'Updated', 'New desc')
      expect(mockPatch).toHaveBeenCalledWith('/api/transcriber/projects/1', { name: 'Updated', description: 'New desc' })
    })

    it('deleteProject calls DELETE /api/transcriber/projects/:id', async () => {
      mockDelete.mockResolvedValue(undefined)
      const api = useTranscriberApi()
      await api.deleteProject(1)
      expect(mockDelete).toHaveBeenCalledWith('/api/transcriber/projects/1')
    })

    it('listProjects handles API errors', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))
      const api = useTranscriberApi()
      await expect(api.listProjects()).rejects.toThrow('Network error')
    })
  })

  describe('Recordings', () => {
    it('listRecordings calls GET /api/transcriber/projects/:id/recordings', async () => {
      mockGet.mockResolvedValue([])
      const api = useTranscriberApi()
      await api.listRecordings(5)
      expect(mockGet).toHaveBeenCalledWith('/api/transcriber/projects/5/recordings')
    })

    it('getRecording calls GET /api/transcriber/recordings/:id', async () => {
      mockGet.mockResolvedValue({ id: 1, filename: 'test.mp3' })
      const api = useTranscriberApi()
      await api.getRecording(1)
      expect(mockGet).toHaveBeenCalledWith('/api/transcriber/recordings/1')
    })

    it('deleteRecording calls DELETE /api/transcriber/recordings/:id', async () => {
      mockDelete.mockResolvedValue(undefined)
      const api = useTranscriberApi()
      await api.deleteRecording(1)
      expect(mockDelete).toHaveBeenCalledWith('/api/transcriber/recordings/1')
    })

    it('uploadRecording creates FormData and calls POST', async () => {
      mockPost.mockResolvedValue({ id: 1, filename: 'audio.mp3', status: 'pending' })
      const api = useTranscriberApi()
      const mockFile = new File(['audio content'], 'audio.mp3', { type: 'audio/mpeg' })

      await api.uploadRecording(5, mockFile)

      expect(mockPost).toHaveBeenCalledWith(
        '/api/transcriber/projects/5/recordings',
        expect.any(FormData)
      )

      const formData = mockPost.mock.calls[0][1] as FormData
      expect(formData.get('file')).toBe(mockFile)
    })

    it('uploadRecording handles file upload errors', async () => {
      mockPost.mockRejectedValue(new Error('File too large'))
      const api = useTranscriberApi()
      const mockFile = new File(['audio'], 'audio.mp3', { type: 'audio/mpeg' })

      await expect(api.uploadRecording(5, mockFile)).rejects.toThrow('File too large')
    })
  })

  describe('Transcripts', () => {
    it('getTranscript calls GET /api/transcriber/recordings/:id/transcript', async () => {
      mockGet.mockResolvedValue({ recording: {}, speakers: [], segments: [] })
      const api = useTranscriberApi()
      await api.getTranscript(42)
      expect(mockGet).toHaveBeenCalledWith('/api/transcriber/recordings/42/transcript')
    })

    it('updateSegment calls PATCH /api/transcriber/segments/:id', async () => {
      mockPatch.mockResolvedValue({ id: 1, text: 'Updated text' })
      const api = useTranscriberApi()
      await api.updateSegment(1, 'Updated text')
      expect(mockPatch).toHaveBeenCalledWith('/api/transcriber/segments/1', { text: 'Updated text' })
    })

    it('updateSpeaker calls PATCH /api/transcriber/speakers/:id', async () => {
      mockPatch.mockResolvedValue({ id: 1, display_name: 'John Doe' })
      const api = useTranscriberApi()
      await api.updateSpeaker(1, 'John Doe')
      expect(mockPatch).toHaveBeenCalledWith('/api/transcriber/speakers/1', { display_name: 'John Doe' })
    })

    it('createNote calls POST /api/transcriber/segments/:id/notes', async () => {
      mockPost.mockResolvedValue({ id: 1, content: 'Important note' })
      const api = useTranscriberApi()
      await api.createNote(5, 'Important note')
      expect(mockPost).toHaveBeenCalledWith('/api/transcriber/segments/5/notes', { content: 'Important note' })
    })

    it('deleteNote calls DELETE /api/transcriber/notes/:id', async () => {
      mockDelete.mockResolvedValue(undefined)
      const api = useTranscriberApi()
      await api.deleteNote(1)
      expect(mockDelete).toHaveBeenCalledWith('/api/transcriber/notes/1')
    })
  })

  describe('Export', () => {
    it('exportRecording calls rawRequest with correct format', async () => {
      mockRawRequest.mockResolvedValue(new Blob())
      const api = useTranscriberApi()
      await api.exportRecording(1, 'pdf')
      expect(mockRawRequest).toHaveBeenCalledWith('/api/transcriber/recordings/1/export', {
        method: 'POST',
        body: { format: 'pdf' },
      })
    })

    it('exportRecording supports all formats', async () => {
      mockRawRequest.mockResolvedValue(new Blob())
      const api = useTranscriberApi()

      await api.exportRecording(1, 'docx')
      expect(mockRawRequest).toHaveBeenCalledWith('/api/transcriber/recordings/1/export', {
        method: 'POST',
        body: { format: 'docx' },
      })

      await api.exportRecording(1, 'srt')
      expect(mockRawRequest).toHaveBeenCalledWith('/api/transcriber/recordings/1/export', {
        method: 'POST',
        body: { format: 'srt' },
      })

      await api.exportRecording(1, 'vtt')
      expect(mockRawRequest).toHaveBeenCalledWith('/api/transcriber/recordings/1/export', {
        method: 'POST',
        body: { format: 'vtt' },
      })
    })

    it('exportRecording passes additional options', async () => {
      mockRawRequest.mockResolvedValue(new Blob())
      const api = useTranscriberApi()
      await api.exportRecording(1, 'pdf', { include_timestamps: true })
      expect(mockRawRequest).toHaveBeenCalledWith('/api/transcriber/recordings/1/export', {
        method: 'POST',
        body: { format: 'pdf', include_timestamps: true },
      })
    })
  })

  describe('AI', () => {
    let mockEventSource: any

    beforeEach(() => {
      mockEventSource = {
        close: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }
      vi.stubGlobal('EventSource', vi.fn(function EventSource(url: string) {
        return mockEventSource
      }))
    })

    it('aiAsk creates EventSource with correct URL', () => {
      const api = useTranscriberApi()
      const result = api.aiAsk(42, 'summarize')

      expect(global.EventSource).toHaveBeenCalledWith(
        expect.stringContaining('/api/transcriber/recordings/42/ai/ask?action=summarize')
      )
      expect(result).toBe(mockEventSource)
    })

    it('aiAsk includes custom question when provided', () => {
      const api = useTranscriberApi()
      api.aiAsk(42, 'custom', 'What is the main topic?')

      expect(global.EventSource).toHaveBeenCalledWith(
        expect.stringContaining('action=custom&q=What%20is%20the%20main%20topic%3F')
      )
    })

    it('aiAsk returns mocked EventSource instance', () => {
      const api = useTranscriberApi()
      const result = api.aiAsk(1, 'summarize')
      expect(result).toBe(mockEventSource)
      expect(result.close).toBeDefined()
    })
  })

  describe('Knowledge Base', () => {
    it('kbPush calls POST /api/transcriber/recordings/:id/kb/push', async () => {
      mockPost.mockResolvedValue({ success: true })
      const api = useTranscriberApi()
      await api.kbPush(1, 'collection-123')
      expect(mockPost).toHaveBeenCalledWith('/api/transcriber/recordings/1/kb/push', {
        collection_id: 'collection-123'
      })
    })

    it('kbStatus calls GET /api/transcriber/recordings/:id/kb/status', async () => {
      mockGet.mockResolvedValue({ pushed: true, pushed_at: '2025-01-01' })
      const api = useTranscriberApi()
      await api.kbStatus(1)
      expect(mockGet).toHaveBeenCalledWith('/api/transcriber/recordings/1/kb/status')
    })

    it('kbPush handles errors', async () => {
      mockPost.mockRejectedValue(new Error('KB not available'))
      const api = useTranscriberApi()
      await expect(api.kbPush(1, 'collection-123')).rejects.toThrow('KB not available')
    })
  })
})
