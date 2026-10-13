<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SchedulePickerField — the app's wiring of the shared kit SchedulePicker
  (#18432): supplies the i18n translator. No server preview yet (backend half
  of #18432), so the kit keeps the picker cron-only. This is
  the ONE picker entry point for Routines, the workflow Schedule trigger and
  the automation setup; do not instantiate the kit component directly.
-->
<script setup lang="ts">
import { SchedulePicker, type ScheduleSpec } from '@autobot/ui'
import { useScheduleI18n } from '@/composables/useSchedule'

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
</script>

<template>
  <SchedulePicker
    :model-value="modelValue"
    :translate="translate"
    :locale="locale"
    :company-timezone="companyTimezone"
    :default-timezone="companyTimezone ?? 'UTC'"
    @update:model-value="emit('update:modelValue', $event)"
    @update:valid="emit('update:valid', $event)"
  />
</template>
