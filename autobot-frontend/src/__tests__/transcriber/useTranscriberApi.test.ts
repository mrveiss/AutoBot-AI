// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({ get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete }),
}))

describe('useTranscriberApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('listProjects calls GET /api/transcriber/projects', async () => {
    mockGet.mockResolvedValue([])
    const api = useTranscriberApi()
    await api.listProjects()
    expect(mockGet).toHaveBeenCalledWith('/api/transcriber/projects')
  })

  it('createProject calls POST /api/transcriber/projects', async () => {
    mockPost.mockResolvedValue({ id: 1, name: 'P', description: '' })
    const api = useTranscriberApi()
    await api.createProject('P', '')
    expect(mockPost).toHaveBeenCalledWith('/api/transcriber/projects', { name: 'P', description: '' })
  })

  it('getTranscript calls GET /api/transcriber/recordings/:id/transcript', async () => {
    mockGet.mockResolvedValue({ recording: {}, speakers: [], segments: [] })
    const api = useTranscriberApi()
    await api.getTranscript(42)
    expect(mockGet).toHaveBeenCalledWith('/api/transcriber/recordings/42/transcript')
  })
})
