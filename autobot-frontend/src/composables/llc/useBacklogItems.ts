// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The backlog list of one company, optionally narrowed to a project by the server (#17680).
// `fetchBacklog` says whether the list was refreshed, so a caller can tell the user when it was not (#20930).
import { ref, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import type { WorkItem } from '@/views/llc/workItemTypes'

const logger = createLogger('useBacklogItems')

export function useBacklogItems(companyId: Readonly<Ref<string>>, projectFilterId: Readonly<Ref<string>>) {
  const api = useApiClient()
  const items = ref<WorkItem[]>([])
  const isLoading = ref(false)

  async function fetchBacklog(): Promise<boolean> {
    isLoading.value = true
    try {
      // `GET /api/llc/backlog` honours `project_id`; sending `company_id` alone listed the whole company (#17680).
      const query = new URLSearchParams({ company_id: companyId.value })
      if (projectFilterId.value) query.set('project_id', projectFilterId.value)
      const result = await api.get<{ items: WorkItem[] }>(`/api/llc/backlog?${query.toString()}`)
      items.value = result.items ?? []
      return true
    } catch (err) {
      logger.error('Failed to load backlog', err)
      return false
    } finally {
      isLoading.value = false
    }
  }

  return { items, isLoading, fetchBacklog }
}
