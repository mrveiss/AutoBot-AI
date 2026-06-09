// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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

  describe('reactive refs + managed upload (#5195)', () => {
    it('should expose initial ref state as null/false/null', () => {
      const { uploadResult, isUploading, error } = useKnowledgeFiles()

      expect(uploadResult.value).toBe(null)
      expect(isUploading.value).toBe(false)
      expect(error.value).toBe(null)
    })

    it('upload() should flip isUploading true while in-flight and populate uploadResult', async () => {
      const mockResponse: UploadResponse = {
        success: true,
        file_path: '/uploads/x.pdf',
        facts_added: 3,
      }
      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { uploadResult, isUploading, error, upload } = useKnowledgeFiles()

      const formData = new FormData()
      const promise = upload(formData)
      expect(isUploading.value).toBe(true)

      const data = await promise
      expect(data).toEqual(mockResponse)
      expect(uploadResult.value).toEqual(mockResponse)
      expect(isUploading.value).toBe(false)
      expect(error.value).toBe(null)
    })

    it('upload() should populate error ref and reset isUploading on failure', async () => {
      vi.mocked(apiClient.post).mockRejectedValue(new Error('upload boom'))

      const { uploadResult, isUploading, error, upload } = useKnowledgeFiles()

      await expect(upload(new FormData())).rejects.toThrow('upload boom')
      expect(uploadResult.value).toBe(null)
      expect(isUploading.value).toBe(false)
      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe('upload boom')
    })

    it('upload() error should wrap non-Error thrown value as Error instance', async () => {
      vi.mocked(apiClient.post).mockRejectedValue('raw string')

      const { error, upload } = useKnowledgeFiles()

      await expect(upload(new FormData())).rejects.toBeDefined()
      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe('raw string')
    })
  })
})
