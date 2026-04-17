/**
 * useKnowledgeFiles Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { UploadResponse } from '@/types/knowledgeBase'
import { useKnowledgeFiles } from '../knowledge/useKnowledgeFiles'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

import apiClient from '@/utils/ApiClient'

describe('useKnowledgeFiles', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('uploadKnowledgeFile', () => {
    it('should upload a knowledge file successfully', async () => {
      const mockUploadResponse: UploadResponse = {
        success: true,
        file_path: '/uploads/test.pdf',
        facts_added: 5,
      }

      const formData = new FormData()
      formData.append('file', new Blob(['test'], { type: 'application/pdf' }))

      vi.mocked(apiClient.post).mockResolvedValue(mockUploadResponse)

      const { uploadKnowledgeFile } = useKnowledgeFiles()
      const result = await uploadKnowledgeFile(formData)

      expect(result).toEqual(mockUploadResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/upload',
        formData
      )
    })

    it('should throw error on upload failure', async () => {
      const formData = new FormData()

      vi.mocked(apiClient.post).mockRejectedValue(new Error('HTTP 400: Upload failed'))

      const { uploadKnowledgeFile } = useKnowledgeFiles()

      await expect(uploadKnowledgeFile(formData)).rejects.toThrow('Upload failed')
    })
  })
})
