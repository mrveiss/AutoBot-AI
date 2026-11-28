// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Display formatting for the Agent Activity Monitor (#17514): moved out of
 * AgentActivityVisualization.vue, which is at its size ceiling. Every visible word comes
 * from i18n; an unmeasured figure reads "not reported", never 0.
 */

import { createDateFormatter, createRecencyFormatter } from '@autobot/ui'
import type { ActivityAgent } from '@/composables/visualizations/useAgentActivityData'

type Translate = (key: string, params?: Record<string, unknown>) => string

const AGENT_ICONS: Record<string, string> = {
  orchestrator: '🎭',
  worker: '⚙️',
  monitor: '👁️',
  analyzer: '🔍',
  executor: '🚀',
}

export function agentActivityFormat(t: Translate, locale?: () => string) {
  const k = (key: string) => `visualizations.agentActivity.${key}`

  function successText(agent: ActivityAgent): string {
    if (agent.tasksCompleted == null || agent.successRate == null) return t(k('notReported'))
    return agent.tasksCompleted === 0 ? t(k('notApplicable')) : `${agent.successRate}%`
  }

  const getAgentIcon = (type: string): string => AGENT_ICONS[type] || '🤖'
  const formatAgentType = (type: string): string => t(k(`types.${type}`))

  function uptimeText(seconds: number): string {
    if (seconds < 60) return t(k('seconds'), { n: seconds })
    if (seconds < 3600) return t(k('minutes'), { n: Math.floor(seconds / 60) })
    return t(k('hours'), { n: Math.floor(seconds / 3600) })
  }

  const formatTimeAgo = createRecencyFormatter({ locale, style: 'narrow', maxUnit: 'hour', invalidText: '—' })

  const formatHourLabel = createDateFormatter({
    kind: 'time',
    locale,
    intl: { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
  })

  // #21270: six one-hour columns from the server's axis start (UTC ms); the current hours when absent.
  function timelineLabels(startMs?: number | null): string[] {
    const hourMs = 60 * 60 * 1000
    const first = startMs ?? new Date().setMinutes(0, 0, 0) - 5 * hourMs
    return Array.from({ length: 6 }, (_, i) => formatHourLabel(new Date(first + i * hourMs)))
  }

  function truncate(text: string, maxLength: number): string {
    return text.length <= maxLength ? text : text.slice(0, maxLength - 1) + '…'
  }

  return { successText, getAgentIcon, formatAgentType, formatUptime: uptimeText, formatTimeAgo, formatHourLabel, timelineLabels, truncate }
}
