<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025-2026 mrveiss
// Author: mrveiss

/**
 * CodeRollbackPanel - deploy an earlier commit through the updater (#20214).
 *
 * The operator picks a commit from a list of dates and subjects (never an id), reviews what the
 * rollback will do and whether a database migration is in the way, and confirms. The rollback then
 * runs as the same update-all job Update Everything creates, so the parent adopts the job it
 * receives in `started` and polls it exactly as it does for Update Everything.
 */

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, BaseModal, BaseSelectMenu } from '@autobot/ui'
import { formatFleetDateTime } from '@/composables/useTimezone'
import { useCodeRollback } from '@/composables/useCodeRollback'
import type { UpdateAllJob } from '@/composables/useCodeSync'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ started: [job: UpdateAllJob] }>()

const { t } = useI18n()
const rollback = useCodeRollback()

const selected = ref<string | undefined>(undefined)
const showConfirm = ref(false)

const options = computed(() =>
  (rollback.candidates.value?.commits ?? []).map((c) => ({
    value: c.commit,
    label: t(c.is_deployed ? 'codeRollback.optionRunning' : 'codeRollback.option', {
      date: formatFleetDateTime(c.date),
      subject: c.subject,
    }),
    disabled: c.is_deployed,
  })),
)

const chosen = computed(() => rollback.preview.value?.commit ?? null)
const blocking = computed(() => (rollback.preview.value?.checks ?? []).filter((c) => c.status !== 'clear'))
const allowed = computed(() => rollback.preview.value?.allowed === true)
const failureText = computed(() => (rollback.failed.value ? (rollback.error.value ?? t('codeRollback.requestFailed')) : null))

async function review(): Promise<void> {
  if (!selected.value) return
  const result = await rollback.loadPreview(selected.value)
  showConfirm.value = result !== null
}

async function confirm(): Promise<void> {
  if (!selected.value) return
  const job = await rollback.start(selected.value)
  if (job) {
    showConfirm.value = false
    rollback.reset()
    emit('started', job)
  }
}

function cancel(): void {
  showConfirm.value = false
  rollback.reset()
}

onMounted(() => rollback.loadCandidates())
</script>

<template>
  <BaseCard :title="$t('codeRollback.title')" :subtitle="$t('codeRollback.description')">
    <BaseAlert v-if="failureText" variant="error" size="compact" class="mb-3" :message="failureText" />
    <p v-if="!rollback.loading.value && options.length === 0 && !failureText" class="text-sm text-gray-500">
      {{ $t('codeRollback.empty') }}
    </p>
    <div v-else class="flex items-center gap-3">
      <BaseSelectMenu
        v-model="selected"
        :options="options"
        :label="$t('codeRollback.pickerLabel')"
        :placeholder="$t('codeRollback.pickerPlaceholder')"
        :disabled="props.disabled || rollback.loading.value"
      />
      <BaseButton
        variant="secondary"
        :disabled="!selected || props.disabled"
        :loading="rollback.checking.value"
        @click="review"
      >
        {{ $t('codeRollback.review') }}
      </BaseButton>
    </div>

    <BaseModal
      v-model="showConfirm"
      :title="allowed ? $t('codeRollback.confirmTitle') : $t('codeRollback.refusedTitle')"
      size="md"
      :close-label="$t('ui.modal.closeDialog')"
      :locked="rollback.starting.value"
      @close="cancel"
    >
      <p v-if="chosen" class="mb-3 text-sm font-medium">
        {{ $t('codeRollback.option', { date: formatFleetDateTime(chosen.date), subject: chosen.subject }) }}
      </p>
      <template v-if="allowed">
        <p class="text-sm">{{ $t('codeRollback.willDo') }}</p>
        <ul class="mt-2 list-disc pl-5 text-sm space-y-1">
          <li>{{ $t('codeRollback.stepFetch') }}</li>
          <li>{{ $t('codeRollback.stepSlm') }}</li>
          <li>{{ $t('codeRollback.stepFleet') }}</li>
          <li>{{ $t('codeRollback.stepMigrations') }}</li>
          <li>{{ $t('codeRollback.stepLatest') }}</li>
        </ul>
      </template>
      <template v-else>
        <BaseAlert variant="error" size="compact" :message="rollback.preview.value?.refusal ?? $t('codeRollback.requestFailed')" />
        <ul class="mt-3 text-sm space-y-1">
          <li v-for="check in blocking" :key="check.database">
            <span class="font-medium">{{ check.database }}:</span> {{ check.message }}
            <span v-if="check.in_the_way?.length"> ({{ check.in_the_way.join(', ') }})</span>
          </li>
        </ul>
      </template>
      <BaseAlert v-if="failureText && allowed" variant="error" size="compact" class="mt-3" :message="failureText" />
      <template #actions>
        <BaseButton variant="ghost" :disabled="rollback.starting.value" @click="cancel">
          {{ allowed ? $t('codeRollback.cancel') : $t('codeRollback.close') }}
        </BaseButton>
        <BaseButton v-if="allowed" variant="warning" :loading="rollback.starting.value" @click="confirm">
          {{ $t('codeRollback.confirm') }}
        </BaseButton>
      </template>
    </BaseModal>
  </BaseCard>
</template>
