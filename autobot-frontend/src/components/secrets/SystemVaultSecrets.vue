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
          <BaseButton size="sm" variant="outline" :disabled="busy" data-testid="rotate-start" @click="startRotate(secret.id)">
            {{ t('security.secretsManager.systemVault.rotate') }}
          </BaseButton>
          <BaseButton size="sm" variant="error" :disabled="busy" data-testid="delete" @click="remove(secret)">
            {{ t('security.secretsManager.systemVault.delete') }}
          </BaseButton>
        </template>
      </li>
    </ul>
    <BaseAlert v-if="failed" variant="error" :message="t('security.secretsManager.writeFailed')" />
  </BaseCard>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton, BaseCard, BaseInput, EmptyState } from '@autobot/ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useSecretWrites } from '@/composables/security/useSecretWrites'
import { secretsApiClient } from '@/utils/SecretsApiClient'

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
const { writeFailed: failed, runWrite, deleteConfirmingDependents } = useSecretWrites()
const rotatingId = ref<string | null>(null)
const newValue = ref('')
const busy = ref(false)

function startRotate(id: string) {
  rotatingId.value = id
  newValue.value = ''
}

function cancelRotate() {
  rotatingId.value = null
  newValue.value = ''
}

/** Run a write on `secretId` through the shared path; a declined confirmation changes nothing. */
async function run(secretId: string, action: () => Promise<unknown>) {
  busy.value = true
  try {
    const outcome = await runWrite('system vault write', action)
    if (outcome === 'declined') return
    // Only the draft of the secret acted on is dropped, and only once applied; another secret's unsaved value stays.
    if (outcome === 'done' && rotatingId.value === secretId) cancelRotate()
    emit('changed') // a failed write's outcome is unconfirmed, so show what is stored either way
  } finally {
    busy.value = false
  }
}

const rotate = (secret: SystemVaultEntry) => run(secret.id, () => secretsApiClient.updateSecret(secret.id, { value: newValue.value }))

/** Ask before deleting. `busy` also covers the open confirm, so a re-entrant click is a no-op. */
async function askToDelete(secret: SystemVaultEntry): Promise<boolean> {
  busy.value = true
  try {
    return await confirm({
      title: t('security.secretsManager.systemVault.deleteTitle'),
      message: t('security.secretsManager.systemVault.deleteMessage', { name: secret.name })
    })
  } finally {
    busy.value = false
  }
}

async function remove(secret: SystemVaultEntry) {
  if (busy.value) return
  if (await askToDelete(secret)) await run(secret.id, () => deleteConfirmingDependents(secret))
}
</script>
