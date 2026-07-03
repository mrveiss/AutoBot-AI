<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-autobot-text-primary">
        {{ t('llmKeys.title') }}
      </h1>
      <button
        class="btn-primary flex items-center gap-2"
        @click="showIssueModal = true"
      >
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        {{ t('llmKeys.issueKey') }}
      </button>
    </div>

    <!-- New raw key banner -->
    <div
      v-if="newRawKey"
      class="mb-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded-lg"
    >
      <p class="text-sm font-semibold text-yellow-800 dark:text-yellow-200 mb-1">
        {{ t('llmKeys.rawKeyWarning') }}
      </p>
      <div class="flex items-center gap-2">
        <code class="flex-1 text-sm font-mono bg-autobot-bg-card px-2 py-1 rounded border">{{ newRawKey }}</code>
        <button class="btn-secondary text-xs" @click="copyRawKey">{{ t('common.copy') }}</button>
      </div>
      <button class="mt-2 text-xs text-yellow-600 underline" @click="newRawKey = ''">{{ t('common.dismiss') }}</button>
    </div>

    <!-- Keys table -->
    <div class="bg-autobot-bg-card rounded-lg shadow overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-autobot-bg-surface text-autobot-text-muted uppercase text-xs">
          <tr>
            <th class="px-4 py-3 text-left">{{ t('llmKeys.col.prefix') }}</th>
            <th class="px-4 py-3 text-left">{{ t('llmKeys.col.team') }}</th>
            <th class="px-4 py-3 text-left">{{ t('llmKeys.col.label') }}</th>
            <th class="px-4 py-3 text-right">{{ t('llmKeys.col.budget') }}</th>
            <th class="px-4 py-3 text-right">{{ t('llmKeys.col.spend') }}</th>
            <th class="px-4 py-3 text-left">{{ t('llmKeys.col.models') }}</th>
            <th class="px-4 py-3 text-left">{{ t('llmKeys.col.status') }}</th>
            <th class="px-4 py-3 text-left">{{ t('llmKeys.col.expires') }}</th>
            <th class="px-4 py-3 text-left">{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-autobot-border">
          <tr v-if="loading">
            <td colspan="9" class="px-4 py-8 text-center text-autobot-text-muted">{{ t('common.loading') }}</td>
          </tr>
          <tr v-else-if="keys.length === 0">
            <td colspan="9" class="px-4 py-8 text-center text-autobot-text-muted">{{ t('llmKeys.empty') }}</td>
          </tr>
          <tr
            v-for="key in keys"
            :key="key.key_id"
            class="hover:bg-autobot-bg-hover"
          >
            <td class="px-4 py-3 font-mono text-xs">{{ key.key_prefix }}</td>
            <td class="px-4 py-3">{{ key.team_id }}</td>
            <td class="px-4 py-3 text-autobot-text-secondary">{{ key.label || '—' }}</td>
            <td class="px-4 py-3 text-right">
              {{ key.monthly_budget_usd > 0 ? '$' + key.monthly_budget_usd.toFixed(2) : t('llmKeys.unlimited') }}
            </td>
            <td class="px-4 py-3 text-right">
              <span :class="spendClass(key)">
                ${{ key.spend_usd_this_month.toFixed(4) }}
              </span>
            </td>
            <td class="px-4 py-3 text-xs">
              {{ key.allowed_models.length ? key.allowed_models.join(', ') : '*' }}
            </td>
            <td class="px-4 py-3">
              <span
                :class="key.revoked
                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'"
                class="px-2 py-0.5 rounded-full text-xs font-medium"
              >
                {{ key.revoked ? t('llmKeys.status.revoked') : t('llmKeys.status.active') }}
              </span>
            </td>
            <td class="px-4 py-3 text-xs text-autobot-text-muted">
              {{ key.expires_at ? new Date(key.expires_at * 1000).toLocaleDateString() : '—' }}
            </td>
            <td class="px-4 py-3">
              <div class="flex gap-2">
                <button
                  v-if="!key.revoked"
                  class="text-xs text-blue-600 hover:underline"
                  @click="handleRotate(key.key_id)"
                >
                  {{ t('llmKeys.rotate') }}
                </button>
                <button
                  v-if="!key.revoked"
                  class="text-xs text-red-600 hover:underline"
                  @click="confirmRevoke(key.key_id)"
                >
                  {{ t('llmKeys.revoke') }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Issue Key Modal -->
    <BaseModal
      v-model="showIssueModal"
      :title="t('llmKeys.issueKey')"
      size="md"
    >
      <form @submit.prevent="handleIssue">
        <div class="space-y-4">
          <div>
            <label class="form-label">{{ t('llmKeys.form.teamId') }} *</label>
            <input v-model="form.team_id" class="form-input" required />
          </div>
          <div>
            <label class="form-label">{{ t('llmKeys.form.label') }}</label>
            <input v-model="form.label" class="form-input" />
          </div>
          <div>
            <label class="form-label">{{ t('llmKeys.form.budget') }}</label>
            <input v-model.number="form.monthly_budget_usd" type="number" step="0.01" min="0" class="form-input" />
            <p class="text-xs text-autobot-text-muted mt-1">{{ t('llmKeys.form.budgetHint') }}</p>
          </div>
          <div>
            <label class="form-label">{{ t('llmKeys.form.models') }}</label>
            <input v-model="form.allowed_models_raw" class="form-input" placeholder='["gpt-4", "claude-*"]' />
            <p class="text-xs text-autobot-text-muted mt-1">{{ t('llmKeys.form.modelsHint') }}</p>
          </div>
          <div>
            <label class="form-label">{{ t('llmKeys.form.expiresAt') }}</label>
            <input v-model="form.expires_at_str" type="date" class="form-input" />
          </div>
        </div>
        <!-- hidden submit keeps Enter-to-submit working inside the form -->
        <button type="submit" class="sr-only" tabindex="-1" aria-hidden="true"></button>
      </form>
      <template #actions>
        <button type="button" class="btn-secondary" @click="showIssueModal = false">
          {{ t('common.cancel') }}
        </button>
        <button type="button" class="btn-primary" :disabled="issuing" @click="handleIssue">
          {{ issuing ? t('common.saving') : t('llmKeys.issueKey') }}
        </button>
      </template>
    </BaseModal>

    <!-- Revoke Confirmation Modal -->
    <BaseModal
      :model-value="!!revokeKeyId"
      :title="t('llmKeys.revokeConfirm.title')"
      size="sm"
      @close="revokeKeyId = ''"
    >
      <p class="text-sm text-autobot-text-secondary">
        {{ t('llmKeys.revokeConfirm.body', { id: revokeKeyId }) }}
      </p>
      <template #actions>
        <button class="btn-secondary" @click="revokeKeyId = ''">{{ t('common.cancel') }}</button>
        <button class="btn-danger" @click="handleRevoke">{{ t('llmKeys.revoke') }}</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getBackendUrl } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'
import { BaseModal } from '@autobot/ui'

const { t } = useI18n()
const logger = createLogger('LlmApiKeysView')

interface KeyRow {
  key_id: string
  key_prefix: string
  team_id: string
  label: string
  monthly_budget_usd: number
  spend_usd_this_month: number
  allowed_models: string[]
  revoked: boolean
  expires_at: number | null
}

const keys = ref<KeyRow[]>([])
const loading = ref(false)
const showIssueModal = ref(false)
const issuing = ref(false)
const newRawKey = ref('')
const revokeKeyId = ref('')

const form = reactive({
  team_id: '',
  label: '',
  monthly_budget_usd: 0,
  allowed_models_raw: '',
  expires_at_str: '',
})

function spendClass(key: KeyRow): string {
  if (key.monthly_budget_usd <= 0) return 'text-autobot-text-secondary'
  const ratio = key.spend_usd_this_month / key.monthly_budget_usd
  if (ratio >= 0.9) return 'text-red-600 font-semibold'
  if (ratio >= 0.7) return 'text-yellow-600 font-semibold'
  return 'text-green-600'
}

async function loadKeys(): Promise<void> {
  loading.value = true
  try {
    const resp = await fetchWithAuth(getBackendUrl() + '/api/llm-keys/list')
    const data = (await resp.json()) as { keys: KeyRow[] }
    keys.value = data.keys ?? []
  } catch (err) {
    logger.error('Failed to load LLM API keys', err)
  } finally {
    loading.value = false
  }
}

async function handleIssue(): Promise<void> {
  issuing.value = true
  try {
    let allowed_models: string[] = []
    if (form.allowed_models_raw.trim()) {
      allowed_models = JSON.parse(form.allowed_models_raw)
    }
    const expires_at = form.expires_at_str
      ? new Date(form.expires_at_str).getTime() / 1000
      : null

    const issueResp = await fetchWithAuth(getBackendUrl() + '/api/llm-keys/issue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        team_id: form.team_id,
        label: form.label,
        monthly_budget_usd: form.monthly_budget_usd,
        allowed_models,
        expires_at,
      }),
    })
    const issueResult = (await issueResp.json()) as { raw_key: string }
    newRawKey.value = issueResult.raw_key
    showIssueModal.value = false
    Object.assign(form, { team_id: '', label: '', monthly_budget_usd: 0, allowed_models_raw: '', expires_at_str: '' })
    await loadKeys()
  } catch (err) {
    logger.error('Failed to issue LLM API key', err)
  } finally {
    issuing.value = false
  }
}

function confirmRevoke(keyId: string): void {
  revokeKeyId.value = keyId
}

async function handleRevoke(): Promise<void> {
  try {
    await fetchWithAuth(getBackendUrl() + '/api/llm-keys/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key_id: revokeKeyId.value }),
    })
    revokeKeyId.value = ''
    await loadKeys()
  } catch (err) {
    logger.error('Failed to revoke LLM API key', err)
  }
}

async function handleRotate(keyId: string): Promise<void> {
  try {
    const rotateResp = await fetchWithAuth(getBackendUrl() + '/api/llm-keys/rotate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key_id: keyId }),
    })
    const rotateResult = (await rotateResp.json()) as { new_raw_key: string }
    newRawKey.value = rotateResult.new_raw_key
    await loadKeys()
  } catch (err) {
    logger.error('Failed to rotate LLM API key', err)
  }
}

async function copyRawKey(): Promise<void> {
  try {
    await navigator.clipboard.writeText(newRawKey.value)
  } catch {
    // clipboard unavailable
  }
}

onMounted(loadKeys)
</script>
