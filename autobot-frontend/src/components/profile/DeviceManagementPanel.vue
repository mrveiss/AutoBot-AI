<!-- autobot-frontend/src/components/profile/DeviceManagementPanel.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="device-management-panel">
    <!-- Empty State -->
    <div v-if="devices.length === 0 && !isLoading" class="empty-state">
      <Icon name="smartphone" class="empty-icon" />
      <h3>{{ $t('devices.noDevices', 'No paired devices') }}</h3>
      <p>{{ $t('devices.pairFirst', 'Pair your mobile device to receive push notifications') }}</p>
      <button @click="showPairingInstructions = true" class="btn btn-primary">
        <Icon name="plus" />
        {{ $t('devices.pairDevice', 'Pair New Device') }}
      </button>
    </div>

    <!-- Devices List -->
    <div v-else-if="!isLoading" class="devices-list">
      <div class="section-header">
        <h3>{{ $t('devices.pairedDevices', 'Paired Devices') }}</h3>
        <button @click="showPairingInstructions = true" class="btn btn-secondary btn-sm">
          <Icon name="plus" />
          {{ $t('devices.addDevice', 'Add Device') }}
        </button>
      </div>

      <div class="devices-container">
        <div v-for="device in devices" :key="device.id" class="device-card">
          <div class="device-header">
            <div class="device-icon">
              <Icon :name="getPlatformIcon(device.platform)" />
            </div>
            <div class="device-info">
              <div class="device-name">{{ device.device_name }}</div>
              <div class="device-platform">{{ formatPlatform(device.platform) }}</div>
            </div>
            <button
              @click="deleteDevice(device.id)"
              class="btn btn-danger btn-sm"
              :aria-label="$t('devices.unpair', 'Unpair device')"
              :disabled="deleteLoading.has(device.id)"
            >
              <Icon v-if="!deleteLoading.has(device.id)" name="trash" />
              <div v-else class="spinner-tiny"></div>
            </button>
          </div>
          <div class="device-meta">
            <span class="meta-label">{{ $t('devices.paired', 'Paired:') }}</span>
            <span>{{ formatDate(device.created_at) }}</span>
            <span v-if="device.last_seen_at" class="meta-label">{{ $t('devices.lastSeen', 'Last Seen:') }}</span>
            <span v-if="device.last_seen_at">{{ formatRelativeTime(device.last_seen_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <p>{{ $t('devices.loading', 'Loading devices...') }}</p>
    </div>

    <!-- Error State -->
    <div v-if="error && !isLoading" class="error-alert">
      <Icon name="exclamation-triangle" />
      <div>
        <strong>{{ $t('devices.error', 'Failed to load devices') }}</strong>
        <p>{{ error }}</p>
      </div>
      <button @click="refresh" class="btn btn-secondary btn-sm">
        {{ $t('common.retry', 'Retry') }}
      </button>
    </div>

    <!-- Pairing Instructions Modal -->
    <div v-if="showPairingInstructions" class="pairing-modal-overlay" @click="closePairingInstructions">
      <div class="pairing-modal" @click.stop>
        <div class="modal-header">
          <h3>{{ $t('devices.pairNewDevice', 'Pair New Device') }}</h3>
          <button @click="closePairingInstructions" class="close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <p>{{ $t('devices.pairingInstructions', 'To pair a device:') }}</p>
          <ol class="instructions-list">
            <li>{{ $t('devices.step1', 'Open the AutoBot mobile app') }}</li>
            <li>{{ $t('devices.step2', 'Go to Settings → Device Pairing') }}</li>
            <li>{{ $t('devices.step3', 'Click "Pair with Desktop"') }}</li>
            <li>{{ $t('devices.step4', 'Scan the QR code shown on your desktop') }}</li>
          </ol>
          <div class="info-box">
            <Icon name="info-circle" />
            <p>{{ $t('devices.pairingNote', 'The QR code expires after 5 minutes') }}</p>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="closePairingInstructions" class="btn btn-primary">
            {{ $t('common.close', 'Close') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import { useDevices } from '@/composables/useDevices'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DeviceManagementPanel')
const { t } = useI18n()

const {
  devices,
  loading: isLoading,
  error,
  fetchDevices,
  deleteDevice: deleteDeviceApi
} = useDevices()

const deleteLoading = ref<Set<string>>(new Set())
const showPairingInstructions = ref(false)

onMounted(async () => {
  await refresh()
})

async function refresh() {
  try {
    await fetchDevices()
  } catch (err) {
    logger.error('Failed to refresh devices:', err)
  }
}

async function deleteDevice(deviceId: string) {
  if (!confirm(t('devices.confirmDelete', 'Are you sure you want to unpair this device?'))) {
    return
  }

  deleteLoading.value = new Set([...deleteLoading.value, deviceId])
  try {
    await deleteDeviceApi(deviceId)
  } catch (err) {
    logger.error('Failed to delete device:', err)
  } finally {
    deleteLoading.value.delete(deviceId)
    deleteLoading.value = new Set(deleteLoading.value)
  }
}

function closePairingInstructions() {
  showPairingInstructions.value = false
}

// #9724: 'apple'/'android' are not SVG IconNames — they rendered empty
// SVGs through <Icon :name>. Use device-shaped registry icons instead.
function getPlatformIcon(platform: string): IconName {
  const icons: Record<string, IconName> = {
    ios: 'mobile-alt',
    android: 'mobile',
    pwa: 'globe'
  }
  return icons[platform] || 'smartphone'
}

function formatPlatform(platform: string): string {
  const labels: Record<string, string> = {
    ios: 'iOS',
    android: 'Android',
    pwa: 'Web App'
  }
  return labels[platform] || platform
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString()
  } catch {
    return dateStr
  }
}

function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

    if (seconds < 60) return t('devices.justNow', 'just now')
    if (seconds < 3600) return t('devices.minutesAgo', `${Math.floor(seconds / 60)}m ago`)
    if (seconds < 86400) return t('devices.hoursAgo', `${Math.floor(seconds / 3600)}h ago`)
    if (seconds < 2592000) return t('devices.daysAgo', `${Math.floor(seconds / 86400)}d ago`)

    return date.toLocaleDateString()
  } catch {
    return dateStr
  }
}
</script>

<style scoped>
.device-management-panel {
  padding: 1.5rem 0;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 2rem;
  border-radius: 8px;
  background: var(--color-bg-secondary);
}

.empty-icon {
  font-size: 3rem;
  color: var(--color-text-secondary);
  margin-bottom: 1rem;
  display: block;
}

.empty-state h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.empty-state p {
  color: var(--color-text-secondary);
  margin-bottom: 1.5rem;
}

/* Devices List */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.section-header h3 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}

.devices-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.device-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1.25rem;
  background: var(--color-bg);
  transition: border-color 0.2s;
}

