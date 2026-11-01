// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The knowledge upload limit, read from the backend (#19712). Checking it here is a courtesy, not the
 * enforcement: the server refuses an oversize file whole, so while the limit is unknown nothing is
 * refused in the browser.
 */
import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeUploadLimit')

export function useKnowledgeUploadLimit() {
  const maxMb = ref<number | null>(null)

  async function loadLimit(): Promise<void> {
    try {
      const data = await apiClient.get<{ max_mb: number }>(`${getApiBase()}/knowledge_base/upload/limit`)
      maxMb.value = data.max_mb
    } catch (error) {
      logger.warn('Could not read the upload limit; the server still enforces it', error)
    }
  }

  function exceedsLimit(bytes: number): boolean {
    return maxMb.value !== null && bytes > maxMb.value * 1024 * 1024
  }

  return { maxMb, loadLimit, exceedsLimit }
}
