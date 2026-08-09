# PairDeviceDialog Component Design

## Overview

Build a QR code pairing dialog component that allows users to pair mobile devices with their AutoBot account using a time-limited challenge token.

## Backend API (Already Exists)

**Endpoint**: `GET /api/devices/pair-qr`
- Returns: `{ challenge_token: string, expires_in_seconds: 300 }`
- Auth: Requires current user session
- TTL: 5 minutes (300 seconds)

**Endpoint**: `POST /api/devices/pair` (called by mobile app, not this dialog)

## Architecture

### Files to Create

1. **`autobot-frontend/src/composables/usePairingQR.ts`**
   - Handles QR challenge lifecycle
   - Generates QR code data URL
   - Manages countdown timer
   - Detects device pairing completion

2. **`autobot-frontend/src/components/mobile/PairDeviceDialog.vue`**
   - Dialog UI with QR code display
   - Countdown timer display
   - Refresh button on expiry
   - Auto-close on pairing success

## Composable Design: `usePairingQR.ts`

```typescript
import { ref, computed, onUnmounted } from 'vue'
import QRCode from 'qrcode'
import { createLogger } from '@/utils/debugUtils'
import { getApiClient } from '@/utils/ApiClient'

interface QRChallengeResponse {
  challenge_token: string
  expires_in_seconds: number
}

export function usePairingQR() {
  const logger = createLogger('usePairingQR')
  const apiClient = getApiClient()
  
  // State
  const challengeToken = ref<string | null>(null)
  const qrDataUrl = ref<string | null>(null)
  const expiresInSeconds = ref<number>(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const isPaired = ref(false)
  
  // Computed
  const isExpired = computed(() => expiresInSeconds.value <= 0)
  const minutesRemaining = computed(() => Math.floor(expiresInSeconds.value / 60))
  const secondsRemaining = computed(() => expiresInSeconds.value % 60)
  const formattedTime = computed(() => 
    `${minutesRemaining.value}:${secondsRemaining.value.toString().padStart(2, '0')}`
  )
  
  // Timers
  let countdownInterval: number | null = null
  let pairingCheckInterval: number | null = null
  
  // Methods
  async function fetchChallenge() {
    loading.value = true
    error.value = null
    
    try {
      const response = await apiClient.get('/devices/pair-qr')
      challengeToken.value = response.challenge_token
      expiresInSeconds.value = response.expires_in_seconds
      
      // Generate QR code
      const qrUrl = `autobot://pair?token=${response.challenge_token}`
      qrDataUrl.value = await QRCode.toDataURL(qrUrl, {
        width: 300,
        margin: 2,
        color: {
          dark: '#000000',
          light: '#FFFFFF'
        }
      })
      
      // Start countdown
      startCountdown()
      
      // Start polling for pairing completion
      startPairingCheck()
      
      logger.info('QR challenge fetched successfully')
    } catch (err) {
      error.value = 'Failed to generate QR code. Please try again.'
      logger.error('Failed to fetch QR challenge:', err)
    } finally {
      loading.value = false
    }
  }
  
  function startCountdown() {
    stopCountdown()
    countdownInterval = window.setInterval(() => {
      if (expiresInSeconds.value > 0) {
        expiresInSeconds.value--
      } else {
        stopCountdown()
      }
    }, 1000)
  }
  
  function stopCountdown() {
    if (countdownInterval !== null) {
      clearInterval(countdownInterval)
      countdownInterval = null
    }
  }
  
  async function startPairingCheck() {
    stopPairingCheck()
    // Poll every 2 seconds to check if device was paired
    pairingCheckInterval = window.setInterval(async () => {
      try {
        const devices = await apiClient.get('/devices')
        // If device count increased, pairing succeeded
        // (More robust: check for device with matching token, but backend doesn't expose that)
        // For now, trust that any new device during the challenge window is the paired one
        if (devices.devices && devices.devices.length > 0) {
          // Check if any device was created in the last 10 seconds
          const recentDevice = devices.devices.find((d: any) => {
            const createdAt = new Date(d.created_at)
            const now = new Date()
            return (now.getTime() - createdAt.getTime()) < 10000 // 10 seconds
          })
          
          if (recentDevice) {
            isPaired.value = true
            stopPairingCheck()
            stopCountdown()
            logger.info('Device paired successfully')
          }
        }
      } catch (err) {
        logger.warn('Pairing check failed:', err)
      }
    }, 2000)
  }
  
  function stopPairingCheck() {
    if (pairingCheckInterval !== null) {
      clearInterval(pairingCheckInterval)
      pairingCheckInterval = null
    }
  }
  
  function reset() {
    stopCountdown()
    stopPairingCheck()
    challengeToken.value = null
    qrDataUrl.value = null
    expiresInSeconds.value = 0
    error.value = null
    isPaired.value = false
  }
  
  // Cleanup on unmount
  onUnmounted(() => {
    stopCountdown()
    stopPairingCheck()
  })
  
  return {
    // State
    challengeToken,
    qrDataUrl,
    expiresInSeconds,
    loading,
    error,
    isPaired,
    
    // Computed
    isExpired,
    formattedTime,
    
    // Methods
    fetchChallenge,
    reset
  }
}
```

## Component Design: `PairDeviceDialog.vue`

```vue
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
            class="px-6 py-2 bg-autobot-primary text-white rounded-md hover:bg-autobot-primary-dark transition-colors"
            @click="pairing.fetchChallenge()"
          >
            <Icon name="sync" class="mr-2" />
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

