// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Tell the operator, once, when the node list held is not the whole fleet (#21584).
 *
 * `fleetStore.fetchNodes` keeps the nodes it did read when a later page fails and records
 * `incomplete`. Every caller of `fetchNodes` (the shell, the fleet page, the deployment, backup,
 * maintenance and NPU views) therefore gets the same notice from this one place; no view carries a
 * copy. Mounted once at the shell, under the toast provider.
 */

import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@autobot/ui'
import { useFleetStore } from '@/stores/fleet'

export function useFleetIncompleteNotice(): void {
  const { t } = useI18n()
  const { showToast } = useToast()
  const fleetStore = useFleetStore()
  let announced = ''

  watch(
    () => fleetStore.incomplete,
    (incomplete) => {
      // A poll that finds the same shortfall again is not news; a different one, or a recovery, is.
      const key = incomplete ? `${incomplete.read}/${incomplete.total}` : ''
      if (key === announced) return
      announced = key
      if (!incomplete) return
      showToast(
        t('fleetOverview.incompleteList', {
          loaded: incomplete.read,
          total: incomplete.total ?? t('fleetOverview.incompleteTotalUnknown'),
          message: incomplete.reason,
        }),
        'error',
      )
    },
    { immediate: true },
  )
}
