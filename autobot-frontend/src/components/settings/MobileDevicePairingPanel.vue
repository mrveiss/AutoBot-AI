<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

MobileDevicePairingPanel.vue — Mobile device pairing via QR code
Issue GH#4463: Mobile device pairing for push notifications and offline sync
-->

<template>
  <div class="mobile-device-pairing-panel">
    <!-- Error banner -->
    <div v-if="error" class="error-banner" role="alert">
      <Icon name="exclamation-triangle" />
      <span>{{ error }}</span>
      <button class="dismiss-btn" @click="clearError" aria-label="Dismiss error">
        <Icon name="times" />
      </button>
    </div>

    <!-- QR Code Generation Section -->
    <div class="qr-section">
      <h3 class="section-title">
        <Icon name="qrcode" />
        Pair a Mobile Device
      </h3>
      <p class="section-description">
        Scan this QR code with your mobile device to pair it with your AutoBot account. You'll receive push
        notifications and can sync conversation state across devices.
      </p>

      <div v-if="!currentQR" class="qr-actions">
        <button class="generate-qr-btn" :disabled="loading" @click="handleGenerateQR">
          <Icon :name="loading ? 'spinner' : 'qrcode'" :spin="loading" />
          {{ loading ? 'Generating...' : 'Generate QR Code' }}
        </button>
      </div>

      <div v-else class="qr-display">
        <div class="qr-code-wrapper">
          <canvas ref="qrCanvas" class="qr-canvas"></canvas>
        </div>
        <p class="qr-hint">Expires in {{ expirySeconds }}s</p>
        <button class="regenerate-btn" @click="handleGenerateQR" :disabled="loading">
          <Icon name="redo" />
          Generate New Code
        </button>
      </div>
    </div>

    <!-- Paired Devices List -->
    <div class="devices-section">
      <h3 class="section-title">
        <Icon name="mobile-alt" />
        Paired Devices
      </h3>
      <p v-if="!hasDevices" class="empty-state">
        No paired devices yet. Scan the QR code above to pair your first device.
      </p>

      <div v-else class="devices-list">
        <div v-for="device in devices" :key="device.id" class="device-card">
          <div class="device-info">
            <div class="device-header">
              <Icon :name="getPlatformIcon(device.platform)" class="device-icon" />
              <span class="device-name">{{ device.device_name }}</span>
              <span class="device-platform">{{ getPlatformLabel(device.platform) }}</span>
            </div>
            <p class="device-meta">
              <span class="meta-item">
                <Icon name="calendar-alt" />
                Paired {{ formatDate(device.created_at) }}
              </span>
              <span v-if="device.last_seen_at" class="meta-item">
                <Icon name="clock" />
                Last seen {{ formatDate(device.last_seen_at) }}
              </span>
            </p>
          </div>
          <button class="delete-device-btn" :disabled="loading" @click="handleDeleteDevice(device.id)" :aria-label="`Delete ${device.device_name}`">
            <Icon name="trash-alt" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import QRCode from 'qrcode'
import Icon from '@/components/ui/Icon.vue'
import { useMobileDevices } from '@/composables/mobile-devices/useMobileDevices'
import { createLogger } from '@/utils/debugUtils'
import { useNotificationBus } from '@/composables/useNotificationBus'

const logger = createLogger('MobileDevicePairingPanel')
const { showToast } = useNotificationBus()

const { devices, currentQR, loading, error, hasDevices, generateQRCode, fetchDevices, deleteDevice, clearError, clearQRChallenge } = useMobileDevices()

const qrCanvas = ref<HTMLCanvasElement | null>(null)
const expirySeconds = ref<number>(0)
let expiryInterval: number | null = null

onMounted(async () => {
  try {
    await fetchDevices()
  } catch (err) {
    logger.error('Failed to load devices on mount', err)
  }
})

onUnmounted(() => {
  if (expiryInterval !== null) {
    clearInterval(expiryInterval)
  }
})

