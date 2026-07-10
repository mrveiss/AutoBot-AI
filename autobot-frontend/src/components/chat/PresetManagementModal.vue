// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<template>
  <BaseModal
    :close-label="t('ui.modal.closeDialog')"
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
import { BaseModal } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import PresetFormBody from '@/components/chat/PresetFormBody.vue'
const { t } = useI18n()

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
}>()
</script>
