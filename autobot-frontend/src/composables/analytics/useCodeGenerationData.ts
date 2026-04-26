// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeGenerationData
 *
 * Encapsulates all fetchWithAuth calls for the Code Generation Dashboard.
 * Extracted from CodeGenerationDashboard.vue (Issue #6060).
 *
 * Endpoints (all under /api/code-generation/*):
 *   POST GET  /code-generation/generate
 *   POST      /code-generation/refactor
 *   POST      /code-generation/validate
 *   GET       /code-generation/stats
 *   GET       /code-generation/refactoring-types
 */

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCodeGenerationData')

export interface GenerateRequest {
  description: string
  language: string
  context: string
  existing_code: string
}

export interface RefactorRequest {
  code: string
  language: string
  refactoring_type: string
  preserve_comments: boolean
}

export interface ValidationInfo {
  is_valid: boolean
  errors: string[]
  warnings: string[]
  ast_info: Record<string, unknown>
}

export interface GenerationResult {
  success: boolean
  generated_code?: string
  refactored_code?: string
  diff?: string
  changes?: string[]
  validation?: ValidationInfo
  tokens_used: number
  processing_time: number
  error?: string
}

export interface CodeGenerationStats {
  generation: { total: number; success: number; tokens: number }
  refactoring: { total: number; success: number; tokens: number }
}

export interface RefactoringType {
  id: string
  name: string
  description: string
}

export function useCodeGenerationData(withSourceId: (url: string) => string) {
  async function generateCode(request: GenerateRequest): Promise<GenerationResult | null> {
    try {
      const response = await fetchWithAuth(`${getApiBase()}/code-generation/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      if (!response.ok) throw new Error('Generation failed')
      return (await response.json()) as GenerationResult
    } catch (err) {
      logger.error('Generation error:', err)
      return null
    }
  }

  async function refactorCode(request: RefactorRequest): Promise<GenerationResult | null> {
    try {
      const response = await fetchWithAuth(`${getApiBase()}/code-generation/refactor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      if (!response.ok) throw new Error('Refactoring failed')
      return (await response.json()) as GenerationResult
    } catch (err) {
      logger.error('Refactoring error:', err)
      return null
    }
  }

  async function validateCode(code: string, language: string): Promise<ValidationInfo | null> {
    try {
      const response = await fetchWithAuth(`${getApiBase()}/code-generation/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language }),
      })
      if (!response.ok) throw new Error('Validation failed')
      return (await response.json()) as ValidationInfo
    } catch (err) {
      logger.error('Validation error:', err)
      return null
    }
  }

  async function fetchStats(): Promise<CodeGenerationStats | null> {
    try {
      // Issue #3436: scope to project when sourceId is present
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/code-generation/stats`))
      if (!response.ok) {
        logger.warn('Failed to fetch stats: HTTP', response.status)
        return null
      }
      return (await response.json()) as CodeGenerationStats
    } catch (err) {
      logger.error('Failed to fetch stats:', err)
      return null
    }
  }

  async function fetchRefactoringTypes(): Promise<RefactoringType[]> {
    try {
      const response = await fetchWithAuth(`${getApiBase()}/code-generation/refactoring-types`)
      if (!response.ok) {
        logger.warn('Failed to fetch refactoring types: HTTP', response.status)
        return []
      }
      const data = await response.json()
      return (data.types as RefactoringType[]) || []
    } catch (err) {
      logger.error('Failed to fetch refactoring types:', err)
      return []
    }
  }

  return {
    generateCode,
    refactorCode,
    validateCode,
    fetchStats,
    fetchRefactoringTypes,
  }
}
