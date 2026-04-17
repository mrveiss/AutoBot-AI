/**
 * useKnowledgeBase Composable Tests
 *
 * Comprehensive unit tests for the knowledge base management composable.
 * Tests cover 30+ API methods and helper functions including:
 * - Knowledge base statistics and categories
 * - Search (basic and advanced)
 * - Fact management (add, upload, vectorize)
 * - Machine profiles and man pages
 * - Background job polling
 * - Icon/formatting helper functions
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  KnowledgeStats,
  CategoryResponse,
  CategoriesListResponse,
  SearchResponse,
  AddFactResponse,
  UploadResponse,
  IntegrationResponse,
  VectorizationStatusResponse,
  VectorizationResponse,
  MachineKnowledgeResponse,
  SystemKnowledgeResponse,
  ManPagesPopulateResponse,
  AutoBotDocsResponse,
  CategorizedFactsResponse,
} from '@/types/knowledgeBase'
import {
  useKnowledgeBase,
  type MachineProfile,
  type ManPagesSummary,
} from '../useKnowledgeBase'

// ========================================
// Mock Setup
// ========================================

// Mock apiClient
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

// Mock fetchWithAuth
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

// Mock parseApiResponse
vi.mock('@/utils/apiResponseHelpers', () => ({
  parseApiResponse: vi.fn((response) => {
    if (!response) return null
    return response.json ? response.json() : response
  }),
}))

// Mock formatHelpers
vi.mock('@/utils/formatHelpers', () => ({
  formatDate: (date: any) => new Date(date).toLocaleDateString(),
  formatFileSize: (bytes: number) => `${(bytes / 1024).toFixed(2)} KB`,
  formatCategoryName: (name: string) => name.replace(/_/g, ' ').toUpperCase(),
}))

// Mock iconMappings
vi.mock('@/utils/iconMappings', () => ({
  getFileIcon: (name: string) => 'fas fa-file',
}))

// Mock appConfig
vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getApiUrl: vi.fn((url) => Promise.resolve(`/api${url}`)),
    getTimeout: vi.fn((type) => {
      if (type === 'knowledge') return 300000
      return 30000
    }),
  },
}))

// Mock logger
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  }),
}))

// Mock ssot-config
vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

import apiClient from '@/utils/ApiClient'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import appConfig from '@/config/AppConfig.js'

// ========================================
// Helper Functions
// ========================================

function mockApiResponse<T>(data: T, ok = true) {
  return {
    ok,
    status: ok ? 200 : 400,
    statusText: ok ? 'OK' : 'Bad Request',
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
    headers: new Map(),
  } as unknown as Response
}

/**
 * Typed wrapper around parseApiResponse mock.
 *
 * `parseApiResponse` in production returns `Promise<any>`, so mocking it with
 * `vi.mocked(parseApiResponse).mockResolvedValue(x)` accepts any value and
 * silently hides test-fixture typos. This helper adds an explicit type
 * parameter so `mockParseApi<KnowledgeStats>(fixture)` fails type-check if
 * `fixture` is not assignable to `KnowledgeStats`.
 */
function mockParseApi<T>(data: T): void {
  vi.mocked(parseApiResponse).mockResolvedValue(data)
}

/**
 * Shape of the background job status response used by `pollJobStatus`.
 * Production types this loosely as `any` (see useKnowledgeBase.ts), so we
 * declare a local interface to keep test fixtures type-checked.
 */
interface JobStatus {
  task_id: string
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE'
  result?: Record<string, unknown>
  error?: string
  progress?: number
}

// ========================================
// Tests
// ========================================

