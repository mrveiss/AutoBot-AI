// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgePrompt Composable (Issue #6039)
 *
 * Centralises all HTTP I/O for the KnowledgePromptEditor component:
 *   - fetchPrompts  — GET  /api/prompts
 *   - savePrompt    — PUT  /api/prompts/:id
 *   - fetchHistory  — GET  /api/prompts/:id/history
 *   - revertPrompt  — POST /api/prompts/:id/revert
 */

import { ref } from 'vue'
import type { Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgePrompt')

// =============================================================================
// Types
// =============================================================================

export interface Prompt {
  id: string
  name: string
  category: 'system' | 'agents' | 'templates'
  content: string
  description?: string
  variables?: string[]
  lastModified?: string
  version?: number
}

export interface PromptVersion {
  version: number
  content: string
  timestamp: string
  author?: string
}

// =============================================================================
// Composable
// =============================================================================

export interface UseKnowledgePromptReturn {
  /** True while prompts list is loading. */
  isLoading: Ref<boolean>
  /** True while a save or revert mutation is in-flight. */
  isSaving: Ref<boolean>
  /** True while version history is being fetched. */
  isLoadingHistory: Ref<boolean>

  /** Fetch all prompts. Throws on network error; caller owns error display. */
  fetchPrompts: () => Promise<Prompt[]>
  /** Save updated content for a prompt. Returns the raw API response. */
  savePrompt: (id: string, content: string) => Promise<Record<string, unknown>>
  /** Fetch version history for a prompt. Returns array of versions. */
  fetchHistory: (id: string) => Promise<PromptVersion[]>
  /** Revert a prompt to a previous version. Returns the raw API response. */
  revertPrompt: (id: string, version: number) => Promise<Record<string, unknown>>
}

export function useKnowledgePrompt(): UseKnowledgePromptReturn {
  const { isLoading, wrap } = useLoadingState()
  const { isLoading: isSaving, wrap: wrapSaving } = useLoadingState()
  const isLoadingHistory = ref(false)

  const fetchPrompts = (): Promise<Prompt[]> =>
    wrap(async () => {
      const data = await apiClient.get<Record<string, unknown>>(`${getApiBase()}/prompts`)
      const prompts = (data?.prompts ?? []) as Prompt[]
      return prompts
    })

  const savePrompt = (id: string, content: string): Promise<Record<string, unknown>> =>
    wrapSaving(async () => {
      return apiClient.put<Record<string, unknown>>(
        `${getApiBase()}/prompts/${encodeURIComponent(id)}`,
        { content },
      )
    })

  const fetchHistory = async (id: string): Promise<PromptVersion[]> => {
    isLoadingHistory.value = true
    try {
      const data = await apiClient.get<Record<string, unknown>>(
        `${getApiBase()}/prompts/${encodeURIComponent(id)}/history`,
      )
      return (data?.versions ?? []) as PromptVersion[]
    } catch (err) {
      logger.error('Failed to load prompt history:', err)
      return []
    } finally {
      isLoadingHistory.value = false
    }
  }

  const revertPrompt = (id: string, version: number): Promise<Record<string, unknown>> =>
    wrapSaving(async () => {
      return apiClient.post<Record<string, unknown>>(
        `${getApiBase()}/prompts/${encodeURIComponent(id)}/revert`,
        { version },
      )
    })

  return {
    isLoading,
    isSaving,
    isLoadingHistory,
    fetchPrompts,
    savePrompt,
    fetchHistory,
    revertPrompt,
  }
}
