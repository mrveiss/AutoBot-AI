<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #14597: the tool sibling of the process attach form (a role picker plus a tool name); detach reaches from each
  role chip on the tool node (WorkflowCanvas.vue). Same gating: owner/admin only, not a view filter.
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
  /** A tool mutation is in flight; the form is read-only until it settles. */
  busy: boolean
}>()
const emit = defineEmits<{ (e: 'attach'): void }>()
const roleId = defineModel<string>('roleId', { default: '' })
const toolName = defineModel<string>('toolName', { default: '' })
const { t } = useI18n()
</script>

<template>
  <div
    class="flex flex-wrap items-end gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
    data-testid="tool-attach-form"
  >
    <div class="flex flex-col gap-1">
      <label for="tool-attach-role" class="text-xs text-autobot-text-secondary">
        {{ t('llc.orgChart.attachRoleLabel') }}
      </label>
      <select
        id="tool-attach-role"
        v-model="roleId"
        :disabled="busy"
        class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
        data-testid="tool-attach-role-select"
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
        data-testid="tool-attach-roles-unavailable"
      >
        {{ t('llc.orgChart.attachRolesUnavailable') }}
      </p>
    </div>
    <div class="flex flex-col gap-1">
      <label for="tool-attach-name" class="text-xs text-autobot-text-secondary">
        {{ t('llc.orgChart.attachToolNameLabel') }}
      </label>
      <input
        id="tool-attach-name"
        v-model="toolName"
        type="text"
        :disabled="busy"
        :placeholder="t('llc.orgChart.attachToolNamePlaceholder')"
        class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
        data-testid="tool-attach-name-input"
      />
    </div>
    <BaseButton
      variant="primary"
      data-testid="tool-attach-submit"
      :disabled="!roleId || !toolName.trim() || busy"
      @click="emit('attach')"
    >
      {{ t('llc.orgChart.attach') }}
    </BaseButton>
  </div>
</template>
