<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SchedulePickerField — the app's wiring of the shared kit SchedulePicker
  (#18432): supplies the i18n translator and the server preview call. This is
  the ONE picker entry point for Routines, the workflow Schedule trigger and
  the automation setup; do not instantiate the kit component directly.
-->
<script setup lang="ts">
import { SchedulePicker, type ScheduleSpec } from '@autobot/ui'
import { useScheduleI18n, useSchedulePreviewCall } from '@/composables/useSchedule'

defineProps<{
  modelValue: ScheduleSpec | null
  /** The company's IANA zone, once the company record carries one. */
  companyTimezone?: string
}>()
const emit = defineEmits<{
  'update:modelValue': [spec: ScheduleSpec]
  'update:valid': [valid: boolean]
}>()

const { translate, locale } = useScheduleI18n()
const preview = useSchedulePreviewCall()
</script>

<template>
  <SchedulePicker
    :model-value="modelValue"
    :translate="translate"
    :locale="locale"
    :company-timezone="companyTimezone"
    :default-timezone="companyTimezone ?? 'UTC'"
    :preview="preview"
    @update:model-value="emit('update:modelValue', $event)"
    @update:valid="emit('update:valid', $event)"
  />
</template>
