<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  External MCP server admin CRUD (#16825) — the #11542 backend (user-
  configured stdio/SSE/streamable_http servers, credential threading,
  egress guard, stdio launcher allowlist) had no reachable GUI.
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseModal } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import {
  useMcpExternalServersApi,
  type McpServer,
  type McpAuthType,
  type McpTransport,
} from '@/composables/useMcpExternalServersApi'

const { t } = useI18n()
const { list, create, update, remove } = useMcpExternalServersApi()

const PLATFORM_ROLES = ['admin', 'superadmin', 'operator', 'analyst', 'editor', 'user', 'readonly'] as const

const servers = ref<McpServer[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const showModal = ref(false)
const editTarget = ref<McpServer | null>(null)
const saving = ref(false)
const modalError = ref<string | null>(null)

interface FormState {
  name: string
  transport: McpTransport
  command: string
  url: string
  enabled: boolean
  auth_type: McpAuthType
  allowed_roles: string[]
  cred_token: string
  cred_key: string
  cred_header: string
  cred_username: string
  cred_password: string
}

function defaultForm(): FormState {
  return {
    name: '',
    transport: 'stdio',
    command: '',
    url: '',
    enabled: true,
    auth_type: '',
    allowed_roles: ['admin'],
    cred_token: '',
    cred_key: '',
    cred_header: 'X-Api-Key',
    cred_username: '',
    cred_password: '',
  }
}

const form = ref<FormState>(defaultForm())

const deleteTarget = ref<McpServer | null>(null)
const deleting = ref(false)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    servers.value = await list()
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editTarget.value = null
  form.value = defaultForm()
  modalError.value = null
  showModal.value = true
}

function openEdit(server: McpServer): void {
  editTarget.value = server
  form.value = {
    ...defaultForm(),
    name: server.name,
    transport: server.transport,
    command: server.command ?? '',
    url: server.url ?? '',
    enabled: server.enabled,
    allowed_roles: [...server.allowed_roles],
    // Credential fields are never returned by the API (has_credential only) —
    // an edit that doesn't touch auth_type leaves the stored credential as-is.
    auth_type: '',
  }
  modalError.value = null
  showModal.value = true
}

function closeModal(): void {
  showModal.value = false
  editTarget.value = null
  modalError.value = null
}

function buildCredentials(): Record<string, string> | undefined {
  switch (form.value.auth_type) {
    case 'BearerAuth':
      return { token: form.value.cred_token }
    case 'ApiKeyAuth':
      return { key: form.value.cred_key, header: form.value.cred_header }
    case 'BasicAuth':
      return { username: form.value.cred_username, password: form.value.cred_password }
    default:
      return undefined
  }
}

async function submitForm(): Promise<void> {
  saving.value = true
  modalError.value = null
  try {
    const credentials = buildCredentials()
    if (editTarget.value) {
      await update(editTarget.value.server_id, {
        name: form.value.name,
        enabled: form.value.enabled,
        command: form.value.transport === 'stdio' ? form.value.command : undefined,
        url: form.value.transport !== 'stdio' ? form.value.url : undefined,
        auth_type: form.value.auth_type || undefined,
        credentials,
        allowed_roles: form.value.allowed_roles,
      })
    } else {
      await create({
        name: form.value.name,
        transport: form.value.transport,
        command: form.value.transport === 'stdio' ? form.value.command : undefined,
        url: form.value.transport !== 'stdio' ? form.value.url : undefined,
        auth_type: form.value.auth_type || undefined,
        credentials,
        enabled: form.value.enabled,
        allowed_roles: form.value.allowed_roles,
      })
    }
    closeModal()
    await load()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : t('admin.mcpServers.saveFailed')
  } finally {
    saving.value = false
  }
}

function confirmDelete(server: McpServer): void {
  deleteTarget.value = server
}

async function doDelete(): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await remove(deleteTarget.value.server_id)
    deleteTarget.value = null
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('admin.mcpServers.deleteFailed')
  } finally {
    deleting.value = false
  }
}

const transportLabel = computed(() => (transport: McpTransport) => {
  return t(`admin.mcpServers.transport${transport === 'streamable_http' ? 'StreamableHttp' : transport === 'sse' ? 'Sse' : 'Stdio'}`)
})

onMounted(load)
</script>

