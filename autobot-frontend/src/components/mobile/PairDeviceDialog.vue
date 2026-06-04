<script setup lang="ts">
/**
 * PairDeviceDialog Component (MVA-3003)
 *
 * QR code pairing dialog for mobile device pairing.
 * Displays a time-limited QR code that the mobile app can scan
 * to pair with the user's account.
 */

import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseModal from '@/components/ui/BaseModal.vue'
import Icon from '@/components/ui/Icon.vue'
import { usePairingQR } from '@/composables/usePairingQR'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()
const logger = createLogger('PairDeviceDialog')

// Props
const props = defineProps<{
  modelValue: boolean
}>()

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'paired': []
}>()

// Composable
const pairing = usePairingQR()

// Fetch challenge when dialog opens
watch(() => props.modelValue, (open) => {
  if (open) {
    pairing.fetchChallenge()
  } else {
    pairing.reset()
  }
}, { immediate: true })

// Auto-close when device is paired
watch(() => pairing.isPaired.value, (paired) => {
  if (paired) {
    logger.info('Device paired, closing dialog')
    emit('paired')
    handleClose()
  }
})

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <BaseModal
    :model-value="modelValue"
    :title="$t('mobile.pairing.title')"
    size="md"
    @update:model-value="handleClose"
  >
    <div class="p-6 space-y-4">
      <!-- Loading State -->
      <div v-if="pairing.loading.value" class="flex flex-col items-center justify-center py-8">
        <Icon name="spinner" :spin="true" size="2x" class="text-autobot-primary mb-4" />
        <p class="text-autobot-text-secondary">{{ $t('mobile.pairing.generating') }}</p>
      </div>

      <!-- Error State -->
      <div v-else-if="pairing.error.value" class="text-center py-8">
        <Icon name="exclamation-triangle" size="2x" class="text-red-500 mb-4" />
        <p class="text-red-600 mb-4">{{ pairing.error.value }}</p>
        <button
          class="px-4 py-2 bg-autobot-primary text-white rounded-md hover:bg-autobot-primary-dark transition-colors"
          @click="pairing.fetchChallenge()"
        >
          {{ $t('mobile.pairing.retry') }}
        </button>
      </div>

      <!-- QR Code Display -->
      <div v-else-if="pairing.qrDataUrl.value" class="space-y-4">
        <!-- Instructions -->
        <div class="text-center">
          <p class="text-autobot-text-primary mb-2">
            {{ $t('mobile.pairing.instructions') }}
          </p>
          <p class="text-sm text-autobot-text-secondary">
            {{ $t('mobile.pairing.instructionsDetail') }}
          </p>
        </div>

        <!-- QR Code -->
        <div class="flex justify-center bg-white p-4 rounded-lg border border-autobot-border">
          <img
            :src="pairing.qrDataUrl.value"
            alt="QR Code for device pairing"
            class="w-64 h-64"
          />
        </div>

        <!-- Countdown Timer -->
        <div class="text-center">
          <div
            class="inline-flex items-center gap-2 px-4 py-2 rounded-full"
            :class="pairing.isExpired.value ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'"
          >
            <Icon :name="pairing.isExpired.value ? 'clock' : 'clock'" />
            <span class="font-mono font-semibold">
              {{ pairing.isExpired.value ? $t('mobile.pairing.expired') : pairing.formattedTime.value }}
            </span>
          </div>
        </div>

        <!-- Refresh Button (shown when expired) -->
        <div v-if="pairing.isExpired.value" class="text-center">
          <button
            class="px-6 py-2 bg-autobot-primary text-white rounded-md hover:bg-autobot-primary-dark transition-colors flex items-center gap-2 mx-auto"
            @click="pairing.fetchChallenge()"
          >
            <Icon name="sync" />
            {{ $t('mobile.pairing.refresh') }}
          </button>
        </div>
      </div>
    </div>

    <template #actions>
      <button
        class="px-4 py-2 bg-autobot-bg-secondary text-autobot-text-primary rounded-md hover:bg-autobot-bg-tertiary transition-colors"
        @click="handleClose"
      >
        {{ $t('common.close') }}
      </button>
    </template>
  </BaseModal>
</template>
