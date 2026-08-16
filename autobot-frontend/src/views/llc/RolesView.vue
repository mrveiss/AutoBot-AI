<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #14221 step 6: Company OS "Roles" tab.

  Company-scoped child of LlcCompanyLayout (/llc/companies/:companyId/roles).

  The layout follows the idea the whole issue is built on: a role is the durable
  thing, and holders come and go. So the left column lists roles, and the right
  column shows what a role *carries* — holders, permissions, workflows, tools
  and credentials — with the holder panel showing past tenures as well as
  current ones, because that history is what survives a departure.

  Credentials are shown as ids only. The backend never returns a secret's value
  or name through this surface, and this view must not invent a place to put
  one.

  Every mutation here is admin-only server-side (llc/services/authz.py). The UI
  does not hide the controls based on a locally-guessed role: a client-side
  guess that disagrees with the server produces a worse experience than a clear
  403, and duplicating the rule invites the two copies to drift.
-->
<template>
  <div class="roles-view">
    <header class="roles-header">
      <div>
        <h2 class="roles-title">{{ t('llcRoles.title') }}</h2>
        <p class="roles-subtitle">{{ t('llcRoles.subtitle') }}</p>
      </div>
      <BaseButton variant="primary" :disabled="!companyId" @click="openCreateModal">
        {{ t('llcRoles.addRole') }}
      </BaseButton>
    </header>

    <p v-if="!companyId" class="roles-state">{{ t('llcRoles.noCompany') }}</p>

    <template v-else>
      <ErrorBanner v-if="errorMessage" :message="errorMessage" class="roles-error" />

      <p v-if="isLoading" class="roles-state">{{ t('llcRoles.loading') }}</p>

      <BaseCard v-else-if="roles.length === 0" class="roles-empty">
        {{ t('llcRoles.empty') }}
      </BaseCard>

      <div v-else class="roles-layout">
        <BaseCard class="roles-list-card">
          <ul class="roles-list">
            <li v-for="role in roles" :key="role.id">
              <button
                type="button"
                class="roles-list-item"
                :class="{ 'is-active': role.id === selectedRoleId }"
                @click="selectRole(role.id)"
              >
                <span class="roles-list-name">{{ role.name }}</span>
                <BaseBadge v-if="role.is_system" variant="neutral">
                  {{ t('llcRoles.systemRole') }}
                </BaseBadge>
              </button>
            </li>
          </ul>
        </BaseCard>

        <BaseCard v-if="selectedRole" class="roles-detail-card">
          <header class="roles-detail-header">
            <div>
              <h3 class="roles-detail-name">{{ selectedRole.name }}</h3>
              <p v-if="selectedRole.description" class="roles-detail-description">
                {{ selectedRole.description }}
              </p>
            </div>
            <BaseButton
              variant="error"
              :disabled="selectedRole.is_system"
              @click="removeRole(selectedRole.id)"
            >
              {{ t('llcRoles.deleteRole') }}
            </BaseButton>
          </header>

          <p v-if="isDetailLoading" class="roles-state">{{ t('llcRoles.loading') }}</p>

          <template v-else>
            <section class="roles-section">
              <h4 class="roles-section-title">{{ t('llcRoles.holders') }}</h4>
              <p v-if="holders.length === 0" class="roles-section-empty">
                {{ t('llcRoles.noHolders') }}
              </p>
              <ul v-else class="roles-chip-list">
                <li v-for="holder in holders" :key="holder.id" class="roles-chip">
                  <BaseBadge :variant="holder.ended_at ? 'neutral' : 'success'">
                    {{ t(`llcRoles.holderType.${holder.holder_type}`) }}
                  </BaseBadge>
                  <span class="roles-chip-id">{{ holder.holder_id }}</span>
                  <span v-if="holder.ended_at" class="roles-chip-note">
                    {{ t('llcRoles.pastHolder') }}
                  </span>
                </li>
              </ul>
              <label class="roles-toggle">
                <input v-model="includePastHolders" type="checkbox" @change="loadDetail" />
                {{ t('llcRoles.showPastHolders') }}
              </label>
            </section>

            <section class="roles-section">
              <h4 class="roles-section-title">{{ t('llcRoles.permissions') }}</h4>
              <p v-if="permissions.length === 0" class="roles-section-empty">
                {{ t('llcRoles.noPermissions') }}
              </p>
              <ul v-else class="roles-chip-list">
                <li v-for="permission in permissions" :key="permission" class="roles-chip">
                  {{ permission }}
                </li>
              </ul>
            </section>

            <section class="roles-section">
              <h4 class="roles-section-title">{{ t('llcRoles.workflows') }}</h4>
              <p v-if="workflows.length === 0" class="roles-section-empty">
                {{ t('llcRoles.noWorkflows') }}
              </p>
              <ul v-else class="roles-chip-list">
                <li v-for="workflow in workflows" :key="workflow" class="roles-chip">
                  {{ workflow }}
                </li>
              </ul>
            </section>

            <section class="roles-section">
              <h4 class="roles-section-title">{{ t('llcRoles.tools') }}</h4>
              <p v-if="tools.length === 0" class="roles-section-empty">
                {{ t('llcRoles.noTools') }}
              </p>
              <ul v-else class="roles-chip-list">
                <li v-for="tool in tools" :key="tool" class="roles-chip">{{ tool }}</li>
              </ul>
            </section>

            <section class="roles-section">
              <h4 class="roles-section-title">{{ t('llcRoles.credentials') }}</h4>
              <!-- Ids only. The backend never exposes a secret's value or name
                   through this surface. -->
              <p v-if="credentials.length === 0" class="roles-section-empty">
                {{ t('llcRoles.noCredentials') }}
              </p>
              <ul v-else class="roles-chip-list">
                <li v-for="secretId in credentials" :key="secretId" class="roles-chip">
                  {{ secretId }}
                </li>
              </ul>
            </section>
          </template>
        </BaseCard>
      </div>
    </template>

    <BaseModal
      v-model="isCreateModalOpen"
      :title="t('llcRoles.addRole')"
      :close-label="t('ui.modal.closeDialog')"
      size="md"
    >
      <template #default>
        <label class="roles-field">
          <span>{{ t('llcRoles.fieldName') }}</span>
          <input v-model="newRoleName" type="text" maxlength="100" />
        </label>
        <label class="roles-field">
          <span>{{ t('llcRoles.fieldDescription') }}</span>
          <textarea v-model="newRoleDescription" rows="3" maxlength="2000"></textarea>
        </label>
      </template>
      <template #footer>
        <BaseButton variant="secondary" @click="closeCreateModal">
          {{ t('llcRoles.cancel') }}
        </BaseButton>
        <BaseButton variant="primary" :disabled="!newRoleName.trim()" @click="createRole">
          {{ t('llcRoles.save') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { BaseModal } from '@autobot/ui'
import ErrorBanner from '@/components/base/ErrorBanner.vue'

interface RoleRow {
  id: string
  company_id: string
  name: string
  description?: string | null
  is_system: boolean
}

interface HolderRow {
  id: string
  role_id: string
  holder_type: string
  holder_id?: string | null
  started_at?: string | null
  ended_at?: string | null
}

const logger = createLogger('LlcRolesView')
const { t } = useI18n()
const route = useRoute()
const api = useApiClient()

const roles = ref<RoleRow[]>([])
const holders = ref<HolderRow[]>([])
const permissions = ref<string[]>([])
const workflows = ref<string[]>([])
const tools = ref<string[]>([])
const credentials = ref<string[]>([])

const selectedRoleId = ref<string | null>(null)
const includePastHolders = ref(false)
const isLoading = ref(false)
const isDetailLoading = ref(false)
const errorMessage = ref('')

const isCreateModalOpen = ref(false)
const newRoleName = ref('')
const newRoleDescription = ref('')

const companyId = computed(() => (route.params.companyId as string) || '')
const selectedRole = computed(
  () => roles.value.find((role) => role.id === selectedRoleId.value) ?? null,
)

function describeError(error: unknown, fallbackKey: string): string {
  // Surface the server's reason rather than a generic message: a 403 from the
  // admin gate and a 400 from validation need different actions from the user,
  // and collapsing them into "something went wrong" hides which one happened.
  //
  // ApiClient throws a plain Error whose message is already `HTTP <status>:
  // <detail>` — it extracts `detail` itself (utils/ApiClient.ts
  // _extractErrorInfo). It is NOT axios-shaped, so reading
  // `error.response.data.detail` would silently always miss and this function
  // would return the generic fallback every time while looking like it worked.
  const message = error instanceof Error ? error.message : ''
  return message.length > 0 ? message : t(fallbackKey)
}

async function loadRoles(): Promise<void> {
  if (!companyId.value) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    const loaded = await api.get<RoleRow[]>(`/api/llc/roles/${companyId.value}`)
    roles.value = Array.isArray(loaded) ? loaded : []
    if (roles.value.length > 0 && !selectedRoleId.value) {
      await selectRole(roles.value[0].id)
    }
  } catch (error) {
    logger.error('Failed to load roles', error)
    errorMessage.value = describeError(error, 'llcRoles.errorLoad')
  } finally {
    isLoading.value = false
  }
}

async function loadDetail(): Promise<void> {
  const roleId = selectedRoleId.value
  if (!companyId.value || !roleId) return
  isDetailLoading.value = true
  errorMessage.value = ''
  const base = `/api/llc/roles/${companyId.value}/${roleId}`
  try {
    // Fetched together so a slow panel cannot leave the others showing a
    // previous role's data — a partially-updated detail pane reads as fact.
    const [loadedHolders, loadedPermissions, loadedWorkflows, loadedTools, loadedCredentials] =
      await Promise.all([
        api.get<HolderRow[]>(`${base}/holders?include_past=${includePastHolders.value}`),
        api.get<string[]>(`${base}/permissions`),
        api.get<string[]>(`${base}/workflows`),
        api.get<string[]>(`${base}/tools`),
        api.get<string[]>(`${base}/credentials`),
      ])
    holders.value = Array.isArray(loadedHolders) ? loadedHolders : []
    permissions.value = Array.isArray(loadedPermissions) ? loadedPermissions : []
    workflows.value = Array.isArray(loadedWorkflows) ? loadedWorkflows : []
    tools.value = Array.isArray(loadedTools) ? loadedTools : []
    credentials.value = Array.isArray(loadedCredentials) ? loadedCredentials : []
  } catch (error) {
    logger.error('Failed to load role detail', error)
    errorMessage.value = describeError(error, 'llcRoles.errorLoadDetail')
  } finally {
    isDetailLoading.value = false
  }
}

async function selectRole(roleId: string): Promise<void> {
  selectedRoleId.value = roleId
  await loadDetail()
}

function openCreateModal(): void {
  newRoleName.value = ''
  newRoleDescription.value = ''
  isCreateModalOpen.value = true
}

function closeCreateModal(): void {
  isCreateModalOpen.value = false
}

async function createRole(): Promise<void> {
  if (!companyId.value || !newRoleName.value.trim()) return
  try {
    await api.post(`/api/llc/roles/${companyId.value}`, {
      name: newRoleName.value.trim(),
      description: newRoleDescription.value.trim() || null,
    })
    closeCreateModal()
    await loadRoles()
  } catch (error) {
    logger.error('Failed to create role', error)
    errorMessage.value = describeError(error, 'llcRoles.errorCreate')
  }
}

async function removeRole(roleId: string): Promise<void> {
  if (!companyId.value) return
  try {
    await api.delete(`/api/llc/roles/${companyId.value}/${roleId}`)
    if (selectedRoleId.value === roleId) selectedRoleId.value = null
    await loadRoles()
  } catch (error) {
    logger.error('Failed to delete role', error)
    errorMessage.value = describeError(error, 'llcRoles.errorDelete')
  }
}

watch(companyId, async () => {
  selectedRoleId.value = null
  await loadRoles()
})

onMounted(loadRoles)
</script>

<style scoped>
.roles-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.roles-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.roles-title {
  margin: 0;
  font-size: var(--font-size-xl);
  color: var(--color-text-primary);
}

.roles-subtitle {
  margin: var(--spacing-xs) 0 0;
  color: var(--color-text-secondary);
}

.roles-state,
.roles-section-empty {
  color: var(--color-text-secondary);
}

.roles-layout {
  display: grid;
  grid-template-columns: minmax(12rem, 18rem) 1fr;
  gap: var(--spacing-lg);
  align-items: start;
}

.roles-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.roles-list-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-primary);
  cursor: pointer;
  text-align: start;
}

.roles-list-item:hover,
.roles-list-item.is-active {
  background: var(--color-surface-hover);
}

.roles-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.roles-detail-name {
  margin: 0;
  font-size: var(--font-size-lg);
  color: var(--color-text-primary);
}

.roles-detail-description {
  margin: var(--spacing-xs) 0 0;
  color: var(--color-text-secondary);
}

.roles-section {
  margin-top: var(--spacing-md);
}

.roles-section-title {
  margin: 0 0 var(--spacing-xs);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
}

.roles-chip-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.roles-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font-family: var(--font-family-mono, monospace);
  font-size: var(--font-size-sm);
}

.roles-chip-note {
  color: var(--color-text-secondary);
  font-family: var(--font-family-base, inherit);
}

.roles-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  color: var(--color-text-secondary);
}

.roles-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
}

@media (max-width: 48rem) {
  .roles-layout {
    grid-template-columns: 1fr;
  }
}
</style>
