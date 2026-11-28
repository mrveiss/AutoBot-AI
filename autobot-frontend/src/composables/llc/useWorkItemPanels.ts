// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Side-panel loads for WorkItemDetail.vue (#20068): comments (paged), artifacts, activity and the
 * handoff brief. Each panel keeps a `failed` flag so a failed load is told apart from an empty one,
 * and comments carry the route's `has_more` so an item with more than a page is not cut.
 */
import { ref, watch } from 'vue'
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
  // Bumped when the item changes: a response captured under an older generation is discarded.
  let generation = 0
  const requested = new Set<() => Promise<void>>()

  async function guarded(key: keyof typeof loading.value, what: string, run: (live: () => boolean) => Promise<void>) {
    const mine = generation
    const live = () => mine === generation
    loading.value[key] = true
    failed.value[key] = false
    try {
      await run(live)
    } catch (err) {
      if (live()) failed.value[key] = true
      logger.error(`Failed to load ${what}`, err)
    } finally {
      if (live()) loading.value[key] = false
    }
  }

  const firstComments = () => fetchComments(false)

  function fetchComments(more = false) {
    if (!more) requested.add(firstComments)
    return guarded('comments', 'comments', async (live) => {
      const url = more ? `${base()}/comments?offset=${serverOffset}` : `${base()}/comments`
      const page = await api.get<CommentsPage>(url)
      if (!live()) return
      const rows = page.comments ?? []
      serverOffset = (more ? serverOffset : 0) + rows.length
      const known = new Set(more ? comments.value.map((c) => c.id) : [])
      comments.value = [...(more ? comments.value : []), ...rows.filter((c) => !known.has(c.id))]
      hasMoreComments.value = page.has_more === true
    })
  }

  /**
   * A comment this user just posted. While later pages exist it is left out: appended here it would sit
   * ahead of older comments still to come. It shows when its own page loads (the server orders it).
   */
  function addPostedComment(forItemId: string, comment: Comment) {
    if (forItemId !== itemId() || hasMoreComments.value) return
    comments.value = [...comments.value.filter((c) => c.id !== comment.id), comment]
  }

  const fetchArtifacts = () => {
    requested.add(fetchArtifacts)
    return guarded('artifacts', 'artifacts', async (live) => {
      // GH#9851: the backend calls these work "products" and returns {products:[...]}.
      const result = await api.get<{ products: RawWorkProduct[] }>(`${base()}/products`)
      if (!live()) return
      artifacts.value = (result.products ?? []).map(toArtifact)
    })
  }

  const fetchActivity = () => {
    requested.add(fetchActivity)
    return guarded('activity', 'activity', async (live) => {
      // GH#9851: /activity returns an ActivityLogResponse ({items:[...]}).
      const result = await api.get<{ items: RawActivityEntry[] }>(`${base()}/activity`)
      if (!live()) return
      activity.value = (result.items ?? []).map(toActivityEvent)
    })
  }

  const fetchHandoffBrief = () => {
    requested.add(fetchHandoffBrief)
    return guarded('handoff', 'handoff brief', async (live) => {
      const result = await api.get<{ brief: string }>(`${base()}/handoff-brief`)
      if (!live()) return
      handoffBrief.value = result.brief ?? null
    })
  }

  // A different item: drop everything the old one loaded and fetch again whatever was being shown.
  watch(itemId, () => {
    generation += 1
    serverOffset = 0
    comments.value = []
    artifacts.value = []
    activity.value = []
    handoffBrief.value = null
    hasMoreComments.value = false
    loading.value = { comments: false, artifacts: false, activity: false, handoff: false }
    failed.value = { comments: false, artifacts: false, activity: false, handoff: false }
    const again = [...requested]
    requested.clear()
    again.forEach((load) => load())
  })

  return {
    addPostedComment,
    comments, artifacts, activity, handoffBrief, hasMoreComments, loading, failed,
    fetchComments, fetchArtifacts, fetchActivity, fetchHandoffBrief,
  }
}
