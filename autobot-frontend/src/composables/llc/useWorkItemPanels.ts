// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Side-panel loads for WorkItemDetail.vue (#20068): comments (paged), artifacts, activity and the
 * handoff brief. Each panel keeps a `failed` flag so a failed load is told apart from an empty one,
 * and comments carry the route's `has_more` so an item with more than a page is not cut.
 */
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { toArtifact, toActivityEvent } from '@/views/llc/workItemDetailTypes'
import type { Comment, Artifact, ActivityEvent, RawWorkProduct, RawActivityEntry } from '@/views/llc/workItemDetailTypes'

const logger = createLogger('useWorkItemPanels')

export interface PanelApi {
  get<T>(url: string): Promise<T>
}

interface CommentsPage {
  comments: Comment[]
  has_more?: boolean
}

export function useWorkItemPanels(api: PanelApi, itemId: () => string) {
  const base = () => `/api/llc/work-items/${itemId()}`
  const comments = ref<Comment[]>([])
  const artifacts = ref<Artifact[]>([])
  const activity = ref<ActivityEvent[]>([])
  const handoffBrief = ref<string | null>(null)
  const hasMoreComments = ref(false)
  const loading = ref({ comments: false, artifacts: false, activity: false, handoff: false })
  const failed = ref({ comments: false, artifacts: false, activity: false, handoff: false })
  // Rows the server has sent; a locally posted comment is not one of them, so it must not shift the offset.
  let serverOffset = 0

  async function guarded(key: keyof typeof loading.value, what: string, run: () => Promise<void>) {
    loading.value[key] = true
    failed.value[key] = false
    try {
      await run()
    } catch (err) {
      failed.value[key] = true
      logger.error(`Failed to load ${what}`, err)
    } finally {
      loading.value[key] = false
    }
  }

  function fetchComments(more = false) {
    return guarded('comments', 'comments', async () => {
      const url = more ? `${base()}/comments?offset=${serverOffset}` : `${base()}/comments`
      const page = await api.get<CommentsPage>(url)
      const rows = page.comments ?? []
      serverOffset = (more ? serverOffset : 0) + rows.length
      const known = new Set(more ? comments.value.map((c) => c.id) : [])
      comments.value = [...(more ? comments.value : []), ...rows.filter((c) => !known.has(c.id))]
      hasMoreComments.value = page.has_more === true
    })
  }

  const fetchArtifacts = () =>
    guarded('artifacts', 'artifacts', async () => {
      // GH#9851: the backend calls these work "products" and returns {products:[...]}.
      const result = await api.get<{ products: RawWorkProduct[] }>(`${base()}/products`)
      artifacts.value = (result.products ?? []).map(toArtifact)
    })

  const fetchActivity = () =>
    guarded('activity', 'activity', async () => {
      // GH#9851: /activity returns an ActivityLogResponse ({items:[...]}).
      const result = await api.get<{ items: RawActivityEntry[] }>(`${base()}/activity`)
      activity.value = (result.items ?? []).map(toActivityEvent)
    })

  const fetchHandoffBrief = () =>
    guarded('handoff', 'handoff brief', async () => {
      const result = await api.get<{ brief: string }>(`${base()}/handoff-brief`)
      handoffBrief.value = result.brief ?? null
    })

  return {
    comments, artifacts, activity, handoffBrief, hasMoreComments, loading, failed,
    fetchComments, fetchArtifacts, fetchActivity, fetchHandoffBrief,
  }
}
