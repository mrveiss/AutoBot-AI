// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Resilient Update-All status polling (#9971 F1, #12593), extracted from
 * CodeSyncView (#20201). Adds two end states the page used to conflate with a
 * control plane restart: an authentication failure (tell the user to log in
 * again) and giving up (stop claiming to reconnect, offer a re-check).
 */

import { computed, ref, type Ref } from 'vue'
import {
  classifyUpdateAllPollError,
  isSelfUpdateReconnecting,
  UPDATE_ALL_UNAUTHENTICATED,
  type UpdateAllJob,
} from '@/composables/useCodeSync'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UpdateAllPoll')

const MAX_TRANSIENT_ERRORS = 90 // ~3 min at 2s intervals
const LOST_CONTACT_ERRORS = 30 // ~1 min before the "lost contact" banner
const FIRST_POLL_MS = 1000
const POLL_INTERVAL_MS = 2000

export type UpdateAllPollResult = UpdateAllJob | null | undefined | typeof UPDATE_ALL_UNAUTHENTICATED

export function useUpdateAllPoll(
  job: Ref<UpdateAllJob | null>,
  getStatus: () => Promise<UpdateAllPollResult>,
  onFinished: () => Promise<void>,
) {
  const polling = ref(false)
  const transientErrors = ref(0)
  const lostContact = ref(false)
  // Polling stopped after MAX_TRANSIENT_ERRORS consecutive failures (#20201).
  const gaveUp = ref(false)
  // The status endpoint answered 401: the session is gone, not the control plane.
  const authFailed = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  // Reconnecting is only true while a poll loop is still trying (#20201).
  const reconnecting = computed(
    () => !gaveUp.value && !authFailed.value && isSelfUpdateReconnecting(job.value, transientErrors.value),
  )

  function stop(): void {
    if (timer) clearTimeout(timer)
    timer = null
    polling.value = false
  }

  function clearFlags(): void {
    lostContact.value = false
    gaveUp.value = false
    authFailed.value = false
  }

  function onTransientError(): boolean {
    transientErrors.value += 1
    const decision = classifyUpdateAllPollError(transientErrors.value, LOST_CONTACT_ERRORS, MAX_TRANSIENT_ERRORS)
    if (decision === 'giveup') {
      logger.warn('Update All status polling gave up after', transientErrors.value, 'failed polls')
      lostContact.value = true
      gaveUp.value = true
      stop()
      return false
    }
    if (decision === 'lost-contact') lostContact.value = true
    return true
  }

  async function poll(): Promise<void> {
    const result = await getStatus()
    if (result === UPDATE_ALL_UNAUTHENTICATED) {
      logger.warn('Update All status poll was rejected as unauthenticated; stopping')
      authFailed.value = true
      stop()
      return
    }
    if (result === undefined) {
      if (onTransientError()) timer = setTimeout(poll, POLL_INTERVAL_MS)
      return
    }
    clearFlags()
    transientErrors.value = 0
    if (result === null) return stop() // true 404: no job ever started
    job.value = result
    if (result.status === 'running' || result.status === 'pending') {
      timer = setTimeout(poll, POLL_INTERVAL_MS)
      return
    }
    stop()
    await onFinished()
  }

  function schedule(): void {
    if (polling.value) return
    polling.value = true
    transientErrors.value = 0
    timer = setTimeout(poll, FIRST_POLL_MS)
  }

  // Re-check the update's status after giving up or an auth failure (#20201).
  function recheck(): void {
    clearFlags()
    schedule()
  }

  return { polling, transientErrors, lostContact, gaveUp, authFailed, reconnecting, schedule, stop, recheck, clearFlags }
}
