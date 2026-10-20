<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * RestartConfirmDialog - Restart confirmation modal (Issue #850 Phase 2)
 *
 * Confirmation dialog for restarting services (single or all).
 * Used across orchestration views for consistent confirmation UX.
 */

import { BaseModal } from '@autobot/ui'

interface Props {
  show: boolean
  title?: string
  message: string
  confirmButtonText?: string
  isProcessing?: boolean
}

withDefaults(defineProps<Props>(), {
  title: 'Confirm Action',
  confirmButtonText: 'Confirm',
  isProcessing: false,
})

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<template>
  <BaseModal
    :model-value="show"
    :title="title"
    size="sm"
    :locked="isProcessing"
    :close-label="$t('addNodeModal.closeDialogAria')"
    @close="emit('cancel')"
  >
    <template #title>
      <svg class="inline w-6 h-6 mr-2 align-text-bottom text-warning-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      {{ title }}
    </template>
    <div class="text-sm text-gray-600" v-html="message"></div>

    <template #actions>
      <button
        @click="emit('cancel')"
        :disabled="isProcessing"
        class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
      >
        {{ $t('orchestration.restartConfirmDialog.cancel') }}
      </button>
      <button
        @click="emit('confirm')"
        :disabled="isProcessing"
        class="px-4 py-2 text-sm font-medium text-white bg-orange-600 rounded-lg hover:bg-orange-700 disabled:opacity-50 flex items-center gap-2"
      >
        <svg
          v-if="isProcessing"
          class="w-4 h-4 animate-spin"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        {{ confirmButtonText }}
      </button>
    </template>
  </BaseModal>
</template>