// Watch for QR challenge and render QR code
watch(currentQR, async (challenge) => {
  if (!challenge || !qrCanvas.value) return

  try {
    // QR payload: JSON with challenge token
    const payload = JSON.stringify({
      type: 'autobot_device_pair',
      challenge_token: challenge.challenge_token,
      api_base: window.location.origin,
    })

    await QRCode.toCanvas(qrCanvas.value, payload, {
      width: 300,
      margin: 2,
      color: {
        dark: '#000000',
        light: '#FFFFFF',
      },
    })

    // Start expiry countdown
    expirySeconds.value = challenge.expires_in_seconds
    if (expiryInterval !== null) clearInterval(expiryInterval)
    expiryInterval = setInterval(() => {
      expirySeconds.value -= 1
      if (expirySeconds.value <= 0) {
        if (expiryInterval !== null) clearInterval(expiryInterval)
        showToast('QR code expired. Generate a new one to pair a device.', 'warning')
        clearQRChallenge()
      }
    }, 1000)

    logger.info('QR code rendered', { expiresIn: challenge.expires_in_seconds })
  } catch (err) {
    logger.error('Failed to render QR code', err)
    showToast('Failed to generate QR code', 'error')
  }
})

async function handleGenerateQR(): Promise<void> {
  try {
    await generateQRCode()
    showToast('QR code generated. Scan it with your mobile device.', 'success')
  } catch (err) {
    showToast('Failed to generate QR code. Please try again.', 'error')
  }
}

async function handleDeleteDevice(deviceId: string): Promise<void> {
  if (!confirm('Are you sure you want to unpair this device?')) return

  try {
    await deleteDevice(deviceId)
    showToast('Device unpaired successfully', 'success')
  } catch (err) {
    showToast('Failed to delete device. Please try again.', 'error')
  }
}

function getPlatformIcon(platform: string): string {
  switch (platform) {
    case 'ios':
      return 'apple'
    case 'android':
      return 'robot'
    case 'pwa':
      return 'globe'
    default:
      return 'mobile-alt'
  }
}

function getPlatformLabel(platform: string): string {
  switch (platform) {
    case 'ios':
      return 'iOS'
    case 'android':
      return 'Android'
    case 'pwa':
      return 'PWA'
    default:
      return 'Unknown'
  }
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}
</script>

<style scoped>
.mobile-device-pairing-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-danger-bg, rgba(220, 38, 38, 0.1));
  color: var(--color-danger, #dc2626);
  border: 1px solid var(--color-danger, #dc2626);
  border-radius: var(--radius-md, 8px);
  font-size: var(--text-sm);
}

.dismiss-btn {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-danger, #dc2626);
  padding: var(--spacing-xs);
}

/* QR Section */
.qr-section {
  padding: var(--spacing-lg);
  background: var(--surface-secondary, var(--bg-secondary));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 8px);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.section-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-lg) 0;
  line-height: var(--leading-relaxed);
}

.qr-actions {
  display: flex;
  justify-content: center;
}

.generate-qr-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-xl);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 8px);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: opacity var(--duration-150);
}

.generate-qr-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.generate-qr-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.qr-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
}

.qr-code-wrapper {
  padding: var(--spacing-md);
  background: #fff;
  border-radius: var(--radius-md, 8px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.qr-canvas {
  display: block;
}

.qr-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.regenerate-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 8px);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: background var(--duration-150);
}

.regenerate-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
}

.regenerate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Devices Section */
.devices-section {
  padding: var(--spacing-lg);
  background: var(--surface-secondary, var(--bg-secondary));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 8px);
}

.empty-state {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--spacing-xl);
  margin: 0;
}

.devices-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.device-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 8px);
  transition: box-shadow var(--duration-150);
}

.device-card:hover {
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.device-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.device-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.device-icon {
  width: var(--text-lg);
  height: var(--text-lg);
  color: var(--color-primary);
}

.device-name {
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.device-platform {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  border-radius: var(--radius-sm, 4px);
  text-transform: uppercase;
}

.device-meta {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin: 0;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.delete-device-btn {
  padding: var(--spacing-sm);
  background: transparent;
  color: var(--color-danger, #dc2626);
  border: 1px solid var(--color-danger, #dc2626);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  transition: background var(--duration-150), color var(--duration-150);
}

.delete-device-btn:hover:not(:disabled) {
  background: var(--color-danger, #dc2626);
  color: #fff;
}

.delete-device-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
