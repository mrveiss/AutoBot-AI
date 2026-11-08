<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #14549: the canvas shows the attachment (role, workflow) it draws a process node from; attach reaches from this form,
  detach from the node itself. A mutation control, not a view filter (it ignores the role lens).
  The parent owns the request and its in-flight/error state; this only collects the two values
  (v-model) and announces `attach`. Shown to an owner/admin only (#20682), which the parent decides.
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'

defineProps<{
  roles: { id: string; name: string }[]
  /** The roles request did not answer, which is not the same as "none" (#14064). */
  rolesFailed: boolean
  /** A process mutation is in flight; the form is read-only until it settles. */
  busy: boolean
}>()
const emit = defineEmits<{ (e: 'attach'): void }>()
const roleId = defineModel<string>('roleId', { default: '' })
const workflowId = defineModel<string>('workflowId', { default: '' })
const { t } = useI18n()
</script>

<template>
  <div
    class="flex flex-wrap items-end gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
    data-testid="process-attach-form"
  >
    <div class="flex flex-col gap-1">
      <label for="process-attach-role" class="text-xs text-autobot-text-secondary">
        {{ t('llc.orgChart.attachRoleLabel') }}
      </label>
      <select
        id="process-attach-role"
        v-model="roleId"
        :disabled="busy"
        class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
        data-testid="process-attach-role-select"
      >
        <option value="">{{ t('llc.orgChart.attachRolePlaceholder') }}</option>
        <option v-for="role in roles" :key="role.id" :value="role.id">
          {{ role.name }}
        </option>
      </select>
      <!-- Stated, not implied: an empty dropdown alone would read as "this
           company has no roles" when the request simply did not answer. -->
      <p
        v-if="rolesFailed"
        class="text-xs text-autobot-text-muted"
        data-testid="process-attach-roles-unavailable"
      >
        {{ t('llc.orgChart.attachRolesUnavailable') }}
      </p>
    </div>
    <div class="flex flex-col gap-1">
      <label for="process-attach-workflow" class="text-xs text-autobot-text-secondary">
        {{ t('llc.orgChart.attachWorkflowLabel') }}
      </label>
      <input
        id="process-attach-workflow"
        v-model="workflowId"
        type="text"
        :disabled="busy"
        :placeholder="t('llc.orgChart.attachWorkflowPlaceholder')"
        class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
        data-testid="process-attach-workflow-input"
      />
    </div>
    <BaseButton
      variant="primary"
      data-testid="process-attach-submit"
      :disabled="!roleId || !workflowId.trim() || busy"
      @click="emit('attach')"
    >
      {{ t('llc.orgChart.attach') }}
    </BaseButton>
  </div>
</template>
