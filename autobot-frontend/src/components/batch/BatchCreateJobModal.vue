<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  BatchCreateJobModal — name a new batch job and pick its type (#20644).
  The job types are the backend's own (`BatchJobType`). The screen performs the create; a failure it
  reports comes back in `error` and stays on screen, with the form kept, so the user can try again.
-->
<template>
  <BaseModal
    :model-value="modelValue"
    :title="t('batchJobs.create.title')"
    width="32rem"
    :close-on-overlay="false"
    :close-on-esc="!busy"
    :close-label="t('batchJobs.create.close')"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <form class="flex flex-col gap-4" @submit.prevent="submit">
      <BaseInput v-model="name" :label="t('batchJobs.create.name')" :placeholder="t('batchJobs.create.namePlaceholder')" required />
      <BaseSelectMenu v-model="jobType" :options="typeOptions" :label="t('batchJobs.create.type')" />
      <BaseAlert v-if="error" variant="error" :message="error" />
    </form>
    <template #actions>
      <BaseButton variant="ghost" :disabled="busy" @click="emit('update:modelValue', false)">
        {{ t('batchJobs.create.cancel') }}
      </BaseButton>
      <BaseButton :loading="busy" :disabled="!name.trim()" @click="submit">
        {{ t('batchJobs.create.submit') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseInput, BaseModal, BaseSelectMenu } from '@autobot/ui'
import type { BatchJobType, CreateBatchJobRequest } from '@/types/batch-processing'

const props = defineProps<{ modelValue: boolean; busy?: boolean; error?: string | null }>()
const emit = defineEmits<{ 'update:modelValue': [open: boolean]; create: [request: CreateBatchJobRequest] }>()
const { t } = useI18n()

/** The backend's job types, in its own order (api/schemas_workflows.py BatchJobType). */
const JOB_TYPES: BatchJobType[] = ['data_processing', 'file_conversion', 'report_generation', 'backup', 'custom']

const name = ref('')
const jobType = ref<string>('data_processing')
const typeOptions = computed(() => JOB_TYPES.map((value) => ({ value, label: t(`batchJobs.type.${value}`) })))

// A fresh form each time the dialog opens.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    name.value = ''
    jobType.value = 'data_processing'
  },
)

function submit(): void {
  const trimmed = name.value.trim()
  if (!trimmed || props.busy) return
  emit('create', { name: trimmed, job_type: jobType.value as BatchJobType, parameters: {} })
}
</script>
