<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#10750 (B2): Company OS "Members" management UI.

  Company-scoped child of LlcCompanyLayout (/llc/companies/:companyId/members).
  Lists current human members (display name + role), supports adding a member
  (user picker populated from /api/user-management/users, role select) and
  removing a member. Roles are the backend MembershipRole enum
  (owner/admin/member/guest/lead — see autobot-backend/llc/models/enums.py).

  Backend has no PATCH-role endpoint; changing a member's role is therefore a
  remove + re-add against the existing endpoints.
-->
<template>
  <div class="members-view">
    <header class="members-header">
      <div>
        <h2 class="members-title">{{ t('llcMembers.title') }}</h2>
        <p class="members-subtitle">{{ t('llcMembers.subtitle') }}</p>
      </div>
      <BaseButton variant="primary" :disabled="!companyId" @click="openAddModal">
        {{ t('llcMembers.addMember') }}
      </BaseButton>
    </header>

    <p v-if="!companyId" class="members-state">{{ t('llcMembers.noCompany') }}</p>

    <template v-else>
      <ErrorBanner v-if="errorMessage" :message="errorMessage" class="members-error" />

      <p v-if="isLoading" class="members-state">{{ t('llcMembers.loading') }}</p>

      <BaseCard v-else-if="members.length === 0" class="members-empty">
        {{ t('llcMembers.empty') }}
      </BaseCard>

      <BaseCard v-else>
        <table class="members-table">
          <thead>
            <tr>
              <th scope="col">{{ t('llcMembers.colName') }}</th>
              <th scope="col">{{ t('llcMembers.colRole') }}</th>
              <th scope="col" class="members-col-actions">{{ t('llcMembers.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="member in members" :key="member.user_id">
              <td>
                <span class="members-name">{{ member.display_name || member.user_id }}</span>
              </td>
              <td>
                <BaseBadge :variant="roleBadgeVariant(member.role)">
                  {{ roleLabel(member.role) }}
                </BaseBadge>
              </td>
              <td class="members-col-actions">
                <BaseButton
                  variant="error"
                  size="sm"
                  :loading="pendingUserId === member.user_id"
                  :disabled="pendingUserId !== null"
                  @click="confirmRemove(member)"
                >
                  {{ t('llcMembers.remove') }}
                </BaseButton>
              </td>
            </tr>
          </tbody>
        </table>
      </BaseCard>
    </template>

    <!-- Add member modal -->
    <BaseModal
      v-model="showAddModal"
      :title="t('llcMembers.addModalTitle')"
      size="md"
    >
      <ErrorBanner v-if="addError" :message="addError" class="members-error" />

      <div class="members-form">
        <div class="members-field">
          <label class="members-label" for="member-user-select">
            {{ t('llcMembers.userLabel') }}
          </label>
          <select
            id="member-user-select"
            v-model="selectedUserId"
            class="members-select"
            :disabled="usersLoading"
          >
            <option value="">{{ t('llcMembers.userPlaceholder') }}</option>
            <option v-for="u in selectableUsers" :key="u.id" :value="u.id">
              {{ u.display_name || u.username }} ({{ u.email }})
            </option>
          </select>
          <p v-if="usersLoading" class="members-hint">{{ t('llcMembers.usersLoading') }}</p>
          <p v-else-if="selectableUsers.length === 0" class="members-hint">
            {{ t('llcMembers.noSelectableUsers') }}
          </p>
        </div>

        <div class="members-field">
          <label class="members-label" for="member-role-select">
            {{ t('llcMembers.roleLabel') }}
          </label>
          <select id="member-role-select" v-model="roleModel" class="members-select">
            <option v-for="role in MEMBERSHIP_ROLES" :key="role" :value="role">
              {{ roleLabel(role) }}
            </option>
          </select>
        </div>
      </div>

      <template #actions>
        <BaseButton variant="secondary" :disabled="isAdding" @click="showAddModal = false">
          {{ t('llcMembers.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          :loading="isAdding"
          :disabled="!selectedUserId || isAdding"
          @click="submitAdd"
        >
          {{ t('llcMembers.confirmAdd') }}
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
import { useCollaborationInvite } from '@/composables/collaboration/useCollaborationInvite'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import { BaseModal } from '@autobot/ui'
import ErrorBanner from '@/components/base/ErrorBanner.vue'

// Backend MembershipRole enum (autobot-backend/llc/models/enums.py).
const MEMBERSHIP_ROLES = ['owner', 'admin', 'member', 'guest', 'lead'] as const
type MembershipRole = (typeof MEMBERSHIP_ROLES)[number]

interface Member {
  user_id: string
  display_name: string | null
  role: string
}

const logger = createLogger('MembersView')
const api = useApiClient()
const route = useRoute()
const { t } = useI18n()

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const members = ref<Member[]>([])
const isLoading = ref(false)
const errorMessage = ref('')
const pendingUserId = ref<string | null>(null)

const showAddModal = ref(false)
const selectedUserId = ref('')
const selectedRole = ref<MembershipRole>('member')
const isAdding = ref(false)
const addError = ref('')

const {
  users,
  loading: usersLoading,
  errorMessage: usersError,
  fetchUsers,
} = useCollaborationInvite()

// Users not already members — the picker only offers people who can be added.
const selectableUsers = computed(() => {
  const existing = new Set(members.value.map((m) => m.user_id))
  return users.value.filter((u) => !existing.has(u.id))
})

function isMembershipRole(value: string): value is MembershipRole {
  return (MEMBERSHIP_ROLES as readonly string[]).includes(value)
}

// Native <select> v-model emits a plain string; this computed accepts that
// string and narrows it back to the MembershipRole union so selectedRole (and
// the API payload built from it) stays type-safe.
const roleModel = computed<string>({
  get: () => selectedRole.value,
  set: (value) => {
    if (isMembershipRole(value)) selectedRole.value = value
  },
})

function roleLabel(role: string): string {
  const key = `llcMembers.role.${role}`
  const label = t(key)
  return label === key ? role : label
}

function roleBadgeVariant(role: string): 'primary' | 'success' | 'warning' | 'default' {
  switch (role) {
    case 'owner':
      return 'primary'
    case 'admin':
    case 'lead':
      return 'success'
    case 'guest':
      return 'warning'
    default:
      return 'default'
  }
}

async function fetchMembers(): Promise<void> {
  if (!companyId.value) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    members.value = await api.get<Member[]>(`/api/llc/companies/${companyId.value}/members`)
  } catch (err) {
    logger.error('Failed to load members', err)
    errorMessage.value = t('llcMembers.loadError')
    members.value = []
  } finally {
    isLoading.value = false
  }
}

function openAddModal(): void {
  selectedUserId.value = ''
  selectedRole.value = 'member'
  addError.value = ''
  showAddModal.value = true
  if (users.value.length === 0) {
    void fetchUsers(t('llcMembers.usersLoadError'))
  }
}

async function submitAdd(): Promise<void> {
  if (!companyId.value || !selectedUserId.value) return
  isAdding.value = true
  addError.value = ''
  try {
    await api.post(`/api/llc/companies/${companyId.value}/members`, {
      user_id: selectedUserId.value,
      role: selectedRole.value,
    })
    showAddModal.value = false
    await fetchMembers()
  } catch (err) {
    logger.error('Failed to add member', err)
    addError.value = t('llcMembers.addError')
  } finally {
    isAdding.value = false
  }
}

async function confirmRemove(member: Member): Promise<void> {
  const name = member.display_name || member.user_id
  if (!window.confirm(t('llcMembers.confirmRemove', { name }))) return
  pendingUserId.value = member.user_id
  errorMessage.value = ''
  try {
    await api.delete(`/api/llc/companies/${companyId.value}/members/${member.user_id}`)
    await fetchMembers()
  } catch (err) {
    logger.error('Failed to remove member', err)
    errorMessage.value = t('llcMembers.removeError')
  } finally {
    pendingUserId.value = null
  }
}

// Surface a picker-load failure inline within the modal.
watch(usersError, (msg) => {
  if (msg) addError.value = msg
})

onMounted(() => {
  void fetchMembers()
})
</script>

<style scoped>
.members-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.members-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.members-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.members-subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.members-state {
  text-align: center;
  padding: 2.5rem;
  color: var(--text-secondary);
}

.members-empty {
  text-align: center;
  color: var(--text-secondary);
}

.members-error {
  margin-bottom: 0.5rem;
}

.members-table {
  width: 100%;
  border-collapse: collapse;
}

.members-table th,
.members-table td {
  text-align: left;
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid var(--border-default);
  font-size: 0.875rem;
}

.members-table th {
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 0.6875rem;
}

.members-col-actions {
  text-align: right;
  width: 1%;
  white-space: nowrap;
}

.members-name {
  font-weight: 500;
}

.members-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.members-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.members-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.members-select {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.875rem;
}

.members-hint {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
