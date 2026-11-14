<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ScheduleTimeField — 24-hour time as two selects (hour, minute), the
  SchedulePicker's time control (#18432). Labels come from the app.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { joinTime, splitTime } from '../schedule/time'

const props = defineProps<{
  modelValue: string
  hourLabel: string
  minuteLabel: string
  idPrefix: string
  /** Minute choices; defaults to 0–59. */
  minutes?: number[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const parts = computed(() => splitTime(props.modelValue) ?? [0, 0])
const HOURS = Array.from({ length: 24 }, (_, i) => i)
const minuteChoices = computed(() => props.minutes ?? Array.from({ length: 60 }, (_, i) => i))

function set(h: number, m: number): void {
  emit('update:modelValue', joinTime(h, m))
}
const pad = (n: number): string => (n < 10 ? `0${n}` : String(n))
</script>

<template>
  <span class="aui-time">
    <label class="aui-sr-only" :for="`${idPrefix}-h`">{{ hourLabel }}</label>
    <select :id="`${idPrefix}-h`" class="aui-field" :value="parts[0]" @change="set(Number(($event.target as HTMLSelectElement).value), parts[1])">
      <option v-for="h in HOURS" :key="h" :value="h">{{ pad(h) }}</option>
    </select>
    <span aria-hidden="true">:</span>
    <label class="aui-sr-only" :for="`${idPrefix}-m`">{{ minuteLabel }}</label>
    <select :id="`${idPrefix}-m`" class="aui-field" :value="parts[1]" @change="set(parts[0], Number(($event.target as HTMLSelectElement).value))">
      <option v-for="m in minuteChoices" :key="m" :value="m">{{ pad(m) }}</option>
    </select>
  </span>
</template>

<style scoped>
.aui-time {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
}
.aui-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}
.aui-field {
  padding: var(--aui-space-1) var(--aui-space-2);
  border: 1px solid var(--aui-color-border-strong);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
}
.aui-field:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 1px;
}
</style>
