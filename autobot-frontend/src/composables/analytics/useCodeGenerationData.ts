// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useCodeGenerationData
 *
 * Encapsulates all fetchWithAuth calls for the Code Generation Dashboard.
 * Extracted from CodeGenerationDashboard.vue (Issue #6060).
 *
 * Migrated from raw fetchWithAuth to useFetchEndpoint / useApi (#6152) for
 * AbortController, race protection, and consistent error handling.
 *
 * Endpoints (all under /api/code-generation/*):
 *   POST GET  /code-generation/generate
 *   POST      /code-generation/refactor
 *   POST      /code-generation/validate
 *   GET       /code-generation/stats
 *   GET       /code-generation/refactoring-types
 */

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useApiClient } from '@/plugins/api'
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

interface RefactoringTypesRaw {
  types?: RefactoringType[]
}

export function useCodeGenerationData(withSourceId: (url: string) => string) {
  const api = useApiClient()

  // GET: /code-generation/stats — scoped to source via withSourceId (#3436)
  const statsEndpoint = useFetchEndpoint<CodeGenerationStats, CodeGenerationStats>(
    {
      path: '/api/code-generation/stats',
      scopeToSource: true,
      pickData: (raw) => raw,
      onError: (_message, err) => {
        logger.error('Failed to fetch stats:', err)
      },
      label: 'Code generation stats',
    },
    { withSourceId },
  )

  // GET: /code-generation/refactoring-types
  const refactoringTypesEndpoint = useFetchEndpoint<RefactoringTypesRaw, RefactoringType[]>(
    {
      path: '/api/code-generation/refactoring-types',
      pickData: (raw) => raw.types ?? [],
      onError: (_message, err) => {
        logger.error('Failed to fetch refactoring types:', err)
      },
      label: 'Refactoring types',
    },
  )

  async function generateCode(request: GenerateRequest): Promise<GenerationResult | null> {
    try {
      return await api.post<GenerationResult>('/api/code-generation/generate', request)
    } catch (err) {
      logger.error('Generation error:', err)
      return null
    }
  }

  async function refactorCode(request: RefactorRequest): Promise<GenerationResult | null> {
    try {
      return await api.post<GenerationResult>('/api/code-generation/refactor', request)
    } catch (err) {
      logger.error('Refactoring error:', err)
      return null
    }
  }

  async function validateCode(code: string, language: string): Promise<ValidationInfo | null> {
    try {
      return await api.post<ValidationInfo>('/api/code-generation/validate', { code, language })
    } catch (err) {
      logger.error('Validation error:', err)
      return null
    }
  }

  async function fetchStats(): Promise<CodeGenerationStats | null> {
    // Issue #3436: scope to project when sourceId is present
    await statsEndpoint.load()
    return statsEndpoint.data.value
  }

  async function fetchRefactoringTypes(): Promise<RefactoringType[]> {
    await refactoringTypesEndpoint.load()
    return refactoringTypesEndpoint.data.value ?? []
  }

  return {
    generateCode,
    refactorCode,
    validateCode,
    fetchStats,
    fetchRefactoringTypes,
  }
}
