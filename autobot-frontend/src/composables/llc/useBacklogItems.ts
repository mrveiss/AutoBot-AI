// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The backlog list of one company, optionally narrowed to a project by the server (#17680).
// `fetchBacklog` says whether the list was refreshed, so a caller can tell the user when it was not (#20930).
// Only the LATEST request may write the list, `isLoading` and `loadFailed` (#21032): a superseded company or
// project response must not overwrite the newer list, and its end must not clear the newer request's spinner.
import { ref, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import type { WorkItem } from '@/views/llc/workItemTypes'

const logger = createLogger('useBacklogItems')

export function useBacklogItems(companyId: Readonly<Ref<string>>, projectFilterId: Readonly<Ref<string>>) {
  const api = useApiClient()
  const items = ref<WorkItem[]>([])
  const isLoading = ref(false)
  // A failed load is its own state, never "No items match": the list on screen is not the server's answer.
  const loadFailed = ref(false)
  let loadedFor = ''
  let latest = 0

  function backlogUrl(): string {
    // `GET /api/llc/backlog` honours `project_id`; sending `company_id` alone listed the whole company (#17680).
    const query = new URLSearchParams({ company_id: companyId.value })
    if (projectFilterId.value) query.set('project_id', projectFilterId.value)
    return `/api/llc/backlog?${query.toString()}`
  }

  /** True when the list was refreshed. A superseded request answers true: the newer one reports its own outcome. */
  async function fetchBacklog(): Promise<boolean> {
    const seq = ++latest
    const company = companyId.value
    isLoading.value = true
    loadFailed.value = false
    try {
      const result = await api.get<{ items: WorkItem[] }>(backlogUrl())
      if (seq !== latest) return true
      items.value = result.items ?? []
      loadedFor = company
      return true
    } catch (err) {
      logger.error('Failed to load backlog', err)
      if (seq !== latest) return true
      loadFailed.value = true
      if (loadedFor !== company) items.value = [] // never show another company's rows under a failure
      return false
    } finally {
      if (seq === latest) isLoading.value = false
    }
  }

  return { items, isLoading, loadFailed, fetchBacklog }
}
