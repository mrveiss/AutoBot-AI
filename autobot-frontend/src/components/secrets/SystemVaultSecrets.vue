<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  SYSTEM-vault secrets (#17099): the entries GET /api/secrets/ returns under
  `system_vault` for an admin. Metadata only -- the value is never displayed;
  rotate sends a new one to PUT /api/secrets/{id}, delete calls DELETE.
-->
<template>
  <section v-if="vault" class="system-vault" data-testid="system-vault">
    <h3 class="system-vault-title">{{ t('security.secretsManager.systemVault.title') }}</h3>
    <p v-if="!vault.available" class="system-vault-unavailable" role="alert">
      {{ t('security.secretsManager.systemVault.unavailable') }}
    </p>
    <p v-else-if="!vault.secrets.length" class="system-vault-empty">
      {{ t('security.secretsManager.systemVault.empty') }}
    </p>
    <ul v-else class="system-vault-list">
      <li v-for="secret in vault.secrets" :key="secret.id" class="system-vault-row">
        <Icon name="key" />
        <span class="system-vault-name">{{ secret.name }}</span>
        <span class="system-vault-type">{{ secret.type }}</span>
        <template v-if="rotatingId === secret.id">
          <input
            v-model="newValue"
            type="password"
            autocomplete="new-password"
            class="system-vault-input"
            :aria-label="t('security.secretsManager.systemVault.newValue')"
          />
          <button type="button" class="system-vault-btn" :disabled="!newValue || busy" data-testid="rotate-save" @click="rotate(secret)">
            {{ t('security.secretsManager.systemVault.save') }}
          </button>
          <button type="button" class="system-vault-btn" @click="cancelRotate">
            {{ t('security.secretsManager.systemVault.cancel') }}
          </button>
        </template>
        <template v-else>
          <button type="button" class="system-vault-btn" data-testid="rotate-start" @click="startRotate(secret.id)">
            {{ t('security.secretsManager.systemVault.rotate') }}
          </button>
          <button type="button" class="system-vault-btn system-vault-danger" data-testid="delete" @click="remove(secret)">
            {{ t('security.secretsManager.systemVault.delete') }}
          </button>
        </template>
      </li>
    </ul>
    <p v-if="failed" class="system-vault-unavailable" role="alert">{{ t('security.secretsManager.systemVault.failed') }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
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

<style scoped>
.system-vault {
  margin: var(--spacing-4) 0;
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}
.system-vault-title {
  margin: 0 0 var(--spacing-2);
  font-size: var(--text-lg);
  color: var(--text-primary);
}
.system-vault-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.system-vault-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) 0;
}
.system-vault-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}
.system-vault-type,
.system-vault-empty {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}
.system-vault-unavailable {
  color: var(--color-warning);
  font-size: var(--text-sm);
}
.system-vault-input {
  padding: var(--spacing-1) var(--spacing-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}
.system-vault-btn {
  padding: var(--spacing-1) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}
.system-vault-danger {
  color: var(--color-error);
}
</style>
