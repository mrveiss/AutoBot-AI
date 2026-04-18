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
})