<script setup lang="ts">
import { watch, onMounted } from 'vue'
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
```

## Integration Points

### 1. i18n Keys (add to locales)

```json
{
  "mobile": {
    "pairing": {
      "title": "Pair Mobile Device",
      "instructions": "Scan this QR code with your mobile device",
      "instructionsDetail": "Open the AutoBot mobile app and scan this code to pair your device",
      "generating": "Generating QR code...",
      "expired": "Expired",
      "refresh": "Get New Code",
      "retry": "Try Again"
    }
  }
}
```

### 2. Router Integration (if needed)

Add route in `autobot-frontend/src/router/index.ts` if the dialog needs a dedicated page.

### 3. Usage Example

```vue
<template>
  <div>
    <button @click="showPairingDialog = true">
      Pair Mobile Device
    </button>
    
    <PairDeviceDialog
      v-model="showPairingDialog"
      @paired="handleDevicePaired"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PairDeviceDialog from '@/components/mobile/PairDeviceDialog.vue'

const showPairingDialog = ref(false)

function handleDevicePaired() {
  console.log('Device successfully paired!')
  // Refresh device list, show notification, etc.
}
</script>
```

## Accessibility

- Focus trap within dialog (inherited from BaseModal)
- ESC key to close (inherited from BaseModal)
- Proper ARIA labels on all interactive elements
- Alt text on QR code image
- Keyboard navigation support

## Error Handling

1. **Network failures**: Show retry button with error message
2. **QR generation failures**: Log error, show retry option
3. **Timeout/expiry**: Show refresh button with clear messaging
4. **Pairing check failures**: Log warning, continue checking (non-blocking)

## Testing Checklist

- [ ] QR code displays correctly with challenge token
- [ ] Countdown timer decrements every second
- [ ] Timer shows expired state at 0:00
- [ ] Refresh button appears when expired
- [ ] Refresh button fetches new challenge
- [ ] Dialog auto-closes when device is paired
- [ ] Error state shows retry button
- [ ] Loading state shows spinner
- [ ] Modal closes on ESC key
- [ ] Modal closes on overlay click
- [ ] Focus trap works correctly
- [ ] i18n strings display correctly

## Dependencies

```bash
npm install --save qrcode
npm install --save-dev @types/qrcode
```

## Acceptance Criteria

- ✅ QR code displays challenge token embedded in `autobot://pair?token=...` URL
- ✅ Countdown timer shows remaining time (MM:SS format)
- ✅ Dialog auto-closes when device paired (detected via polling `/api/devices`)
- ✅ Refresh button appears when timer expires
- ✅ Error handling with retry capability
- ✅ Accessibility features from BaseModal (focus trap, ESC close, ARIA)

## Reference

- Backend API: `autobot-backend/api/mobile_devices.py`
- Parent Issue: [MVA-2905](/MVA/issues/MVA-2905)
- GitHub Issue: https://github.com/mrveiss/AutoBot-AI/issues/4463