describe('useKnowledgeBase', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // =========================================================================
  // 1. Knowledge Statistics
  // =========================================================================
  describe('fetchStats', () => {
    it('should fetch knowledge base statistics successfully', async () => {
      const mockStats: KnowledgeStats = {
        total_facts: 100,
        total_documents: 50,
        last_updated: '2025-04-12T10:00:00Z',
      }

      const response = mockApiResponse(mockStats)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<KnowledgeStats>(mockStats)

      const { fetchStats } = useKnowledgeBase()
      const result = await fetchStats()

      expect(result).toEqual(mockStats)
      expect(apiClient.get).toHaveBeenCalledWith('/knowledge_base/knowledge_base/stats')
    })

    it('should throw error when stats fetch fails', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(null)

      const { fetchStats } = useKnowledgeBase()

      await expect(fetchStats()).rejects.toThrow('Failed to fetch stats')
    })

    it('should throw error when parseApiResponse fails', async () => {
      const response = mockApiResponse<null>(null)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      vi.mocked(parseApiResponse).mockRejectedValue(new Error('Parse failed'))

      const { fetchStats } = useKnowledgeBase()

      await expect(fetchStats()).rejects.toThrow('Parse failed')
    })
  })

  // =========================================================================
  // 2. Categories
  // =========================================================================
  describe('fetchCategories', () => {
    it('should fetch all categories with counts', async () => {
      const mockCategoriesResponse: CategoriesListResponse = {
        categories: [
          { name: 'architecture', count: 10, id: 'arch-1' },
          { name: 'security', count: 15, id: 'sec-1' },
        ],
        total: 2,
      }

      const response = mockApiResponse(mockCategoriesResponse)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<CategoriesListResponse>(mockCategoriesResponse)

      const { fetchCategories } = useKnowledgeBase()
      const result = await fetchCategories()

      expect(result).toEqual(mockCategoriesResponse.categories)
      expect(apiClient.get).toHaveBeenCalledWith('/knowledge_base/knowledge_base/categories')
    })

    it('should throw error when response structure is invalid', async () => {
      // Intentionally malformed: missing the required `categories` array so
      // that the runtime validator in `fetchCategories` throws. Typed as
      // `unknown` (not `CategoriesListResponse`) because it is deliberately
      // shape-invalid.
      const invalidResponse: unknown = { notCategories: [] }

      const response = mockApiResponse(invalidResponse)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<unknown>(invalidResponse)

      const { fetchCategories } = useKnowledgeBase()

      await expect(fetchCategories()).rejects.toThrow('Invalid categories response format')
    })
  })

  describe('fetchCategory', () => {
    it('should fetch facts for a specific category', async () => {
      const mockCategory: CategoryResponse = {
        facts: [
          { id: '1', fact: 'Use strong passwords', category: 'security', created_at: '2025-04-12T10:00:00Z', updated_at: '2025-04-12T10:00:00Z' },
        ],
      }

      const response = mockApiResponse(mockCategory)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<CategoryResponse>(mockCategory)

      const { fetchCategory } = useKnowledgeBase()
      const result = await fetchCategory('security')

      expect(result).toEqual(mockCategory)
      expect(apiClient.get).toHaveBeenCalledWith('/knowledge_base/knowledge_base/category/security')
    })

    it('should throw error for invalid category', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(null)

      const { fetchCategory } = useKnowledgeBase()

      await expect(fetchCategory('nonexistent')).rejects.toThrow('Failed to fetch category')
    })
  })

  // =========================================================================
  // 3. Categorized Facts & Filtering
  // =========================================================================
  describe('getCategorizedFacts', () => {
    it('should fetch categorized facts', async () => {
      const mockCategorizedFacts: CategorizedFactsResponse = {
        total_facts: 50,
        categories: {
          security: [
            { key: '1', title: 'fact1', content: 'fact1 content', category: 'security', type: 'general', metadata: {} },
            { key: '2', title: 'fact2', content: 'fact2 content', category: 'security', type: 'general', metadata: {} },
          ],
          architecture: [
            { key: '3', title: 'fact3', content: 'fact3 content', category: 'architecture', type: 'general', metadata: {} },
          ],
        },
      }

      const response = mockApiResponse(mockCategorizedFacts)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<CategorizedFactsResponse>(mockCategorizedFacts)

      const { getCategorizedFacts } = useKnowledgeBase()
      const result = await getCategorizedFacts()

      expect(result).toEqual(mockCategorizedFacts)
      expect(result.total_facts).toBe(50)
      expect(Object.keys(result.categories).length).toBe(2)
    })

    it('should respect category filter parameter', async () => {
      const mockCategorizedFacts: CategorizedFactsResponse = {
        total_facts: 2,
        categories: {
          security: [
            {
              key: '1',
              title: 'fact1',
              content: 'fact1',
              category: 'security',
              type: 'general',
              metadata: {},
            },
          ],
        },
      }

      const response = mockApiResponse(mockCategorizedFacts)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<CategorizedFactsResponse>(mockCategorizedFacts)

      const { getCategorizedFacts } = useKnowledgeBase()
      await getCategorizedFacts('security', 100)

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringContaining('category=security')
      )
    })

    it('should throw error for invalid response format', async () => {
      // Intentionally malformed — `categories` is missing so the runtime
      // validator rejects the response. Typed as `unknown` because the
      // shape is deliberately non-conforming.
      const invalidResponse: unknown = { total_facts: 0, noCategoriesField: {} }

      const response = mockApiResponse(invalidResponse)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<unknown>(invalidResponse)

      const { getCategorizedFacts } = useKnowledgeBase()

      await expect(getCategorizedFacts()).rejects.toThrow('Invalid categorized facts response format')
    })
  })

  describe('buildCategoryFilterOptions', () => {
    it('should build filter options from categorized facts', () => {
      const categorizedFacts: CategorizedFactsResponse = {
        total_facts: 5,
        categories: {
          security: [
            { key: '1', title: 'f1', content: 'fact1', category: 'security', type: 'general', metadata: {} },
            { key: '2', title: 'f2', content: 'fact2', category: 'security', type: 'general', metadata: {} },
          ],
          architecture: [
            { key: '3', title: 'f3', content: 'fact3', category: 'architecture', type: 'general', metadata: {} },
          ],
        },
      }

      const { buildCategoryFilterOptions } = useKnowledgeBase()
      const options = buildCategoryFilterOptions(categorizedFacts)

      expect(options.length).toBe(3)
      expect(options[0].label).toBe('All Categories')
      expect(options[0].value).toBe(null)
      expect(options[0].count).toBe(5)
    })

    it('should sort options by count descending', () => {
      const categorizedFacts: CategorizedFactsResponse = {
        total_facts: 6,
        categories: {
          small: [
            { key: '1', title: 'f1', content: 'fact1', category: 'small', type: 'general', metadata: {} },
          ],
          big: [
            { key: '2', title: 'f2', content: 'fact2', category: 'big', type: 'general', metadata: {} },
            { key: '3', title: 'f3', content: 'fact3', category: 'big', type: 'general', metadata: {} },
            { key: '4', title: 'f4', content: 'fact4', category: 'big', type: 'general', metadata: {} },
          ],
        },
      }

      const { buildCategoryFilterOptions } = useKnowledgeBase()
      const options = buildCategoryFilterOptions(categorizedFacts)

      // First should be "All Categories"
      expect(options[0].value).toBe(null)
      // Rest should be sorted by count (big before small)
      expect(options[1].count).toBeGreaterThanOrEqual(options[2].count)
    })
  })

  // =========================================================================
  // 4. Search Operations
  // =========================================================================
  describe('searchKnowledge', () => {
    it('should perform basic keyword search', async () => {
      const mockSearchResult: SearchResponse = {
        results: [
          { id: '1', fact: 'matching fact', similarity_score: 0.95 },
        ],
        total_results: 1,
      }

      const response = mockApiResponse(mockSearchResult)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<SearchResponse>(mockSearchResult)

      const { searchKnowledge } = useKnowledgeBase()
      const result = await searchKnowledge('test query')

      expect(result).toEqual(mockSearchResult)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/search',
        { query: 'test query' }
      )
    })

    it('should throw error when search fails', async () => {
      vi.mocked(apiClient.post).mockResolvedValue(null)

      const { searchKnowledge } = useKnowledgeBase()

      await expect(searchKnowledge('test')).rejects.toThrow('Search failed')
    })
  })

  describe('advancedSearch', () => {
    it('should perform advanced search with all options', async () => {
      const mockResults: SearchResponse = {
        results: [{ id: '1', fact: 'semantic match', similarity_score: 0.98 }],
        total_results: 1,
      }

      const response = mockApiResponse(mockResults)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<SearchResponse>(mockResults)

      const { advancedSearch } = useKnowledgeBase()
      const result = await advancedSearch({
        query: 'test',
        mode: 'semantic',
        enable_rag: true,
        category: 'security',
        top_k: 10,
      })

      expect(result).toEqual(mockResults)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/search',
        expect.objectContaining({
          query: 'test',
          mode: 'semantic',
          enable_rag: true,
          category: 'security',
        })
      )
    })

    it('should support hybrid search mode', async () => {
      const mockResults: SearchResponse = { results: [], total_results: 0 }

      const response = mockApiResponse(mockResults)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<SearchResponse>(mockResults)

      const { advancedSearch } = useKnowledgeBase()
      await advancedSearch({
        query: 'test',
        mode: 'hybrid',
        enable_reranking: true,
      })

      expect(apiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          mode: 'hybrid',
          enable_reranking: true,
        })
      )
    })
  })

  // =========================================================================
  // 5. Fact Management
  // =========================================================================
  describe('addFact', () => {
    it('should add a new fact to knowledge base', async () => {
      const mockAddResponse: AddFactResponse = {
        success: true,
        fact_id: 'fact-123',
        fact: {
          id: 'fact-123',
          fact: 'New security fact',
          category: 'security',
          created_at: '2025-04-12T10:00:00Z',
          updated_at: '2025-04-12T10:00:00Z',
        },
      }

      const response = mockApiResponse(mockAddResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<AddFactResponse>(mockAddResponse)

      const { addFact } = useKnowledgeBase()
      const result = await addFact({
        content: 'New security fact',
        category: 'security',
      })

      expect(result).toEqual(mockAddResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/facts',
        expect.objectContaining({
          content: 'New security fact',
          category: 'security',
        })
      )
    })

    it('should add fact with metadata', async () => {
      const mockAddResponse: AddFactResponse = {
        success: true,
        fact_id: 'fact-456',
        fact: {
          id: 'fact-456',
          fact: 'Fact with metadata',
          category: 'architecture',
          created_at: '2025-04-12T10:00:00Z',
          updated_at: '2025-04-12T10:00:00Z',
        },
      }

      const response = mockApiResponse(mockAddResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<AddFactResponse>(mockAddResponse)

      const { addFact } = useKnowledgeBase()
      const result = await addFact({
        content: 'Fact with metadata',
        category: 'architecture',
        metadata: { source: 'manual', priority: 'high' },
      })

      expect(result.success).toBe(true)
    })
  })

  // =========================================================================
  // 6. File Upload
  // =========================================================================
  describe('uploadKnowledgeFile', () => {
    it('should upload a knowledge file successfully', async () => {
      const mockUploadResponse: UploadResponse = {
        success: true,
        file_path: '/uploads/test.pdf',
        facts_added: 5,
      }

      const formData = new FormData()
      formData.append('file', new Blob(['test'], { type: 'application/pdf' }))

      const response = mockApiResponse(mockUploadResponse)
      vi.mocked(fetchWithAuth).mockResolvedValue(response)
      mockParseApi<UploadResponse>(mockUploadResponse)

      const { uploadKnowledgeFile } = useKnowledgeBase()
      const result = await uploadKnowledgeFile(formData)

      expect(result).toEqual(mockUploadResponse)
      expect(fetchWithAuth).toHaveBeenCalled()
    })

    it('should throw error on upload failure', async () => {
      const formData = new FormData()

      const response = mockApiResponse<null>(null, false)
      vi.mocked(fetchWithAuth).mockResolvedValue(response)

      const { uploadKnowledgeFile } = useKnowledgeBase()

      await expect(uploadKnowledgeFile(formData)).rejects.toThrow('Upload failed')
    })
  })

  // =========================================================================
  // 7. Machine Profiles & Man Pages
  // =========================================================================
  describe('fetchMachineProfiles', () => {
    it('should fetch all machine profiles', async () => {
      const mockProfiles: MachineProfile[] = [
        { machine_id: 'host1', os_type: 'linux', distro: 'Ubuntu' },
        { machine_id: 'host2', os_type: 'linux', distro: 'CentOS' },
      ]

      const response = mockApiResponse(mockProfiles)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<MachineProfile[]>(mockProfiles)

      const { fetchMachineProfiles } = useKnowledgeBase()
      const result = await fetchMachineProfiles()

      expect(result).toEqual(mockProfiles)
      expect(Array.isArray(result)).toBe(true)
    })

    it('should return empty array on error', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(null)

      const { fetchMachineProfiles } = useKnowledgeBase()
      const result = await fetchMachineProfiles()

      expect(result).toEqual([])
    })
  })

  describe('fetchManPagesSummary', () => {
    it('should fetch man pages summary', async () => {
      const mockSummary: ManPagesSummary = {
        status: 'ready',
        successful: 150,
        processed: 150,
        current_man_page_files: 1500,
      }

      const response = mockApiResponse(mockSummary)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<ManPagesSummary>(mockSummary)

      const { fetchManPagesSummary } = useKnowledgeBase()
      const result = await fetchManPagesSummary()

      expect(result).toEqual(mockSummary)
      expect(result?.status).toBe('ready')
    })

    it('should return null on error', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(null)

      const { fetchManPagesSummary } = useKnowledgeBase()
      const result = await fetchManPagesSummary()

      expect(result).toBe(null)
    })
  })

  // =========================================================================
  // 8. Vectorization
  // =========================================================================
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

      const response = mockApiResponse(mockVectorizationResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<VectorizationResponse>(mockVectorizationResponse)

      const { vectorizeFacts } = useKnowledgeBase()
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

      const response = mockApiResponse(mockResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<VectorizationResponse>(mockResponse)

      const { vectorizeFacts } = useKnowledgeBase()
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

      const response = mockApiResponse(mockStatus)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<VectorizationStatusResponse>(mockStatus)

      const { getVectorizationStatus } = useKnowledgeBase()
      const result = await getVectorizationStatus()

      expect(result).toEqual(mockStatus)
      expect(result.status).toBe('in_progress')
    })
  })

  // =========================================================================
  // 9. Background Job Operations
  // =========================================================================
  describe('pollJobStatus', () => {
    it('should poll job status successfully', async () => {
      const mockJobStatus: JobStatus = {
        task_id: 'task-123',
        status: 'SUCCESS',
        result: { processed: 100 },
      }

      const response = mockApiResponse(mockJobStatus)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<JobStatus>(mockJobStatus)

      const { pollJobStatus } = useKnowledgeBase()
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

        const response = mockApiResponse(mockJobStatus)
        vi.mocked(apiClient.get).mockResolvedValue(response)
        mockParseApi<JobStatus>(mockJobStatus)

        const { pollJobStatus } = useKnowledgeBase()
        const result = await pollJobStatus('task-123')

        expect(result.status).toBe(status)
      }
    })
  })

  describe('initializeMachineKnowledge', () => {
    it('should initialize machine knowledge', async () => {
      const mockResponse: MachineKnowledgeResponse = {
        status: 'success',
        message: 'Machine knowledge initialized',
        machine_id: 'host1',
        facts_added: 50,
      }

      const response = mockApiResponse(mockResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<MachineKnowledgeResponse>(mockResponse)

      const { initializeMachineKnowledge } = useKnowledgeBase()
      const result = await initializeMachineKnowledge('host1')

      expect(result).toEqual(mockResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/machine_knowledge/initialize',
        { machine_id: 'host1' }
      )
    })
  })

  describe('refreshSystemKnowledge', () => {
    it('should trigger system knowledge refresh and return task_id', async () => {
      const mockResponse: SystemKnowledgeResponse = {
        status: 'queued',
        message: 'System knowledge refresh queued',
        total_machines: 3,
      }

      const response = mockApiResponse(mockResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<SystemKnowledgeResponse>(mockResponse)

      const { refreshSystemKnowledge } = useKnowledgeBase()
      const result = await refreshSystemKnowledge()

      expect(result).toEqual(mockResponse)
      expect(result.status).toBe('queued')
    })
  })

  // =========================================================================
  // 10. Icon & Formatting Helpers
  // =========================================================================
  describe('getCategoryIcon', () => {
    it('should return correct icon for security category', () => {
      const { getCategoryIcon } = useKnowledgeBase()
      const icon = getCategoryIcon('security')

      expect(icon).toBe('fas fa-shield-alt')
    })

    it('should return correct icon for architecture category', () => {
      const { getCategoryIcon } = useKnowledgeBase()
      const icon = getCategoryIcon('architecture')

      expect(icon).toBe('fas fa-drafting-compass')
    })

    it('should return correct icon for devops category', () => {
      const { getCategoryIcon } = useKnowledgeBase()
      const icon = getCategoryIcon('devops')

      expect(icon).toBe('fas fa-cogs')
    })

    it('should return default folder icon for unknown category', () => {
      const { getCategoryIcon } = useKnowledgeBase()
      const icon = getCategoryIcon('unknown')

      expect(icon).toBe('fas fa-folder')
    })

    it('should handle case-insensitive matching', () => {
      const { getCategoryIcon } = useKnowledgeBase()
      const upper = getCategoryIcon('SECURITY')
      const mixed = getCategoryIcon('SeCuRiTy')

      expect(upper).toBe('fas fa-shield-alt')
      expect(mixed).toBe('fas fa-shield-alt')
    })
  })

  describe('getTypeIcon', () => {
    it('should return PDF icon for PDF documents', () => {
      const { getTypeIcon } = useKnowledgeBase()
      const icon = getTypeIcon('pdf')

      expect(icon).toBe('fas fa-file-pdf')
    })

    it('should return code icon for JSON types', () => {
      const { getTypeIcon } = useKnowledgeBase()
      const icon = getTypeIcon('json')

      expect(icon).toBe('fas fa-file-code')
    })

    it('should return image icon for image types', () => {
      const { getTypeIcon } = useKnowledgeBase()
      expect(getTypeIcon('png')).toBe('fas fa-file-image')
      expect(getTypeIcon('jpg')).toBe('fas fa-file-image')
    })

    it('should return default file icon for unknown type', () => {
      const { getTypeIcon } = useKnowledgeBase()
      const icon = getTypeIcon('unknown')

      expect(icon).toBe('fas fa-file')
    })
  })

  describe('getFileIcon', () => {
    it('should return folder icon for directories', () => {
      const { getFileIcon } = useKnowledgeBase()
      const icon = getFileIcon('mydir', true)

      expect(icon).toContain('fas fa-folder')
    })

    it('should return styled icon for file with color class', () => {
      const { getFileIcon } = useKnowledgeBase()
      const icon = getFileIcon('script.js', false)

      expect(icon).toContain('text-')
    })

    it('should apply different colors for different file types', () => {
      const { getFileIcon } = useKnowledgeBase()
      const jsIcon = getFileIcon('app.js', false)
      const pyIcon = getFileIcon('script.py', false)
      const pdfIcon = getFileIcon('document.pdf', false)

      // Different colors for different types
      expect(jsIcon).not.toEqual(pyIcon)
      expect(pyIcon).not.toEqual(pdfIcon)
    })
  })

  describe('getOSBadgeClass', () => {
    it('should return success class for Linux', () => {
      const { getOSBadgeClass } = useKnowledgeBase()
      const badgeClass = getOSBadgeClass('linux')

      expect(badgeClass).toBe('badge-success')
    })

    it('should return info class for Windows', () => {
      const { getOSBadgeClass } = useKnowledgeBase()
      const badgeClass = getOSBadgeClass('windows')

      expect(badgeClass).toBe('badge-info')
    })

    it('should return warning class for macOS', () => {
      const { getOSBadgeClass } = useKnowledgeBase()
      const badgeClass = getOSBadgeClass('macos')

      expect(badgeClass).toBe('badge-warning')
    })

    it('should return secondary class for unknown OS', () => {
      const { getOSBadgeClass } = useKnowledgeBase()
      const badgeClass = getOSBadgeClass('unknown')

      expect(badgeClass).toBe('badge-secondary')
    })
  })

  describe('getMessageIcon', () => {
    it('should return info icon for info type', () => {
      const { getMessageIcon } = useKnowledgeBase()
      const icon = getMessageIcon('info')

      expect(icon).toContain('fas fa-info-circle')
      expect(icon).toContain('text-blue-500')
    })

    it('should return success icon for success type', () => {
      const { getMessageIcon } = useKnowledgeBase()
      const icon = getMessageIcon('success')

      expect(icon).toContain('fas fa-check-circle')
      expect(icon).toContain('text-green-500')
    })

    it('should return warning icon for warning type', () => {
      const { getMessageIcon } = useKnowledgeBase()
      const icon = getMessageIcon('warning')

      expect(icon).toContain('fas fa-exclamation-triangle')
      expect(icon).toContain('text-yellow-500')
    })

    it('should return error icon for error type', () => {
      const { getMessageIcon } = useKnowledgeBase()
      const icon = getMessageIcon('error')

      expect(icon).toContain('fas fa-times-circle')
      expect(icon).toContain('text-red-500')
    })

    it('should default to info icon for unknown type', () => {
      const { getMessageIcon } = useKnowledgeBase()
      const icon = getMessageIcon('unknown')

      expect(icon).toContain('fas fa-info-circle')
    })
  })

  describe('formatTime', () => {
    it('should format timestamp to locale time string', () => {
      const { formatTime } = useKnowledgeBase()
      const timestamp = '2025-04-12T10:30:45Z'
      const formatted = formatTime(timestamp)

      expect(typeof formatted).toBe('string')
      expect(formatted).toMatch(/\d{1,2}:\d{2}:\d{2}/)
    })

    it('should handle Date objects', () => {
      const { formatTime } = useKnowledgeBase()
      const date = new Date('2025-04-12T10:30:45Z')
      const formatted = formatTime(date)

      expect(typeof formatted).toBe('string')
    })
  })

  // =========================================================================
  // 11. Additional Machine & Docs Operations
  // =========================================================================
  describe('populateManPages', () => {
    it('should populate man pages for a machine', async () => {
      const mockResponse: ManPagesPopulateResponse = {
        status: 'success',
        message: 'Man pages populated',
        machine_id: 'host1',
        man_pages_added: 150,
      }

      const response = mockApiResponse(mockResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<ManPagesPopulateResponse>(mockResponse)

      const { populateManPages } = useKnowledgeBase()
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

      const response = mockApiResponse(mockResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<AutoBotDocsResponse>(mockResponse)

      const { populateAutoBotDocs } = useKnowledgeBase()
      const result = await populateAutoBotDocs()

      expect(result).toEqual(mockResponse)
    })
  })

  describe('fetchMachineProfile', () => {
    it('should fetch profile for specific machine', async () => {
      const mockProfile: MachineProfile = {
        machine_id: 'host1',
        os_type: 'linux',
        distro: 'Ubuntu 20.04',
      }

      const response = mockApiResponse(mockProfile)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<MachineProfile>(mockProfile)

      const { fetchMachineProfile } = useKnowledgeBase()
      const result = await fetchMachineProfile('host1')

      expect(result).toEqual(mockProfile)
      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringContaining('machine_id=host1')
      )
    })

    it('should return null on error', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(null)

      const { fetchMachineProfile } = useKnowledgeBase()
      const result = await fetchMachineProfile('host1')

      expect(result).toBe(null)
    })
  })

  describe('fetchBasicStats', () => {
    it('should fetch basic statistics', async () => {
      const mockStats: KnowledgeStats = {
        total_facts: 75,
        total_documents: 3,
      }

      const response = mockApiResponse(mockStats)
      vi.mocked(apiClient.get).mockResolvedValue(response)
      mockParseApi<KnowledgeStats>(mockStats)

      const { fetchBasicStats } = useKnowledgeBase()
      const result = await fetchBasicStats()

      expect(result).toEqual(mockStats)
      expect(apiClient.get).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/stats/basic'
      )
    })
  })

  // =========================================================================
  // 12. Integration & Man Pages
  // =========================================================================
  describe('integrateManPages', () => {
    it('should integrate man pages for a machine', async () => {
      const mockResponse: IntegrationResponse = {
        status: 'queued',
        message: 'Man pages integration queued',
        machine_id: 'host1',
      }

      const response = mockApiResponse(mockResponse)
      vi.mocked(apiClient.post).mockResolvedValue(response)
      mockParseApi<IntegrationResponse>(mockResponse)

      const { integrateManPages } = useKnowledgeBase()
      const result = await integrateManPages('host1')

      expect(result).toEqual(mockResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/man_pages/integrate',
        { machine_id: 'host1' }
      )
    })
  })

  // =========================================================================
  // 13. Export Verification
  // =========================================================================
  describe('composable exports', () => {
    it('should export all API call methods', () => {
      const composable = useKnowledgeBase()

      // API methods
      expect(typeof composable.fetchStats).toBe('function')
      expect(typeof composable.fetchCategories).toBe('function')
      expect(typeof composable.fetchCategory).toBe('function')
      expect(typeof composable.searchKnowledge).toBe('function')
      expect(typeof composable.advancedSearch).toBe('function')
      expect(typeof composable.addFact).toBe('function')
      expect(typeof composable.uploadKnowledgeFile).toBe('function')
      expect(typeof composable.vectorizeFacts).toBe('function')
      expect(typeof composable.pollJobStatus).toBe('function')
    })

    it('should export all helper functions', () => {
      const composable = useKnowledgeBase()

      // Helper functions
      expect(typeof composable.getCategoryIcon).toBe('function')
      expect(typeof composable.getTypeIcon).toBe('function')
      expect(typeof composable.getFileIcon).toBe('function')
      expect(typeof composable.getOSBadgeClass).toBe('function')
      expect(typeof composable.getMessageIcon).toBe('function')
      expect(typeof composable.formatTime).toBe('function')
    })

    it('should export formatting functions from shared utilities', () => {
      const composable = useKnowledgeBase()

      // Formatting aliases
      expect(typeof composable.formatDate).toBe('function')
      expect(typeof composable.formatCategory).toBe('function')
      expect(typeof composable.formatFileSize).toBe('function')
    })
  })
})