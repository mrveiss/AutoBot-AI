<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import Icon from '@/components/ui/Icon.vue'
import { usePairingQR } from '@/composables/usePairingQR'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('PairDeviceDialog')

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  paired: []
}>()

const {
  loading,
  error,
  qrDataUrl,
  isExpired,
  formattedTime,
  isPaired,
  fetchChallenge,
  reset,
} = usePairingQR()

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      fetchChallenge()
    } else {
      reset()
    }
  },
  { immediate: true }
)

watch(isPaired, (paired) => {
  if (paired) {
    logger.info('Device paired, closing dialog')
    emit('paired')
    emit('update:modelValue', false)
  }
})
</script>

<template>
  <BaseModal
    :model-value="modelValue"
    :title="$t('mobile.pairing.title')"
    size="md"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="p-6 space-y-4">
      <!-- Loading State -->
      <div v-if="loading" class="flex flex-col items-center justify-center py-8">
        <Icon name="spinner" :spin="true" class="text-autobot-primary mb-4 text-3xl" />
        <p class="text-autobot-text-secondary text-sm">{{ $t('mobile.pairing.generating') }}</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="flex flex-col items-center justify-center py-8 gap-3">
        <Icon name="exclamation-triangle" class="text-red-500 text-3xl" />
        <p class="text-red-600 text-sm text-center">{{ error }}</p>
        <button
          type="button"
          class="px-4 py-2 bg-autobot-primary text-white rounded-md text-sm hover:opacity-90 transition-opacity"
          @click="fetchChallenge()"
        >
          {{ $t('mobile.pairing.retry') }}
        </button>
      </div>

      <!-- QR Code Display -->
      <template v-else-if="qrDataUrl">
        <div class="text-center space-y-1">
          <p class="text-autobot-text-primary font-medium">{{ $t('mobile.pairing.instructions') }}</p>
          <p class="text-sm text-autobot-text-secondary">{{ $t('mobile.pairing.instructionsDetail') }}</p>
        </div>

        <div class="flex justify-center bg-white p-4 rounded-lg border border-autobot-border">
          <img
            :src="qrDataUrl"
            :alt="$t('mobile.pairing.instructions')"
            class="w-64 h-64"
          />
        </div>

        <!-- Countdown Timer -->
        <div class="flex justify-center">
          <div
            class="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium"
            :class="isExpired ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'"
          >
            <Icon name="clock" />
            <span class="font-mono">
              {{ isExpired ? $t('mobile.pairing.expired') : formattedTime }}
            </span>
          </div>
        </div>

        <!-- Refresh Button (shown when expired) -->
        <div v-if="isExpired" class="flex justify-center">
          <button
            type="button"
            class="inline-flex items-center gap-2 px-6 py-2 bg-autobot-primary text-white rounded-md text-sm hover:opacity-90 transition-opacity"
            @click="fetchChallenge()"
          >
            <Icon name="sync" />
            {{ $t('mobile.pairing.refresh') }}
          </button>
        </div>
      </template>
    </div>

    <template #actions>
      <button
        type="button"
        class="px-4 py-2 bg-autobot-bg-secondary text-autobot-text-primary rounded-md text-sm hover:bg-autobot-bg-tertiary transition-colors"
        @click="$emit('update:modelValue', false)"
      >
        {{ $t('common.close') }}
      </button>
    </template>
  </BaseModal>
</template>
