<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Platform admin status for one user (#20670). Calls PUT /users/{id}/admin, the only route that
  changes admin status; the role select changes permissions only. Removing admin status asks for
  confirmation first. The last-admin rule (#21018) is enforced by the backend, which sees every
  account; its refusal is shown here in words.
-->
<template>
  <span class="admin-status-control">
    <BaseSwitch
      :model-value="user.is_platform_admin"
      :label="t('adminUsers.adminStatusLabel', { username: user.username })"
      :disabled="saving"
      size="sm"
      @change="onToggle"
    />
    <BaseModal
      :model-value="confirming"
      role="alertdialog"
      :title="t('adminUsers.revokeAdminTitle')"
      :close-label="t('ui.modal.closeDialog')"
      size="sm"
      @close="confirming = false"
    >
      <p>{{ isSelf ? t('adminUsers.revokeAdminSelf') : t('adminUsers.revokeAdminConfirm', { username: user.username }) }}</p>
      <template #actions>
        <BaseButton variant="secondary" size="sm" @click="confirming = false">{{ t('common.cancel') }}</BaseButton>
        <BaseButton variant="error" size="sm" :disabled="saving" @click="confirmRevoke">
          {{ t('adminUsers.revokeAdminAction') }}
        </BaseButton>
      </template>
    </BaseModal>
  </span>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseModal, BaseSwitch, httpErrorText, isHttpError } from '@autobot/ui'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const props = defineProps<{
  user: { id: string; username: string; is_platform_admin: boolean }
  /** The signed-in admin is looking at their own row: removing admin signs them out of this page. */
  isSelf: boolean
}>()
/** `changed` fires after every attempt, so the list is re-read; `failure` is the text to show, or null. */
const emit = defineEmits<{ changed: [failure: string | null] }>()

const { t } = useI18n()
const logger = createLogger('AdminStatusControl')
const saving = ref(false)
const confirming = ref(false)

/** The #21018 refusal codes (autobot_shared/user_management/last_platform_admin.py), worded for a person. */
const LAST_ADMIN_TEXT: Record<string, string> = {
  last_platform_admin: 'adminUsers.adminStatusLastAdmin',
  last_platform_admin_retry: 'adminUsers.adminStatusRetry',
}

function failureText(err: unknown): string {
  const detail = isHttpError(err) ? err.details?.detail : null
  const code = detail && typeof detail === 'object' ? (detail as { code?: unknown }).code : null
  const key = typeof code === 'string' ? LAST_ADMIN_TEXT[code] : undefined
  return key ? t(key) : httpErrorText(err, t('adminUsers.adminStatusFailed'))
}

async function setAdmin(isPlatformAdmin: boolean): Promise<void> {
  saving.value = true
  let failure: string | null = null
  try {
    await apiClient.call('put', '/api/user-management/users/{user_id}/admin', {
      path: { user_id: props.user.id },
      body: { is_platform_admin: isPlatformAdmin },
    })
  } catch (err) {
    logger.error('Failed to change admin status:', err)
    failure = failureText(err)
  } finally {
    saving.value = false
    confirming.value = false
  }
  emit('changed', failure)
}

function onToggle(next: boolean): void {
  if (next) {
    void setAdmin(true)
    return
  }
  confirming.value = true
}

function confirmRevoke(): void {
  void setAdmin(false)
}
</script>

<style scoped>
.admin-status-control {
  display: inline-flex;
  align-items: center;
}
</style>
