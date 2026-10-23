// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Superadmin revoke of the LLM sign-in token every org may share (#19241, owner
 * decision 2026-10-23). One confirmation + DELETE /api/llm-auth/{provider}/shared
 * flow, used by the System section's shared-revoke block and by an org-less
 * admin's System row (whose system connection IS the shared token).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import type { components } from '@/types/generated/api'

type RevokeResult = components['schemas']['ProviderRevokeResult']

export interface SharedProvider {
  name: string
  label: string
}

const logger = createLogger('useSharedTokenRevoke')

export function useSharedTokenRevoke() {
  const { t } = useI18n()
  const { confirm } = useConfirmDialog()
  const busy = ref(false)
  const message = ref('')
  const isWarning = ref(false)

  function describe(p: SharedProvider, result: RevokeResult): void {
    isWarning.value = result.provider_revoked === false
    message.value = isWarning.value
      ? t('settings.providerAuth.providerRevokeFailed', { reason: result.provider_error ?? '' })
      : t('settings.providerAuth.shared.done', { provider: p.label })
  }

  /** Confirm, then revoke; resolves true when the shared token was deleted. */
  async function revokeShared(p: SharedProvider): Promise<boolean> {
    const ok = await confirm({
      title: t('settings.providerAuth.shared.confirmTitle', { provider: p.label }),
      message: t('settings.providerAuth.shared.confirmMessage', { provider: p.label }),
    })
    if (!ok) return false
    busy.value = true
    try {
      const result: RevokeResult = await ApiClient.delete(`/api/llm-auth/${p.name}/shared`)
      describe(p, result)
      return true
    } catch (err: unknown) {
      logger.error('Shared token revoke failed', err)
      isWarning.value = true
      message.value = (err as Error)?.message || t('settings.providerAuth.disconnectFailed')
      return false
    } finally {
      busy.value = false
    }
  }

  return { busy, message, isWarning, revokeShared }
}
