<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #14549: the canvas shows the attachment (role, workflow) it draws a process node from; attach reaches from this form,
  detach from the node itself. A mutation control, not a view filter (it ignores the role lens).
  The parent owns the request and its in-flight/error state; this only collects the two values
  (v-model) and announces `attach`. Shown to an owner/admin only (#20682), which the parent decides.

  #21242: the workflow is chosen from the company's workflows (a select, not a typed id), and
  "New workflow" opens the create modal; a workflow made there is chosen in the select, attachable
  without a reload because the modal creates through the same service the select reads.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseSelectMenu } from '@autobot/ui'
import type { CompanyWorkflowsService } from '@/composables/llc/useCompanyWorkflows'
import CompanyWorkflowCreateModal from './CompanyWorkflowCreateModal.vue'

const props = defineProps<{
  roles: { id: string; name: string }[]
  /** The roles request did not answer, which is not the same as "none" (#14064). */
  rolesFailed: boolean
  /** A process mutation is in flight; the form is read-only until it settles. */
  busy: boolean
  companyId: string
  /** The company's workflows: the select reads them, the modal creates through it. */
  service: CompanyWorkflowsService
  /** Workflow ids already attached to the chosen role; they stay listed, disabled. */
  attachedIds: string[]
}>()
const emit = defineEmits<{ (e: 'attach'): void }>()
const roleId = defineModel<string>('roleId', { default: '' })
const workflowId = defineModel<string>('workflowId', { default: '' })
const { t } = useI18n()

const showCreate = ref(false)
const roleOptions = computed(() => props.roles.map((r) => ({ value: r.id, label: r.name })))
const workflowOptions = computed(() =>
  props.service.attachable(props.attachedIds).map((o) => ({ value: o.id, label: o.label, disabled: o.disabled })),
)
const workflowsReady = computed(() => props.service.state.value === 'ready')
const working = computed(() => props.busy || props.service.pending.value)

function onCreated(id: string): void {
  workflowId.value = id
  showCreate.value = false
}
</script>

<template>
  <div
    class="flex flex-wrap items-end gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
    data-testid="process-attach-form"
  >
    <div class="flex flex-col gap-1">
      <span class="text-xs text-autobot-text-secondary">{{ t('llc.orgChart.attachRoleLabel') }}</span>
      <div data-testid="process-attach-role-select">
        <BaseSelectMenu
          v-model="roleId"
          :options="roleOptions"
          :label="t('llc.orgChart.attachRoleLabel')"
          :placeholder="t('llc.orgChart.attachRolePlaceholder')"
          :disabled="busy"
        />
      </div>
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
      <span class="text-xs text-autobot-text-secondary">{{ t('llc.orgChart.attachWorkflowLabel') }}</span>
      <div data-testid="process-attach-workflow-select">
        <BaseSelectMenu
          v-model="workflowId"
          :options="workflowOptions"
          :label="t('llc.orgChart.attachWorkflowLabel')"
          :placeholder="t('llc.workflows.pickerPlaceholder')"
          :disabled="working || !workflowsReady || workflowOptions.length === 0"
        />
      </div>
      <p
        v-if="service.state.value === 'failed'"
        class="text-xs text-autobot-text-muted"
        data-testid="process-attach-workflows-unavailable"
      >
        {{ t('llc.orgChart.workflowsUnavailable') }}
      </p>
    </div>
    <BaseButton
      variant="primary"
      data-testid="process-attach-submit"
      :disabled="!roleId || !workflowId || working"
      @click="emit('attach')"
    >
      {{ t('llc.orgChart.attach') }}
    </BaseButton>
    <BaseButton variant="outline" data-testid="process-attach-new-workflow" :disabled="working" @click="showCreate = true">
      {{ t('llc.workflows.newWorkflow') }}
    </BaseButton>
    <CompanyWorkflowCreateModal
      v-model="showCreate"
      :company-id="companyId"
      :service="service"
      @close="showCreate = false"
      @created="onCreated"
    />
  </div>
</template>
