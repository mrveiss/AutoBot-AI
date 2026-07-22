<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  GH#11388: Company OS company-scoped secrets management.

  Operator UI for the LLC secrets backend (GH#8216 §6.12, autobot-backend/llc/api/secrets.py):
  list / create-or-update / revoke company secrets that routines and agents bind
  to by name. Values are write-only — never fetched or displayed after entry.
  Company-scoped via :companyId so the LlcSidebar stays mounted (#10750 B3).
-->
<template>
  <div class="secrets-view">
    <div class="secrets-header">
      <div>
        <h2 class="view-title">{{ $t('llc.secrets.title') }}</h2>
        <p class="view-sub">{{ $t('llc.secrets.subtitle') }}</p>
      </div>
      <button class="btn-primary" @click="openCreate">{{ $t('llc.secrets.newSecret') }}</button>
    </div>

    <div v-if="isLoading && secrets.length === 0" class="state-msg">{{ $t('llc.secrets.loading') }}</div>
    <div v-else-if="loadError" class="state-msg state-error">{{ loadError }}</div>
    <div v-else-if="secrets.length === 0" class="state-msg">{{ $t('llc.secrets.empty') }}</div>

    <div v-else class="secrets-grid-wrapper">
      <table class="secrets-grid">
        <thead>
          <tr>
            <th>{{ $t('llc.secrets.colName') }}</th>
            <th>{{ $t('llc.secrets.colVersion') }}</th>
            <th>{{ $t('llc.secrets.colCreatedBy') }}</th>
            <th>{{ $t('llc.secrets.colCreatedAt') }}</th>
            <th>{{ $t('llc.secrets.colStatus') }}</th>
            <th>{{ $t('llc.secrets.colActions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="secret in secrets" :key="secret.name" class="secret-row">
            <td class="secret-name"><code>{{ secret.name }}</code></td>
            <td>v{{ secret.version }}</td>
            <td class="secret-actor">{{ secret.created_by_agent_id }}</td>
            <td>{{ displayDate(secret.created_at) }}</td>
            <td>
              <span class="status-badge" :class="secret.revoked_at ? 'status-revoked' : 'status-active'">
                {{ secret.revoked_at ? $t('llc.secrets.statusRevoked') : $t('llc.secrets.statusActive') }}
              </span>
            </td>
            <td class="secret-actions">
              <button class="btn-sm" @click="openRotate(secret)">{{ $t('llc.secrets.rotate') }}</button>
              <button
                v-if="!secret.revoked_at"
                class="btn-sm btn-danger"
                :disabled="mutating.has(secret.name)"
                @click="revokeSecret(secret)"
              >
                {{ $t('llc.secrets.revoke') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / rotate modal -->
    <div v-if="editorOpen" class="modal-overlay" @click.self="closeEditor">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h3>{{ rotateName ? $t('llc.secrets.rotateTitle', { name: rotateName }) : $t('llc.secrets.createTitle') }}</h3>
          <button class="btn-close" :aria-label="$t('common.close')" @click="closeEditor">✕</button>
        </div>
        <form class="modal-body" @submit.prevent="submitEditor">
          <label class="field">
            <span>{{ $t('llc.secrets.fieldName') }}</span>
            <input
              v-model.trim="form.name"
              type="text"
              required
              :disabled="!!rotateName"
              :placeholder="$t('llc.secrets.fieldNamePlaceholder')"
            />
          </label>
          <label class="field">
            <span>{{ $t('llc.secrets.fieldValue') }}</span>
            <input
              v-model="form.value"
              type="password"
              required
              autocomplete="new-password"
              :placeholder="$t('llc.secrets.fieldValuePlaceholder')"
            />
            <small class="field-hint">{{ $t('llc.secrets.valueHint') }}</small>
          </label>
          <p v-if="editorError" class="state-error">{{ editorError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-sm" @click="closeEditor">{{ $t('common.cancel') }}</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? $t('llc.secrets.saving') : $t('llc.secrets.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { formatDateTime } from '@/utils/formatHelpers'
import { useUserStore } from '@/stores/useUserStore'
import type { components } from '@/types/generated/api'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ companyId?: string }>()

const logger = createLogger('SecretsView')
const api = useApiClient()
const userStore = useUserStore()
const { t } = useI18n()

// #11367: derive from the generated OpenAPI schema.
type SecretSummary = components['schemas']['SecretSummary']

const secrets = ref<SecretSummary[]>([])
const isLoading = ref(false)
const loadError = ref('')
const mutating = ref<Set<string>>(new Set())

const editorOpen = ref(false)
const rotateName = ref<string | null>(null)
const saving = ref(false)
const editorError = ref('')
const form = ref({ name: '', value: '' })

function displayDate(iso?: string | null) {
  return formatDateTime(iso) || '—'
}

function actor() {
  return userStore.currentUser?.username ?? 'operator'
}

// Secrets routes require the X-Agent-Company-Id header (backend _check_company_access
// equality guard); ApiClient does not inject it, so pass it explicitly per call.
function companyHeaders() {
  return { headers: { 'X-Agent-Company-Id': props.companyId ?? '' } }
}

async function loadSecrets() {
  if (!props.companyId) return
  isLoading.value = true
  loadError.value = ''
  try {
    secrets.value = await api.get<SecretSummary[]>(`/api/llc/secrets/${props.companyId}`, companyHeaders())
  } catch (err) {
    logger.error('Failed to load secrets', err)
    loadError.value = t('llc.secrets.loadFailed')
  } finally {
    isLoading.value = false
  }
}

function openCreate() {
  rotateName.value = null
  editorError.value = ''
  form.value = { name: '', value: '' }
  editorOpen.value = true
}

function openRotate(secret: SecretSummary) {
  rotateName.value = secret.name
  editorError.value = ''
  form.value = { name: secret.name, value: '' }
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
}

async function submitEditor() {
  if (!props.companyId) return
  saving.value = true
  editorError.value = ''
  try {
    await api.post(
      `/api/llc/secrets/${props.companyId}`,
      { name: form.value.name, value: form.value.value, actor: actor() },
      companyHeaders(),
    )
    editorOpen.value = false
    await loadSecrets()
  } catch (err) {
    logger.error('Failed to save secret', err)
    editorError.value = t('llc.secrets.saveFailed')
  } finally {
    saving.value = false
  }
}

async function revokeSecret(secret: SecretSummary) {
  if (!props.companyId) return
  if (!window.confirm(t('llc.secrets.confirmRevoke', { name: secret.name }))) return
  const next = new Set(mutating.value)
  next.add(secret.name)
  mutating.value = next
  loadError.value = ''
  try {
    // actor is a required query param on the revoke route (backend contract).
    const path = `/api/llc/secrets/${props.companyId}/${encodeURIComponent(secret.name)}`
    await api.delete(`${path}?actor=${encodeURIComponent(actor())}`, companyHeaders())
    await loadSecrets()
  } catch (err) {
    logger.error('Failed to revoke secret', err)
    loadError.value = t('llc.secrets.revokeFailed')
  } finally {
    const done = new Set(mutating.value)
    done.delete(secret.name)
    mutating.value = done
  }
}

onMounted(() => void loadSecrets())
</script>

<style scoped>
/* Ember semantic tokens with fallbacks for non-ember themes. */
.secrets-view {
  padding: 1rem 1.25rem;
}

.secrets-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1rem;
  gap: 1rem;
}

.view-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.view-sub {
  font-size: 0.8125rem;
  color: var(--text-muted);
  margin-top: 0.125rem;
}

.state-msg {
  padding: 1.5rem 0;
  color: var(--text-muted);
}

.state-error {
  color: var(--color-danger);
}

.secrets-grid-wrapper {
  overflow-x: auto;
}

.secrets-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.secrets-grid th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-default);
}

.secrets-grid td {
  padding: 0.625rem 0.75rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.secret-name code {
  font-family: var(--font-mono, monospace);
  font-size: 0.8125rem;
  background: var(--bg-code, var(--secretsview-bg-code));
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-sm);
}

.secret-actor {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.status-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 999px;
}

.status-active {
  background: var(--color-success-subtle, var(--secretsview-success-bg));
  color: var(--color-success-text, var(--secretsview-success-text));
}

.status-revoked {
  background: var(--bg-muted, var(--secretsview-status-revoked-bg));
  color: var(--text-muted);
}

.secret-actions {
  display: flex;
  gap: 0.375rem;
}

.btn-primary {
  padding: 0.4375rem 0.875rem;
  font-size: 0.875rem;
  font-weight: 600;
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-accent, var(--secretsview-accent));
  color: var(--secretsview-on-accent);
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 0.25rem 0.625rem;
  font-size: 0.8125rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
}

.btn-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-danger {
  color: var(--color-danger);
  border-color: var(--color-danger-subtle, var(--secretsview-danger-border));
}

.btn-close {
  border: none;
  background: none;
  font-size: 1rem;
  cursor: pointer;
  color: var(--text-muted);
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.modal {
  width: min(30rem, 92vw);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default);
}

.modal-body {
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.field input {
  padding: 0.4375rem 0.5rem;
  font-size: 0.875rem;
  font-weight: 400;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-primary);
}

.field input:disabled {
  background: var(--bg-muted, var(--secretsview-input-disabled-bg));
  color: var(--text-muted);
}

.field-hint {
  font-weight: 400;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
