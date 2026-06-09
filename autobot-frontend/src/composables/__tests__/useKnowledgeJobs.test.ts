// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeJobs Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  VectorizationStatusResponse,
  VectorizationResponse,
} from '@/types/knowledgeBase'
import { useKnowledgeJobs } from '../knowledge/useKnowledgeJobs'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getApiUrl: vi.fn((url) => Promise.resolve(`/api${url}`)),
    getTimeout: vi.fn((type) => {
      if (type === 'knowledge') return 300000
      return 30000
    }),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

import apiClient from '@/utils/ApiClient'

interface JobStatus {
  task_id: string
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE'
  result?: Record<string, unknown>
  error?: string
  progress?: number
}

describe('useKnowledgeJobs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('vectorizeFacts', () => {
    it('should vectorize facts with default parameters', async () => {
      const mockVectorizationResponse: VectorizationResponse = {
        status: 'success',
        message: 'Vectorization complete',
        successful: 50,
        skipped: 0,
        failed: 0,
        total_processed: 50,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockVectorizationResponse)

      const { vectorizeFacts } = useKnowledgeJobs()
      const result = await vectorizeFacts()

      expect(result).toEqual(mockVectorizationResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/vectorize_facts',
        {
          batch_size: 50,
          batch_delay: 0.5,
          skip_existing: true,
        },
        { timeout: 300000 }
      )
    })

    it('should vectorize with custom batch parameters', async () => {
      const mockResponse: VectorizationResponse = {
        status: 'success',
        message: 'Vectorization complete',
        successful: 100,
        skipped: 25,
        failed: 0,
        total_processed: 125,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { vectorizeFacts } = useKnowledgeJobs()
      await vectorizeFacts(100, 1.0, false)

      expect(apiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        {
          batch_size: 100,
          batch_delay: 1.0,
          skip_existing: false,
        },
        expect.any(Object)
      )
    })
  })

  describe('getVectorizationStatus', () => {
    it('should fetch vectorization status', async () => {
      const mockStatus: VectorizationStatusResponse = {
        status: 'in_progress',
        total_facts: 200,
        vectorized_facts: 50,
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockStatus)

      const { getVectorizationStatus } = useKnowledgeJobs()
      const result = await getVectorizationStatus()

      expect(result).toEqual(mockStatus)
      expect(result.status).toBe('in_progress')
    })
  })

  describe('pollJobStatus', () => {
    it('should poll job status successfully', async () => {
      const mockJobStatus: JobStatus = {
        task_id: 'task-123',
        status: 'SUCCESS',
        result: { processed: 100 },
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockJobStatus)

      const { pollJobStatus } = useKnowledgeJobs()
      const result = await pollJobStatus('task-123')

      expect(result).toEqual(mockJobStatus)
      expect(apiClient.get).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/job_status/task-123'
      )
    })

    it('should handle various job statuses', async () => {
      const statuses: JobStatus['status'][] = ['PENDING', 'PROGRESS', 'SUCCESS', 'FAILURE']

      for (const status of statuses) {
        const mockJobStatus: JobStatus = { task_id: 'task-123', status }

        vi.mocked(apiClient.get).mockResolvedValue(mockJobStatus)

        const { pollJobStatus } = useKnowledgeJobs()
        const result = (await pollJobStatus('task-123')) as JobStatus

        expect(result.status).toBe(status)
      }
    })
  })

  describe('reactive refs + managed actions (#5195)', () => {
    it('should expose initial ref state as null/false/null', () => {
      const {
        vectorizationStatus,
        vectorizationResult,
        isLoadingStatus,
        isVectorizing,
        error,
      } = useKnowledgeJobs()

      expect(vectorizationStatus.value).toBe(null)
      expect(vectorizationResult.value).toBe(null)
      expect(isLoadingStatus.value).toBe(false)
      expect(isVectorizing.value).toBe(false)
      expect(error.value).toBe(null)
    })

    it('refreshStatus() should flip isLoadingStatus and populate vectorizationStatus', async () => {
      const mockStatus: VectorizationStatusResponse = {
        status: 'idle',
        total_facts: 10,
        vectorized_facts: 10,
      }
      vi.mocked(apiClient.get).mockResolvedValue(mockStatus)

      const { vectorizationStatus, isLoadingStatus, error, refreshStatus } =
        useKnowledgeJobs()

      const promise = refreshStatus()
      expect(isLoadingStatus.value).toBe(true)

      const data = await promise
      expect(data).toEqual(mockStatus)
      expect(vectorizationStatus.value).toEqual(mockStatus)
      expect(isLoadingStatus.value).toBe(false)
      expect(error.value).toBe(null)
    })

    it('refreshStatus() should populate error ref and reset isLoadingStatus on failure', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('status boom'))

      const { vectorizationStatus, isLoadingStatus, error, refreshStatus } =
        useKnowledgeJobs()

      await expect(refreshStatus()).rejects.toThrow('status boom')
      expect(vectorizationStatus.value).toBe(null)
      expect(isLoadingStatus.value).toBe(false)
      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe('status boom')
    })

    it('runVectorization() should flip isVectorizing, populate vectorizationResult on success', async () => {
      const mockResponse: VectorizationResponse = {
        status: 'success',
        message: 'ok',
        successful: 50,
        skipped: 0,
        failed: 0,
        total_processed: 50,
      }
      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { vectorizationResult, isVectorizing, error, runVectorization } =
        useKnowledgeJobs()

      const promise = runVectorization(100, 1.0, false)
      expect(isVectorizing.value).toBe(true)

      const data = await promise
      expect(data).toEqual(mockResponse)
      expect(vectorizationResult.value).toEqual(mockResponse)
      expect(isVectorizing.value).toBe(false)
      expect(error.value).toBe(null)
      // Verify params forwarded
      expect(apiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        { batch_size: 100, batch_delay: 1.0, skip_existing: false },
        expect.any(Object)
      )
    })

    it('runVectorization() error should set error ref as Error instance, not raw string', async () => {
      vi.mocked(apiClient.post).mockRejectedValue('vector failure')

      const { error, isVectorizing, runVectorization } = useKnowledgeJobs()

      await expect(runVectorization()).rejects.toBeDefined()
      expect(isVectorizing.value).toBe(false)
      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe('vector failure')
    })
  })
})
