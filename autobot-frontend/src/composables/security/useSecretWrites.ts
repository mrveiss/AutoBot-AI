// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * One write path for every secrets screen (#20732): the user-secret list and the
 * SYSTEM-vault panel delete, save and transfer through the same rules.
 *
 * - A delete the backend refuses because something still uses the secret (409
 *   `secret_has_dependents`) lists those dependents in a second confirm before forcing it; the
 *   forced delete echoes the listing's digest, so a dependent registered after the person saw
 *   the list is refused again with the new list (#21039).
 * - A failed write's outcome is unconfirmed (it may have been refused, or applied with the
 *   response lost), so it sets `writeFailed` and the screen reloads what is stored.
 * - A declined confirmation is not a change: no reload, no alert.
 */

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { isHttpError } from '@autobot/ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { secretsApiClient } from '@/utils/SecretsApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useSecretWrites')

export interface DeletableSecret {
  id: string
  name: string
  chat_id?: string | null
}

/** How a write ended: applied, declined at a confirmation, or failed with an unconfirmed outcome. */
export type WriteOutcome = 'done' | 'declined' | 'failed'

interface Dependent {
  dependent_kind: string
  dependent_id: string
}

interface DependentsRefusal {
  dependents: Dependent[]
  digest?: string
}

/** The dependents (and their digest) the backend refused the delete for (409), or null for any other error (#20557). */
export function refusalOf(error: unknown): DependentsRefusal | null {
  if (!isHttpError(error) || error.status !== 409) return null
  const detail = error.details?.detail as
    | { code?: string; dependents?: Dependent[]; dependents_digest?: string }
    | undefined
  if (detail?.code !== 'secret_has_dependents') return null
  return { dependents: detail.dependents ?? [], digest: detail.dependents_digest }
}

export function useSecretWrites() {
  const { t } = useI18n()
  const { confirm } = useConfirmDialog()
  const writeFailed = ref(false)

  /** Ask the person to confirm the listed dependents. */
  function confirmDependents(secret: DeletableSecret, dependents: Dependent[]): Promise<boolean> {
    const listed = dependents.map((d) => `${d.dependent_kind}:${d.dependent_id}`).join(', ')
    return confirm({
      title: t('security.secretsManager.dependentsTitle'),
      message: t('security.secretsManager.dependentsMessage', { name: secret.name, dependents: listed })
    })
  }

  /**
   * Delete; when dependents still use the secret, confirm the listed set before forcing it. The forced
   * delete carries that listing's digest, so a set that changed meanwhile is listed and confirmed again.
   * `false` = declined.
   */
  async function deleteConfirmingDependents(secret: DeletableSecret): Promise<unknown> {
    let dependentsDigest: string | undefined
    for (;;) {
      try {
        return await secretsApiClient.deleteSecret(secret.id, { chatId: secret.chat_id, dependentsDigest })
      } catch (error) {
        const refusal = refusalOf(error)
        if (!refusal?.digest) throw error
        if (!(await confirmDependents(secret, refusal.dependents))) return false
        dependentsDigest = refusal.digest
      }
    }
  }

  /** Run one write; an action resolving `false` was declined, so nothing changed. */
  async function runWrite(label: string, action: () => Promise<unknown>): Promise<WriteOutcome> {
    writeFailed.value = false
    try {
      return (await action()) === false ? 'declined' : 'done'
    } catch (error) {
      logger.error(`Secret ${label} failed:`, error)
      writeFailed.value = true
      return 'failed'
    }
  }

  return { writeFailed, runWrite, deleteConfirmingDependents }
}
