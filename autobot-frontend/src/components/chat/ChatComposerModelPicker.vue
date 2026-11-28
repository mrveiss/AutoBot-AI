<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerModelPicker -- the per-conversation model and provider choice (#11585): "Auto" or one of the
  live models. A native select on the kit tokens (the Chat mockup's `Model` control); advanced (`.adv`).
-->
<template>
  <label class="adv flex max-w-56 shrink-0 items-center gap-2 text-sm text-[var(--aui-color-text-muted)]" :title="$t('chat.modelPicker.title')">
    <span>{{ $t('chat.modelPicker.label') }}</span>
    <select
      :value="modelValue"
      class="h-8 min-w-0 cursor-pointer rounded-[var(--aui-radius-md)] border border-[var(--aui-input-border)] bg-[var(--aui-input-bg)] px-2 text-sm text-[var(--aui-color-text)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--aui-color-focus-ring)] disabled:cursor-not-allowed disabled:opacity-55"
      :disabled="disabled"
      :aria-label="$t('chat.modelPicker.label')"
      @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">{{ $t('chat.modelPicker.auto') }}</option>
      <option v-for="m in models" :key="m.name" :value="m.name">
        {{ m.provider ? `${m.name} · ${m.provider}` : m.name }}
      </option>
    </select>
  </label>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
  models: { name: string; provider?: string }[]
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
