// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Rollback to an earlier commit (#20214).
 *
 * The picker lists the commits the server offers (ancestors of the tracked branch, with dates and
 * subjects), `loadPreview` asks the server whether choosing one is allowed, and `start` begins the
 * rollback, which runs as the same update-all job Update Everything creates; the caller polls it
 * with `useCodeSync().getUpdateAllStatus()`.
 *
 * Every request uses `rawRequest`: a refusal (400 / 409 / 503) carries an operator-facing `detail`
 * that must reach the screen, and the convenience methods throw it away.
 */

import { ref } from 'vue'
import slmApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'
import type { UpdateAllJob } from '@/composables/useCodeSync'

const logger = createLogger('useCodeRollback')

export type RollbackCandidates = components['schemas']['RollbackCandidates']
export type RollbackCommit = components['schemas']['RollbackCommit']
export type RollbackPreview = components['schemas']['RollbackPreview']

async function readDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown } | null
    return typeof body?.detail === 'string' ? body.detail : null
  } catch {
    return null
  }
}

export function useCodeRollback() {
  const candidates = ref<RollbackCandidates | null>(null)
  const preview = ref<RollbackPreview | null>(null)
  const loading = ref(false)
  const checking = ref(false)
  const starting = ref(false)
  /** The server's operator-facing reason, when it gave one. */
  const error = ref<string | null>(null)
  /** A request failed; the screen shows `error` if set, else its own generic message. */
  const failed = ref(false)

  async function loadCandidates(): Promise<void> {
    loading.value = true
    error.value = null
    failed.value = false
    try {
      const response = await slmApiClient.rawRequest('/code-sync/rollback/candidates', { method: 'GET' })
      if (!response.ok) {
        error.value = await readDetail(response)
        failed.value = true
        return
      }
      const data: RollbackCandidates = await response.json()
      candidates.value = data
    } catch (e) {
      logger.warn('rollback candidates failed', e)
      failed.value = true
    } finally {
      loading.value = false
    }
  }

  /** Ask the server whether `commit` may be rolled back to. Sets `preview`; null when the request itself failed. */
  async function loadPreview(commit: string): Promise<RollbackPreview | null> {
    checking.value = true
    error.value = null
    preview.value = null
    try {
      const response = await slmApiClient.rawRequest('/code-sync/rollback/preview', {
        method: 'GET',
        params: { commit },
      })
      if (!response.ok) {
        error.value = await readDetail(response)
        failed.value = true
        return null
      }
      const data: RollbackPreview = await response.json()
      preview.value = data
      return data
    } catch (e) {
      logger.warn('rollback preview failed', e)
      failed.value = true
      return null
    } finally {
      checking.value = false
    }
  }

  /** Start the rollback. Returns the update-all job, or null when it was refused (see `error`). */
  async function start(commit: string): Promise<UpdateAllJob | null> {
    starting.value = true
    error.value = null
    failed.value = false
    try {
      const response = await slmApiClient.rawRequest('/code-sync/rollback', {
        method: 'POST',
        body: { commit },
      })
      if (!response.ok) {
        error.value = await readDetail(response)
        failed.value = true
        return null
      }
      const job: UpdateAllJob = await response.json()
      return job
    } catch (e) {
      logger.warn('rollback start failed', e)
      failed.value = true
      return null
    } finally {
      starting.value = false
    }
  }

  function reset(): void {
    preview.value = null
    error.value = null
    failed.value = false
  }

  return { candidates, preview, loading, checking, starting, error, failed, loadCandidates, loadPreview, start, reset }
}
