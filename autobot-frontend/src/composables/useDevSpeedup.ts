// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Developer Speedup Composable
 * Issue #902 - Developer Speedup Tools
 */

import { ref, onMounted } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useDevSpeedup')

// ===== Type Definitions =====

export interface SearchResult {
  type: 'file' | 'code' | 'symbol'
  path: string
  line?: number
  content: string
  context?: string
  score: number
}

export interface CodeSnippet {
  id: string
  language: string
  code: string
  description: string
  tags: string[]
  created_at: string
}

export interface CodeTemplate {
  id: string
  name: string
  description: string
  language: string
  template: string
  variables: string[]
  category: string
}

export interface RefactorSuggestion {
  type: 'extract_method' | 'rename' | 'inline' | 'simplify'
  description: string
  before: string
  after: string
  impact: 'low' | 'medium' | 'high'
  line_number?: number
}

export interface TestCase {
  name: string
  code: string
  description: string
  framework: string
}

export interface SpeedupAction {
  id: string
  action: string
  timestamp: string
  input: string
  output: string
}

export interface UseDevSpeedupOptions {
  autoFetch?: boolean
}

// ===== Composable Implementation =====

export function useDevSpeedup(options: UseDevSpeedupOptions = {}) {
  const { autoFetch = false } = options

  // State
  const searchResults = ref<SearchResult[]>([])
  const snippets = ref<CodeSnippet[]>([])
  const templates = ref<CodeTemplate[]>([])
  const refactorSuggestions = ref<RefactorSuggestion[]>([])
  const generatedTests = ref<TestCase[]>([])
  const actionHistory = ref<SpeedupAction[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ===== API Methods =====

  async function quickSearch(query: string, type?: 'file' | 'code' | 'symbol'): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/quick-search', { query, type })
      searchResults.value = data.results || []
      logger.debug('Search results:', searchResults.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to search'
      logger.error('Search failed:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function generateSnippet(description: string, language: string): Promise<CodeSnippet | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/snippet-generate', { description, language })
      const snippet = data.snippet
      snippets.value.unshift(snippet)
      logger.debug('Generated snippet:', snippet)
      return snippet
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate snippet'
      logger.error('Snippet generation failed:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTemplates(category?: string): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const params = category ? `?category=${category}` : ''
      const data = await ApiClient.get(`/api/dev-speedup/templates${params}`)
      templates.value = data.templates || []
      logger.debug('Fetched templates:', templates.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch templates'
      logger.error('Failed to fetch templates:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function suggestRefactor(code: string, language: string): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/refactor-suggest', { code, language })
      refactorSuggestions.value = data.suggestions || []
      logger.debug('Refactor suggestions:', refactorSuggestions.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to get refactor suggestions'
      logger.error('Refactor suggestions failed:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function generateBoilerplate(type: string, options: Record<string, unknown>): Promise<string | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/boilerplate', { type, ...options })
      logger.debug('Generated boilerplate')
      return data.code
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate boilerplate'
      logger.error('Boilerplate generation failed:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function generateTests(code: string, language: string, framework?: string): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/test-generate', { code, language, framework })
      generatedTests.value = data.tests || []
      logger.debug('Generated tests:', generatedTests.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate tests'
      logger.error('Test generation failed:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function optimizeCode(code: string, language: string): Promise<string | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/optimize', { code, language })
      logger.debug('Code optimized')
      return data.optimized_code
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to optimize code'
      logger.error('Code optimization failed:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function formatCode(code: string, language: string): Promise<string | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/format', { code, language })
      logger.debug('Code formatted')
      return data.formatted_code
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to format code'
      logger.error('Code formatting failed:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function lintFix(code: string, language: string): Promise<string | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/dev-speedup/lint-fix', { code, language })
      logger.debug('Linting fixed')
      return data.fixed_code
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fix linting'
      logger.error('Lint fix failed:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function fetchHistory(): Promise<void> {
    try {
      const data = await ApiClient.get('/api/dev-speedup/history')
      actionHistory.value = data.actions || []
      logger.debug('Fetched action history:', actionHistory.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch history'
      logger.error('Failed to fetch history:', err)
      error.value = message
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      Promise.all([fetchTemplates(), fetchHistory()])
    }
  })

  return {
    // State
    searchResults,
    snippets,
    templates,
    refactorSuggestions,
    generatedTests,
    actionHistory,
    isLoading,
    error,

    // Methods
    quickSearch,
    generateSnippet,
    fetchTemplates,
    suggestRefactor,
    generateBoilerplate,
    generateTests,
    optimizeCode,
    formatCode,
    lintFix,
    fetchHistory,
  }
}

export default useDevSpeedup
