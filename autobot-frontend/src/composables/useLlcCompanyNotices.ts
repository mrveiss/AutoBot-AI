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
 * Identical type+agent events inside `LLC_NOTICE_DEDUPE_MS`
 * collapse into one toast so a burst cannot stack sticky toasts.
 *
 * The router publishes to every member of the company; #20885 will filter by
 * recipient, after which this composable needs no change.
 */
import { onUnmounted, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEventBus } from '@/composables/useEventBus'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { getEnvPositiveInt } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'
import type { LiveEvent } from '@/services/LiveEventService'

const logger = createLogger('useLlcCompanyNotices')

/** Dedupe window (ms) for identical type+agent notices; env VITE_LLC_NOTICE_DEDUPE_MS, default 30 s. */
export const LLC_NOTICE_DEDUPE_MS = getEnvPositiveInt(
  import.meta.env,
  'VITE_LLC_NOTICE_DEDUPE_MS',
  30000,
)

type NoticeLevel = 'info' | 'warning' | 'error'

interface NoticeSpec {
  key: string
  level: NoticeLevel
}

const IGNORED_EVENTS = new Set(['heartbeat_ok', 'llc:activity_created'])

/** Notices whose text names an agent; each has a `<key>NoAgent` fallback. */
const AGENT_NOTICE_KEYS = new Set([
  'llc.notices.heartbeatMissed',
  'llc.notices.heartbeatRecoveryUnfiled',
  'llc.notices.agentPaused',
  'llc.notices.agentResumed',
])

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

/** Per-composable window: true when this type+agent already toasted recently. */
export function createNoticeDeduper(windowMs: number, now: () => number = Date.now) {
  const last = new Map<string, number>()
  return (type: string, agent: string): boolean => {
    const key = `${type}|${agent}`
    const t = now()
    const prev = last.get(key)
    if (prev !== undefined && t - prev < windowMs) return true
    last.set(key, t)
    return false
  }
}

export function useLlcCompanyNotices(companyId: Ref<string | null | undefined>): void {
  const { t } = useI18n()
  const live = useEventBus()
  const bus = useNotificationBus()
  const isDuplicate = createNoticeDeduper(LLC_NOTICE_DEDUPE_MS)
  const notify: Record<NoticeLevel, (message: string) => void> = {
    info: bus.notifyInfo,
    warning: bus.notifyWarning,
    error: bus.notifyError,
  }

  function onEvent(ev: LiveEvent): void {
    const notice = resolveNotice(ev)
    if (!notice) return
    const type = String(ev.event_type)
    const agent = String(ev.payload?.agent_id ?? '')
    if (isDuplicate(type, agent)) return
    logger.debug('company notice', type)
    const key = !agent && AGENT_NOTICE_KEYS.has(notice.key) ? `${notice.key}NoAgent` : notice.key
    notify[notice.level](t(key, { agent }))
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