.device-card:hover {
  border-color: var(--color-border-hover);
}

.device-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.device-icon {
  flex-shrink: 0;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 6px;
  background: var(--color-bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  color: var(--color-text-primary);
}

.device-info {
  flex: 1;
  min-width: 0;
}

.device-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.device-platform {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.device-meta {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.meta-label {
  font-weight: 500;
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-bottom: 1rem;
}

.spinner-tiny {
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error State */
.error-alert {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--color-danger);
  border-radius: 6px;
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.error-alert strong {
  display: block;
  margin-bottom: 0.25rem;
}

.error-alert p {
  margin: 0;
  font-size: 0.875rem;
}

/* Pairing Modal */
.pairing-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.pairing-modal {
  background: var(--color-bg);
  border-radius: 12px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--color-text-secondary);
  padding: 0;
}

.modal-body {
  padding: 1.5rem;
}

.qr-step {
  text-align: center;
}

.qr-step p {
  margin: 0 0 1.5rem 0;
  color: var(--color-text-secondary);
}

.qr-display {
  display: flex;
  justify-content: center;
  margin: 1.5rem 0;
}

.qr-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  border: 1px solid transparent;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-sm {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  background: var(--color-bg-secondary);
  border-color: var(--color-border);
  color: var(--color-text-primary);
}

.btn-secondary:hover {
  background: var(--color-bg-hover);
}

.btn-danger {
  background: transparent;
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.btn-danger:hover {
  background: var(--color-danger-bg);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Instructions */
.instructions-list {
  list-style-position: inside;
  margin: 1rem 0;
  padding-left: 0;
}

.instructions-list li {
  margin: 0.5rem 0;
  color: var(--color-text-primary);
}

/* Info Box */
.info-box {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  padding: 1rem;
  border-radius: 6px;
  background: var(--color-info-bg, rgba(59, 130, 246, 0.1));
  color: var(--color-info, rgb(59, 130, 246));
  margin-top: 1rem;
}

.info-box svg {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.info-box p {
  margin: 0;
}
</style>
