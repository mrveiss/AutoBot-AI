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

  A member's role changes in place via PATCH /members/{user_id} (#19960). The
  server owns the rules (membership_policy.py): it answers 403 / 409 and the row
  reverts. The list also carries the roles the viewer may grant (#20073), computed
  by the server from the verified caller; the control is disabled for a member the
  viewer may not change and the roles they may not grant are not offered. That only
  reflects the server, which still refuses what the viewer may not do. Loading and
  role changes are scoped to the company shown: see useCompanyMembers.
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
      <BaseAlert variant="error" v-if="errorMessage" :message="errorMessage" class="members-error" dismissible :dismiss-label="t('common.dismiss')" />

      <p v-if="isLoading" class="members-state">{{ t('llcMembers.loading') }}</p>

      <BaseCard v-else-if="members.length === 0" class="members-empty">
        {{ t('llcMembers.empty') }}
      </BaseCard>

      <BaseTable v-else :columns="columns" :rows="rows" row-key="user_id" :aria-label="t('llcMembers.title')" :actions-label="t('llcMembers.colActions')">
        <template #cell-display_name="{ value }">
          <span class="members-name">{{ value }}</span>
        </template>
        <template #cell-role="{ value }">
          <BaseBadge size="sm" :variant="roleBadgeVariant(String(value))">
            {{ roleLabel(String(value)) }}
          </BaseBadge>
        </template>
        <template #cell-role_control="{ row }">
          <select
            class="members-select members-role-select"
            :aria-label="t('llcMembers.changeRole', { name: row.display_name })"
            :value="row.role"
            :disabled="pendingUserId !== null || !canChangeRole(grantableRoles, String(row.role))"
            :aria-describedby="canChangeRole(grantableRoles, String(row.role)) ? undefined : hintId(row)"
            @change="onRoleChange(row as unknown as Member, $event)"
          >
            <option
              v-for="role in MEMBERSHIP_ROLES"
              :key="role"
              :value="role"
              :disabled="!canGrantRole(grantableRoles, role, String(row.role))"
            >
              {{ roleLabel(role) }}
            </option>
          </select>
          <span v-if="!canChangeRole(grantableRoles, String(row.role))" :id="hintId(row)" class="sr-only">
            {{ t('llcMembers.roleNotGrantable') }}
          </span>
        </template>
        <template #actions="{ row }">
          <BaseButton
            variant="error"
            size="sm"
            :loading="pendingUserId === row.user_id"
            :disabled="pendingUserId !== null"
            @click="confirmRemove(row as unknown as Member)"
          >
            {{ t('llcMembers.remove') }}
          </BaseButton>
        </template>
      </BaseTable>
    </template>

    <!-- Add member modal -->
    <BaseModal
      :close-label="t('ui.modal.closeDialog')"
      v-model="showAddModal"
      :title="t('llcMembers.addModalTitle')"
      size="md"
    >
      <BaseAlert variant="error" v-if="addError" :message="addError" class="members-error" dismissible :dismiss-label="t('common.dismiss')" />

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
              {{ displayNameOf(u) }} ({{ u.email }})
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
          <select id="member-role-select" v-model="roleModel" class="members-select" :disabled="!canAdd">
            <option v-for="role in addRoleOptions" :key="role" :value="role">
              {{ roleLabel(role) }}
            </option>
          </select>
          <p v-if="!canAdd" class="members-hint">{{ t('llcMembers.addNotAllowed') }}</p>
        </div>
      </div>

      <template #actions>
        <BaseButton variant="secondary" :disabled="isAdding" @click="showAddModal = false">
          {{ t('llcMembers.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          :loading="isAdding"
          :disabled="!selectedUserId || isAdding || !canAdd"
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
import { displayNameOf } from '@/utils/displayName'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useCompanyMembers, canChangeRole, canGrantRole, rolesToOffer, type Member } from '@/composables/llc/useCompanyMembers'
import { useCollaborationInvite } from '@/composables/collaboration/useCollaborationInvite'
import { BaseAlert, BaseBadge, BaseButton, BaseCard, BaseModal, BaseTable, type BaseTableColumn } from '@autobot/ui'

// Backend MembershipRole enum (autobot-backend/llc/models/enums.py).
const MEMBERSHIP_ROLES = ['owner', 'admin', 'member', 'guest', 'lead'] as const
type MembershipRole = (typeof MEMBERSHIP_ROLES)[number]

const logger = createLogger('MembersView')
const api = useApiClient()
const route = useRoute()
const { t } = useI18n()

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const { members, grantableRoles, standingKnown, isLoading, errorMessage, pendingUserId, load: fetchMembers, changeRole, removeMember } =
  useCompanyMembers(api, () => companyId.value)
// BaseTable rows are plain records; Member carries no index signature.
const rows = computed(() => members.value.map((m) => ({ ...m })))
const columns = computed<BaseTableColumn[]>(() => [
  { key: 'display_name', label: t('llcMembers.colName') },
  { key: 'role', label: t('llcMembers.colRole') },
  { key: 'role_control', label: t('llcMembers.colChangeRole') },
])

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

function roleBadgeVariant(role: string): 'primary' | 'success' | 'warning' | 'neutral' {
  switch (role) {
    case 'owner':
      return 'primary'
    case 'admin':
    case 'lead':
      return 'success'
    case 'guest':
      return 'warning'
    default:
      return 'neutral'
  }
}

// The add form offers what the server would let the viewer grant (an empty company has no standing: all).
const addRoleOptions = computed(() => rolesToOffer(MEMBERSHIP_ROLES, grantableRoles.value, standingKnown.value))
const canAdd = computed(() => addRoleOptions.value.length > 0)
const hintId = (row: Record<string, unknown>) => `members-role-hint-${String(row.user_id)}`

function openAddModal(): void {
  selectedUserId.value = ''
  const offered = addRoleOptions.value
  selectedRole.value = offered.includes('member') ? 'member' : (offered[0] ?? 'member')
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
    addError.value = (err as { status?: number })?.status === 403 ? t('llcMembers.roleChangeForbidden') : t('llcMembers.addError')
  } finally {
    isAdding.value = false
  }
}

async function confirmRemove(member: Member): Promise<void> {
  if (!window.confirm(t('llcMembers.confirmRemove', { name: member.display_name }))) return
  await removeMember(member)
}

// A refusal puts the select back on the role the row still has.
async function onRoleChange(member: Member, event: Event): Promise<void> {
  const select = event.target as HTMLSelectElement
  const newRole = select.value
  if (newRole === member.role || !isMembershipRole(newRole)) return
  if (!(await changeRole(member, newRole))) select.value = member.role
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
