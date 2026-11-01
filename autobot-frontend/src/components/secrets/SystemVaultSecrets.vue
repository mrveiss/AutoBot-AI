<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  SYSTEM-vault secrets (#17099): the entries GET /api/secrets/ returns under
  `system_vault` for an admin. Metadata only -- the value is never displayed;
  rotate sends a new one to PUT /api/secrets/{id}, delete calls DELETE.
-->
<template>
  <BaseCard v-if="vault" :title="t('security.secretsManager.systemVault.title')" data-testid="system-vault">
    <BaseAlert v-if="!vault.available" variant="warning" :message="t('security.secretsManager.systemVault.unavailable')" />
    <EmptyState v-else-if="!vault.secrets.length" :title="t('security.secretsManager.systemVault.empty')" />
    <ul v-else>
      <li v-for="secret in vault.secrets" :key="secret.id" class="flex items-center gap-3 py-2">
        <span class="font-medium">{{ secret.name }}</span>
        <BaseBadge :label="secret.type" />
        <template v-if="rotatingId === secret.id">
          <BaseInput
            v-model="newValue"
            type="password"
            :placeholder="t('security.secretsManager.systemVault.newValue')"
          />
          <BaseButton size="sm" :disabled="!newValue || busy" data-testid="rotate-save" @click="rotate(secret)">
            {{ t('security.secretsManager.systemVault.save') }}
          </BaseButton>
          <BaseButton size="sm" variant="ghost" @click="cancelRotate">
            {{ t('security.secretsManager.systemVault.cancel') }}
          </BaseButton>
        </template>
        <template v-else>
          <BaseButton size="sm" variant="outline" data-testid="rotate-start" @click="startRotate(secret.id)">
            {{ t('security.secretsManager.systemVault.rotate') }}
          </BaseButton>
          <BaseButton size="sm" variant="error" data-testid="delete" @click="remove(secret)">
            {{ t('security.secretsManager.systemVault.delete') }}
          </BaseButton>
        </template>
      </li>
    </ul>
    <BaseAlert v-if="failed" variant="error" :message="t('security.secretsManager.systemVault.failed')" />
  </BaseCard>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton, BaseCard, BaseInput, EmptyState } from '@autobot/ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { secretsApiClient } from '@/utils/SecretsApiClient'
import { createLogger } from '@/utils/debugUtils'

export interface SystemVaultEntry {
  id: string
  name: string
  type: string
}
export interface SystemVaultListing {
  available: boolean
  secrets: SystemVaultEntry[]
}

defineProps<{ vault: SystemVaultListing | null }>()
const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()
const { confirm } = useConfirmDialog()
const logger = createLogger('SystemVaultSecrets')
const rotatingId = ref<string | null>(null)
const newValue = ref('')
const busy = ref(false)
const failed = ref(false)

function startRotate(id: string) {
  rotatingId.value = id
  newValue.value = ''
}

function cancelRotate() {
  rotatingId.value = null
  newValue.value = ''
}

async function run(action: () => Promise<unknown>) {
  busy.value = true
  failed.value = false
  try {
    await action()
    cancelRotate()
    emit('changed')
  } catch (error) {
    failed.value = true
    logger.error('System vault write failed:', error)
  } finally {
    busy.value = false
  }
}

const rotate = (secret: SystemVaultEntry) => run(() => secretsApiClient.updateSecret(secret.id, { value: newValue.value }))

async function remove(secret: SystemVaultEntry) {
  const ok = await confirm({
    title: t('security.secretsManager.systemVault.deleteTitle'),
    message: t('security.secretsManager.systemVault.deleteMessage', { name: secret.name })
  })
  if (ok) await run(() => secretsApiClient.deleteSecret(secret.id))
}
</script>
