// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useLlcCompanyNotices (#21045)
 *
 * Turns Company OS router events on the `company:{id}` live channel into
 * toasts through the notification bus. Replaces the unused parallel-transport
 * `useLLCNotifications` composable.
 *
 * The router publishes to every member of the company; #20885 will filter by
 * recipient, after which this composable needs no change.
 */
import { onUnmounted, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLiveEvents } from '@/composables/useLiveEvents'
import { useNotificationBus } from '@/composables/useNotificationBus'
import type { LiveEvent } from '@/services/LiveEventService'

type NoticeLevel = 'info' | 'warning' | 'error'

interface NoticeSpec {
  key: string
  level: NoticeLevel
}

const IGNORED_EVENTS = new Set(['heartbeat_ok', 'llc:activity_created'])

const GENERIC_NOTICE: NoticeSpec = { key: 'llc.notices.generic', level: 'info' }

const EXACT_NOTICES: Record<string, NoticeSpec> = {
  heartbeat_missed: { key: 'llc.notices.heartbeatMissed', level: 'warning' },
  budget_warning_80: { key: 'llc.notices.budgetWarning80', level: 'warning' },
  budget_warning_95: { key: 'llc.notices.budgetWarning95', level: 'warning' },
  budget_exhausted: { key: 'llc.notices.budgetExhausted', level: 'error' },
  agent_paused: { key: 'llc.notices.agentPaused', level: 'info' },
  agent_resumed: { key: 'llc.notices.agentResumed', level: 'info' },
}

const PREFIX_NOTICES: Array<[string, NoticeSpec]> = [
  ['approval_', { key: 'llc.notices.approval', level: 'info' }],
  ['sprint_', { key: 'llc.notices.sprint', level: 'info' }],
]

/** Map an event to its notice, or null when the event is not user-facing. */
export function resolveNotice(ev: Pick<LiveEvent, 'event_type' | 'payload'>): NoticeSpec | null {
  const type = String(ev.event_type)
  if (IGNORED_EVENTS.has(type)) return null
  if (type === 'heartbeat_missed' && ev.payload?.reason === 'recovery_unfiled') {
    return { key: 'llc.notices.heartbeatRecoveryUnfiled', level: 'warning' }
  }
  const exact = EXACT_NOTICES[type]
  if (exact) return exact
  const prefixed = PREFIX_NOTICES.find(([prefix]) => type.startsWith(prefix))
  return prefixed ? prefixed[1] : GENERIC_NOTICE
}

export function useLlcCompanyNotices(companyId: Ref<string | null | undefined>): void {
  const { t } = useI18n()
  const live = useLiveEvents()
  const bus = useNotificationBus()
  const notify: Record<NoticeLevel, (message: string) => void> = {
    info: bus.notifyInfo,
    warning: bus.notifyWarning,
    error: bus.notifyError,
  }

  function onEvent(ev: LiveEvent): void {
    const notice = resolveNotice(ev)
    if (!notice) return
    const agent = String(ev.payload?.agent_id ?? '')
    notify[notice.level](t(notice.key, { agent, type: String(ev.event_type) }))
  }

  let unsubscribe: (() => void) | null = null
  const stop = (): void => {
    if (unsubscribe) unsubscribe()
    unsubscribe = null
  }

  watch(
    companyId,
    (id) => {
      stop()
      unsubscribe = id ? live.subscribe(`company:${id}`, onEvent) : null
    },
    { immediate: true },
  )
  onUnmounted(stop)
}
