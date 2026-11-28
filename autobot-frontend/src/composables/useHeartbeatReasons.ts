// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { useI18n } from 'vue-i18n'

/**
 * Stable reason codes the heartbeat panel sends to the backend (#21377).
 *
 * The backend stores the reason verbatim and never translates it. A translated string would freeze the
 * writer's locale into shared data, so the panel sends a code and renders it through
 * `agent.heartbeatReasons.<code>` in the viewer's locale.
 */
export const MANUAL_PAUSE_BODY = { reason: 'manual_pause_ui' } as const
export const MANUAL_WAKEUP_BODY = { priority: 0, reason: 'manual_wakeup_ui' } as const

export function useHeartbeatReasons() {
  const { t, te } = useI18n()

  /** A known reason code through its i18n key; any other value is a legacy free-text reason, shown unchanged. */
  function reasonLabel(reason: string | null): string {
    if (!reason) return '—'
    const key = `agent.heartbeatReasons.${reason}`
    return te(key) ? t(key) : reason
  }

  return { reasonLabel }
}