<template>
  <div class="admin-mcp-servers view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h1 class="page-title">{{ t('admin.mcpServers.title') }}</h1>
        <p class="page-subtitle">{{ t('admin.mcpServers.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-primary" @click="openCreate">
          <Icon name="plus-circle" />
          {{ t('admin.mcpServers.newServer') }}
        </button>
        <button class="btn-action-secondary" :disabled="loading" @click="load">
          <Icon name="sync-alt" :spin="loading" />
          {{ t('common.refresh') }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
    </div>

    <div v-if="loading && servers.length === 0" class="loading-state">
      <Icon name="sync-alt" :spin="true" /> {{ t('admin.mcpServers.loading') }}
    </div>
    <div v-else-if="!loading && servers.length === 0" class="empty-state">
      <Icon name="network-wired" class="empty-icon" />
      <p>{{ t('admin.mcpServers.empty') }}</p>
    </div>

    <table v-else class="data-table">
      <thead>
        <tr>
          <th>{{ t('admin.mcpServers.colName') }}</th>
          <th>{{ t('admin.mcpServers.colTransport') }}</th>
          <th>{{ t('admin.mcpServers.colTarget') }}</th>
          <th>{{ t('admin.mcpServers.colCredential') }}</th>
          <th>{{ t('admin.mcpServers.colRoles') }}</th>
          <th>{{ t('admin.mcpServers.colStatus') }}</th>
          <th>{{ t('admin.mcpServers.colActions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="server in servers" :key="server.server_id">
          <td>{{ server.name }}</td>
          <td>
            <BaseBadge variant="neutral" size="sm">{{ transportLabel(server.transport) }}</BaseBadge>
          </td>
          <td class="monospace">{{ server.command || server.url || '—' }}</td>
          <td>
            <BaseBadge :variant="server.has_credential ? 'success' : 'neutral'" size="sm">
              {{ server.has_credential ? t('admin.mcpServers.credentialSet') : t('admin.mcpServers.credentialNone') }}
            </BaseBadge>
          </td>
          <td>{{ server.allowed_roles.join(', ') }}</td>
          <td>
            <BaseBadge :variant="server.enabled ? 'success' : 'neutral'" size="sm">
              {{ server.enabled ? t('admin.mcpServers.statusEnabled') : t('admin.mcpServers.statusDisabled') }}
            </BaseBadge>
          </td>
          <td class="actions-cell">
            <button class="btn-icon" :title="t('common.edit')" @click="openEdit(server)">
              <Icon name="pencil-alt" />
            </button>
            <button class="btn-icon btn-danger" :title="t('common.delete')" @click="confirmDelete(server)">
              <Icon name="trash-alt" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Create / Edit Modal -->
    <BaseModal
      :model-value="showModal"
      :title="editTarget ? t('admin.mcpServers.modalEditTitle') : t('admin.mcpServers.modalNewTitle')"
      :close-label="t('common.close')"
      :width="560"
      @close="closeModal"
    >
      <div v-if="modalError" class="error-banner">
        <Icon name="exclamation-circle" />
        <span>{{ modalError }}</span>
      </div>

      <form id="mcp-server-form" class="modal-form" @submit.prevent="submitForm">
        <div class="form-row">
          <label class="form-label">{{ t('admin.mcpServers.fieldName') }} <span class="required">*</span></label>
          <input v-model="form.name" type="text" class="text-input" required />
        </div>

        <div class="form-row">
          <label class="form-label">{{ t('admin.mcpServers.fieldTransport') }} <span class="required">*</span></label>
          <select v-model="form.transport" class="filter-select" :disabled="!!editTarget">
            <option value="stdio">{{ t('admin.mcpServers.transportStdio') }}</option>
            <option value="sse">{{ t('admin.mcpServers.transportSse') }}</option>
            <option value="streamable_http">{{ t('admin.mcpServers.transportStreamableHttp') }}</option>
          </select>
        </div>

        <div v-if="form.transport === 'stdio'" class="form-row">
          <label class="form-label">{{ t('admin.mcpServers.fieldCommand') }} <span class="required">*</span></label>
          <input v-model="form.command" type="text" class="text-input" placeholder="npx -y @modelcontextprotocol/server-example" required />
        </div>
        <div v-else class="form-row">
          <label class="form-label">{{ t('admin.mcpServers.fieldUrl') }} <span class="required">*</span></label>
          <input v-model="form.url" type="url" class="text-input" placeholder="https://example.com/mcp" required />
        </div>

        <div class="form-row">
          <label class="form-label">{{ t('admin.mcpServers.fieldAuthType') }}</label>
          <select v-model="form.auth_type" class="filter-select">
            <option value="">{{ t('admin.mcpServers.authNone') }}</option>
            <option value="BearerAuth">{{ t('admin.mcpServers.authBearer') }}</option>
            <option value="ApiKeyAuth">{{ t('admin.mcpServers.authApiKey') }}</option>
            <option value="BasicAuth">{{ t('admin.mcpServers.authBasic') }}</option>
          </select>
          <p v-if="editTarget" class="field-hint">{{ t('admin.mcpServers.authEditHint') }}</p>
        </div>

        <template v-if="form.auth_type === 'BearerAuth'">
          <div class="form-row">
            <label class="form-label">{{ t('admin.mcpServers.fieldToken') }} <span class="required">*</span></label>
            <input v-model="form.cred_token" type="password" class="text-input" autocomplete="off" required />
          </div>
        </template>
        <template v-else-if="form.auth_type === 'ApiKeyAuth'">
          <div class="form-row two-col">
            <div>
              <label class="form-label">{{ t('admin.mcpServers.fieldApiKey') }} <span class="required">*</span></label>
              <input v-model="form.cred_key" type="password" class="text-input" autocomplete="off" required />
            </div>
            <div>
              <label class="form-label">{{ t('admin.mcpServers.fieldHeader') }}</label>
              <input v-model="form.cred_header" type="text" class="text-input" />
            </div>
          </div>
        </template>
        <template v-else-if="form.auth_type === 'BasicAuth'">
          <div class="form-row two-col">
            <div>
              <label class="form-label">{{ t('admin.mcpServers.fieldUsername') }} <span class="required">*</span></label>
              <input v-model="form.cred_username" type="text" class="text-input" required />
            </div>
            <div>
              <label class="form-label">{{ t('admin.mcpServers.fieldPassword') }} <span class="required">*</span></label>
              <input v-model="form.cred_password" type="password" class="text-input" autocomplete="off" required />
            </div>
          </div>
        </template>

        <div class="form-row">
          <label class="form-label">{{ t('admin.mcpServers.fieldAllowedRoles') }}</label>
          <div class="role-checkboxes">
            <label v-for="role in PLATFORM_ROLES" :key="role" class="checkbox-label">
              <input v-model="form.allowed_roles" type="checkbox" :value="role" class="checkbox-input" />
              {{ role }}
            </label>
          </div>
        </div>

        <div class="form-row">
          <label class="checkbox-label">
            <input v-model="form.enabled" type="checkbox" class="checkbox-input" />
            {{ t('admin.mcpServers.fieldEnabled') }}
          </label>
        </div>
      </form>

      <template #actions>
        <button type="button" class="btn-action-secondary" @click="closeModal">{{ t('common.cancel') }}</button>
        <button type="submit" form="mcp-server-form" class="btn-action-primary" :disabled="saving">
          <Icon v-if="saving" name="sync-alt" :spin="true" />
          {{ editTarget ? t('admin.mcpServers.saveChanges') : t('admin.mcpServers.createServer') }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete confirm -->
    <BaseModal
      :model-value="!!deleteTarget"
      :title="t('admin.mcpServers.deleteTitle')"
      :close-label="t('common.close')"
      :width="420"
      @close="deleteTarget = null"
    >
      <p v-if="deleteTarget" class="modal-body-text">
        {{ t('admin.mcpServers.deleteConfirm') }}
        <strong>{{ deleteTarget.name }}</strong>?
        {{ t('admin.mcpServers.deleteUndone') }}
      </p>
      <template #actions>
        <button class="btn-action-secondary" @click="deleteTarget = null">{{ t('common.cancel') }}</button>
        <button class="btn-action-danger" :disabled="deleting" @click="doDelete">
          <Icon v-if="deleting" name="sync-alt" :spin="true" />
          {{ t('common.delete') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.admin-mcp-servers {
  padding: var(--spacing-6);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-6);
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  margin: 0 0 var(--spacing-1);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  margin-bottom: var(--spacing-4);
  background-color: var(--bg-danger-subtle, #fef2f2);
  color: var(--text-danger, #b91c1c);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.loading-state,
.empty-state {
  padding: var(--spacing-12) var(--spacing-4);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.empty-icon {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-2);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.data-table th {
  text-align: left;
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--text-tertiary);
  font-weight: var(--font-medium);
  border-bottom: 1px solid var(--border-default);
}

.data-table td {
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
  vertical-align: middle;
}

.monospace {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.actions-cell {
  display: flex;
  gap: var(--spacing-2);
}

.btn-icon {
  padding: var(--spacing-1) var(--spacing-2);
  background: none;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
}

.btn-icon.btn-danger {
  color: var(--text-danger, #b91c1c);
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.form-row.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-3);
}

.form-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  margin-bottom: var(--spacing-1);
}

.required {
  color: var(--text-danger, #b91c1c);
}

.field-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: var(--spacing-1) 0 0;
}

.text-input,
.filter-select {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.role-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-sm);
}

.modal-body-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.btn-action-primary,
.btn-action-secondary,
.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  border-radius: var(--radius-md);
  cursor: pointer;
  white-space: nowrap;
}

.btn-action-primary {
  color: var(--text-on-primary, #fff);
  background-color: var(--color-primary, #2563eb);
  border: 1px solid transparent;
}

.btn-action-secondary {
  color: var(--text-primary);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.btn-action-danger {
  color: var(--text-on-primary, #fff);
  background-color: var(--color-danger, #dc2626);
  border: 1px solid transparent;
}

.btn-action-primary:disabled,
.btn-action-secondary:disabled,
.btn-action-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
