<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #21241: create a company workflow, and (when a role is given) attach it to that role in the same flow.

  The caller owns the request machinery: it passes the `useCompanyWorkflows` service, so the list the
  caller shows is the list the create reloads. The id is asked for rather than derived: the contract
  requires `workflow_id`, no shared id helper exists, and a derived id would be unreadable for a name
  in a script that has no Latin letters.

  Create succeeds and attach fails: the workflow exists (it is already in the picker) and is not
  created again on retry; the form keeps its id and offers the attach alone. Everything after an
  await checks that the company and role captured before it are still the ones shown, so a switch
  mid-flight writes nothing into the new company's form.
-->
<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseInput, BaseModal } from '@autobot/ui'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import { WorkflowWriteError, type CompanyWorkflowsService } from '@/composables/llc/useCompanyWorkflows'
import { createLogger } from '@/utils/debugUtils'

const props = defineProps<{
  modelValue: boolean
  companyId: string
  /** When set, the new workflow is attached to this role right after it is created. */
  roleId?: string
  service: Pick<CompanyWorkflowsService, 'create' | 'attach'>
}>()
const emit = defineEmits<{
  (e: 'close'): void
  /** `attached` is true when a role was given and the attach went through. */
  (e: 'created', workflowId: string, attached: boolean): void
}>()

const logger = createLogger('CompanyWorkflowCreateModal')
const { t } = useI18n()

/** Ties the footer's submit button to the form, so Enter in a field and the button are one submit. */
const formId = `workflow-create-${useId()}`
const workflowId = ref('')
const name = ref('')
const submitting = ref(false)
const error = ref('')
/** Set once the create succeeded, so a retry attaches instead of creating a duplicate. */
const createdId = ref('')

const trimmedId = computed(() => workflowId.value.trim())
const canSubmit = computed(() => !!trimmedId.value && !submitting.value)
const submitLabel = computed(() => {
  if (submitting.value) return t('llc.workflows.working')
  if (createdId.value) return t('llc.workflows.attachCreated')
  return props.roleId ? t('llc.workflows.createAndAttach') : t('common.create')
})

function reset(): void {
  workflowId.value = ''
  name.value = ''
  error.value = ''
  createdId.value = ''
  submitting.value = false
}

// Another company or role: the form's state belongs to the one it was opened for.
watch(
  () => [props.companyId, props.roleId],
  () => {
    reset()
    if (props.modelValue) emit('close')
  },
)

// A closed form starts blank next time; the workflow it created stays in the picker.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) reset()
  },
)

function createFailedMessage(err: unknown): string {
  if (err instanceof WorkflowWriteError && err.forbidden) return t('llc.workflows.createForbidden')
  return describeApiError(err, t('llc.workflows.createFailed'))
}

function failureMessage(err: unknown): string {
  if (!createdId.value) return createFailedMessage(err)
  const detail = describeApiError(err, t('llcRoles.errorAttach'))
  return t('llc.workflows.attachCreatedFailed', { id: createdId.value, detail })
}

/** Create the workflow unless an earlier submit already did. False when the form moved on meanwhile. */
async function createOnce(current: () => boolean): Promise<boolean> {
  if (createdId.value) return true
  const made = await props.service.create({
    workflow_id: trimmedId.value,
    name: name.value.trim() || null,
    status: 'planned',
    kind: 'workflow',
  })
  if (!current()) return false
  createdId.value = made.workflow_id
  return true
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  const company = props.companyId
  const role = props.roleId
  const current = () => company === props.companyId && role === props.roleId
  submitting.value = true
  error.value = ''
  try {
    if (!(await createOnce(current))) return
    if (role) await props.service.attach(role, createdId.value)
    if (!current()) return
    const id = createdId.value
    reset()
    emit('created', id, !!role)
  } catch (err: unknown) {
    logger.error('Create workflow failed', err)
    if (current()) error.value = failureMessage(err)
  } finally {
    if (current()) submitting.value = false
  }
}
</script>

<template>
  <BaseModal
    :model-value="modelValue"
    :title="t('llc.workflows.createTitle')"
    :close-label="t('ui.modal.closeDialog')"
    :width="480"
    :locked="submitting"
    @close="emit('close')"
  >
    <form :id="formId" class="flex flex-col gap-4" data-testid="workflow-create-form" @submit.prevent="submit">
      <BaseInput
        v-model="workflowId"
        type="text"
        maxlength="255"
        required
        :label="t('llc.workflows.fieldId')"
        :helper-text="t('llc.workflows.idHint')"
        :disabled="submitting || !!createdId"
        data-testid="workflow-create-id"
      />
      <BaseInput
        v-model="name"
        type="text"
        maxlength="255"
        :label="t('llc.workflows.fieldName')"
        :disabled="submitting || !!createdId"
        data-testid="workflow-create-name"
      />
      <BaseAlert v-if="error" variant="error" :message="error" data-testid="workflow-create-error" />
    </form>

    <template #actions>
      <BaseButton variant="secondary" :disabled="submitting" @click="emit('close')">{{ t('common.cancel') }}</BaseButton>
      <BaseButton variant="primary" type="submit" :form="formId" :disabled="!canSubmit" data-testid="workflow-create-submit">
        {{ submitLabel }}
      </BaseButton>
    </template>
  </BaseModal>
</template>
