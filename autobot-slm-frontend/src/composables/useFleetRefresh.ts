// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Re-read the fleet's node list and say so when the list shown is not the whole fleet (#21584).
 *
 * `fleetStore.fetchNodes` keeps the nodes it did read when a later page fails; this is where the
 * operator is told, so a shorter list is never presented as the whole fleet.
 */

import { useI18n } from 'vue-i18n'
import { createLogger, useToast } from '@autobot/ui'
import { useFleetStore } from '@/stores/fleet'
import { PartialListError } from '@/utils/fetchAllPages'

const logger = createLogger('useFleetRefresh')

export function useFleetRefresh() {
  const { t } = useI18n()
  const { showToast } = useToast()
  const fleetStore = useFleetStore()

  async function refreshFleet(): Promise<void> {
    try {
      await fleetStore.fetchNodes()
    } catch (err) {
      logger.error('Failed to refresh fleet:', err)
      if (err instanceof PartialListError) {
        showToast(t('fleetOverview.incompleteList', { loaded: err.items.length, total: err.total, message: err.reason }), 'error')
      }
    }
  }

  return { refreshFleet }
}
