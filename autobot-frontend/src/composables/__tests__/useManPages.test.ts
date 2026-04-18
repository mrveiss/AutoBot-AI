/**
 * useManPages Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  IntegrationResponse,
  ManPagesPopulateResponse,
  AutoBotDocsResponse,
} from '@/types/knowledgeBase'
import { useManPages, type ManPagesSummary } from '../knowledge/useManPages'

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

describe('useManPages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('fetchManPagesSummary', () => {
    it('should fetch man pages summary', async () => {
      const mockSummary: ManPagesSummary = {
        status: 'ready',
        successful: 150,
        processed: 150,
        current_man_page_files: 1500,
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockSummary)

      const { fetchManPagesSummary } = useManPages()
      const result = await fetchManPagesSummary()

      expect(result).toEqual(mockSummary)
      expect(result?.status).toBe('ready')
    })

    it('should return null on error', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('HTTP 500'))

      const { fetchManPagesSummary } = useManPages()
      const result = await fetchManPagesSummary()

      expect(result).toBe(null)
    })
  })

  describe('integrateManPages', () => {
    it('should integrate man pages for a machine', async () => {
      const mockResponse: IntegrationResponse = {
        status: 'queued',
        message: 'Man pages integration queued',
        machine_id: 'host1',
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { integrateManPages } = useManPages()
      const result = await integrateManPages('host1')

      expect(result).toEqual(mockResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/man_pages/integrate',
        { machine_id: 'host1' }
      )
    })
  })

  describe('populateManPages', () => {
    it('should populate man pages for a machine', async () => {
      const mockResponse: ManPagesPopulateResponse = {
        status: 'success',
        message: 'Man pages populated',
        machine_id: 'host1',
        man_pages_added: 150,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { populateManPages } = useManPages()
      const result = await populateManPages('host1')

      expect(result).toEqual(mockResponse)
    })
  })

  describe('populateAutoBotDocs', () => {
    it('should populate AutoBot documentation', async () => {
      const mockResponse: AutoBotDocsResponse = {
        status: 'success',
        message: 'AutoBot docs populated',
        documents_processed: 45,
        facts_added: 120,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { populateAutoBotDocs } = useManPages()
      const result = await populateAutoBotDocs()

      expect(result).toEqual(mockResponse)
    })
  })
})
