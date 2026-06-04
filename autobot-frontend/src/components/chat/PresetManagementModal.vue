// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<template>
  <BaseModal
    :model-value="modelValue"
    :title="$t('chat.presets.modalTitle')"
    size="md"
    :scrollable="true"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <PresetFormBody id-prefix="preset" />
  </BaseModal>
</template>

<script setup lang="ts">
import BaseModal from '@/components/ui/BaseModal.vue'
import PresetFormBody from '@/components/chat/PresetFormBody.vue'

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
}>()
</script>
