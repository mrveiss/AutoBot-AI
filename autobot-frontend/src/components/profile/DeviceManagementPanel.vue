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
      <button @click="showPairDialog = true" class="btn btn-primary">
        <Icon name="plus" />
        {{ $t('devices.pairDevice', 'Pair New Device') }}
      </button>
    </div>

    <!-- Devices List -->
    <div v-else-if="!isLoading" class="devices-list">
      <div class="section-header">
        <h3>{{ $t('devices.pairedDevices', 'Paired Devices') }}</h3>
        <button @click="showPairDialog = true" class="btn btn-secondary btn-sm">
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

    <!-- The pairing dialog owns the QR challenge, its countdown and the expiry
         refresh. It replaces a static instruction list that told the user to
         scan "the QR code shown on your desktop" while no desktop surface ever
         rendered one — the step-4 instruction had no corresponding UI. -->
    <PairDeviceDialog v-model="showPairDialog" @paired="refresh" />
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import Icon from '@/components/ui/Icon.vue'
import PairDeviceDialog from '@/components/mobile/PairDeviceDialog.vue'
import { useDevices } from '@/composables/useDevices'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DeviceManagementPanel')
const { t } = useI18n()
const { confirm } = useConfirmDialog()

const {
  devices,
  loading: isLoading,
  error,
  fetchDevices,
  deleteDevice: deleteDeviceApi
} = useDevices()

const deleteLoading = ref<Set<string>>(new Set())
const showPairDialog = ref(false)

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
  if (!(await confirm({ title: t('common.confirm'), message: t('devices.confirmDelete', 'Are you sure you want to unpair this device?') }))) {
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
  color: var(--text-secondary);
  margin-bottom: 1rem;
  display: block;
}

.empty-state h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.empty-state p {
  color: var(--text-secondary);
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
  border: 1px solid var(--border-default);
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
  color: var(--text-primary);
}

.device-info {
  flex: 1;
  min-width: 0;
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

</style>
