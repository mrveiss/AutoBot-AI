<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  A user's system role (PUT /users/{id}/role). Roles change permissions only, never platform admin
  status (#20670): `admin` is not offered here and the shown role is the user's own role row, not
  derived from `is_platform_admin`. Admin status has its own control, AdminStatusControl.
-->
<template>
  <!-- Controlled: after a failed PUT /role the list is re-read and the menu snaps back to the stored role. -->
  <BaseSelectMenu
    :model-value="current"
    :options="options"
    :label="t('adminUsers.roleSelectLabel', { username: user.username })"
    size="sm"
    @update:model-value="onRoleChange"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseSelectMenu, httpErrorText, type SelectMenuOption } from '@autobot/ui'
import { ASSIGNABLE_ROLES, DEFAULT_ROLE, isAssignableRole } from '@/constants/roles'
import type { Role } from '@/types/_generated/workflow'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const props = defineProps<{
  user: { id: string; username: string; roles: Array<{ name: string; is_system: boolean }> }
}>()
/** `changed` fires after every attempt, so the list is re-read; `failure` is the text to show, or null. */
const emit = defineEmits<{ changed: [failure: string | null] }>()

const { t } = useI18n()
const logger = createLogger('UserRoleSelect')

const current = computed(() => props.user.roles.find(r => r.is_system)?.name ?? DEFAULT_ROLE)

// #14937: every canonical role has a label, so a role the UI does not assign
// still renders as itself; `Record<Role, ...>` fails to compile when one is added.
const roleLabels = computed<Record<Role, string>>(() => ({
  admin: t('adminUsers.roleAdmin'),
  superadmin: t('adminUsers.roleSuperadmin'),
  operator: t('adminUsers.roleOperator'),
  analyst: t('adminUsers.roleAnalyst'),
  editor: t('adminUsers.roleEditor'),
  user: t('adminUsers.roleUser'),
  readonly: t('adminUsers.roleReadonly'),
}))

function roleLabel(role: string): string {
  return (roleLabels.value as Record<string, string>)[role] ?? role
}

/** The assignable roles; #14937: a role the UI does not assign still shows as itself, disabled, not blank. */
const options = computed<SelectMenuOption[]>(() => [
  ...(isAssignableRole(current.value) ? [] : [{ value: current.value, label: roleLabel(current.value), disabled: true }]),
  ...ASSIGNABLE_ROLES.map(role => ({ value: role, label: roleLabel(role) })),
])

async function onRoleChange(role: string): Promise<void> {
  let failure: string | null = null
  try {
    await apiClient.call('put', '/api/user-management/users/{user_id}/role', {
      path: { user_id: props.user.id },
      body: { role },
    })
  } catch (err) {
    logger.error('Failed to update role:', err)
    failure = httpErrorText(err, t('adminUsers.roleUpdateFailed'))
  }
  emit('changed', failure)
}
</script>
