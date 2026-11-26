// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * How a chat-reaching socket follows the selected company (#21997). A leaf on purpose: many specs import the
 * socket owners with partial mocks of `ssot-config` and `vue-i18n`, so the company store (which pulls both) is
 * loaded lazily, only when a switch is actually being watched.
 */
import { getActivePinia } from 'pinia'
import { getCurrentScope, onScopeDispose, watch, type WatchStopHandle } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { withCompanyScope } from '@/utils/orgContext'

export { withCompanyScope }

const logger = createLogger('companyScopedSocket')

/**
 * Run `reconnect` whenever the selected company changes, so a socket opened under the old company reopens with a
 * URL rebuilt by `withCompanyScope` (its `company_id` is fixed at connect). The one mechanism every chat-reaching
 * socket uses. A no-op until Pinia is active (a socket created before the app mounts reads the company at connect).
 * Stops with the calling effect scope, or through the returned handle.
 */
export function onCompanySwitch(reconnect: () => void): WatchStopHandle {
  if (!getActivePinia()) return () => {}
  let stop: WatchStopHandle = () => {}
  let stopped = false
  const handle = () => {
    stopped = true
    stop()
  }
  import('@/stores/useLlcCompanyStore')
    .then(({ useLlcCompanyStore }) => {
      if (stopped) return
      const store = useLlcCompanyStore()
      stop = watch(() => store.selectedCompanyId, (id, previous) => id !== previous && reconnect())
    })
    .catch((error: unknown) => logger.warn('Company switch watcher unavailable:', error))
  if (getCurrentScope()) onScopeDispose(handle)
  return handle
}
