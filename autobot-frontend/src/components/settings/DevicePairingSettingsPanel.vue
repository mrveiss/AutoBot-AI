<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2026 mrveiss
Author: mrveiss

DevicePairingSettingsPanel.vue - Mobile Device Pairing Configuration (MVA-3085)
Allows users to pair mobile devices for push notifications and offline sync
-->

<template>
  <form class="device-pairing-panel" @submit.prevent>
    <div class="panel-content">
      <!-- Pair Device Section -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="mobile" />
          Pair New Device
        </legend>
        <p class="preference-hint">
          Click the button below to pair a mobile device and receive push notifications.
        </p>

        <div class="pair-device-actions">
          <button
            v-if="!showPairingFlow"
            type="button"
            class="pair-device-btn"
            @click="startPairingFlow"
            :disabled="pairingInProgress"
          >
            <Icon :name="pairingInProgress ? 'spinner' : 'mobile-alt'" :class="{ 'fa-spin': pairingInProgress }" />
            {{ pairingInProgress ? 'Generating Code…' : 'Pair Mobile Device' }}
          </button>
        </div>

        <!-- Pairing Flow -->
        <div v-if="showPairingFlow" class="pairing-flow">
          <!-- Step 1: Display QR Code -->
          <div v-if="pairingStep === 1" class="pairing-step">
            <h4 class="step-title">
              <span class="step-number">1</span>
              Scan QR Code
            </h4>
            <p class="step-description">
              Open the AutoBot mobile app and scan this QR code:
            </p>

            <div v-if="pairingCode" class="qr-code-container">
              <div class="qr-code">
                <!-- QR Code will be rendered here -->
                <canvas ref="qrCanvas" class="qr-canvas"></canvas>
              </div>
              <p class="qr-code-alt">
                Can't scan? Enter this code manually: <code>{{ pairingCode }}</code>
              </p>
            </div>

            <div v-if="pairingError" class="error-box">
              <Icon name="exclamation-triangle" />
              <span>{{ pairingError }}</span>
            </div>

            <div v-if="pairingTimeoutWarning" class="warning-box">
              <Icon name="hourglass-half" />
              <span>{{ pairingTimeoutWarning }}</span>
            </div>

            <div class="step-actions">
              <button
                type="button"
                class="primary-btn"
                @click="nextPairingStep"
                :disabled="!pairingCode"
              >
                <Icon name="check" />
                I've Scanned the Code
              </button>
              <button
                type="button"
                class="secondary-btn"
                @click="cancelPairingFlow"
              >
                Cancel
              </button>
            </div>
          </div>

          <!-- Step 2: Confirm Pairing -->
          <div v-if="pairingStep === 2" class="pairing-step">
            <h4 class="step-title">
              <span class="step-number">2</span>
              Confirm Pairing
            </h4>
            <p class="step-description">
              A notification was sent to your mobile device. Please confirm the pairing on your phone.
            </p>

            <div class="device-info">
              <label class="info-field">
                <span class="info-label">Device Name</span>
                <input
                  v-model="deviceName"
                  type="text"
                  class="info-input"
                  placeholder="e.g., My iPhone"
                  @keyup.enter="completePairing"
                />
              </label>
            </div>

            <div v-if="confirmationTimeout" class="warning-box">
              <Icon name="hourglass-end" />
              <span>{{ confirmationTimeout }}</span>
            </div>

            <div class="step-actions">
              <button
                type="button"
                class="primary-btn"
                @click="completePairing"
                :disabled="!deviceName || !confirmationReceived"
              >
                <Icon name="check-circle" />
                Complete Pairing
              </button>
              <button
                type="button"
                class="secondary-btn"
                @click="cancelPairingFlow"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </fieldset>

      <!-- Pairing Status -->
      <div v-if="pairingStatus" :class="['pairing-status', pairingStatus.type]">
        <Icon :name="pairingStatus.icon" />
        <span>{{ pairingStatus.message }}</span>
      </div>

      <!-- Paired Devices List -->
      <fieldset v-if="pairedDevices.length > 0" class="preference-section">
        <legend class="preference-label">
          <Icon name="list" />
          Paired Devices
        </legend>
        <p class="preference-hint">
          Manage your paired mobile devices.
        </p>

        <div class="devices-list">
          <div v-for="device in pairedDevices" :key="device.id" class="device-item">
            <div class="device-info">
              <div class="device-header">
                <Icon name="mobile" class="device-icon" />
                <div class="device-details">
                  <h5 class="device-name">{{ device.name }}</h5>
                  <p class="device-meta">
                    {{ device.platform }} · Last seen: {{ formatLastSeen(device.lastSeenAt) }}
                  </p>
                </div>
              </div>
              <button
                type="button"
                class="revoke-btn"
                @click="revokeDevice(device.id)"
                :disabled="revokingDeviceId === device.id"
                aria-label="Revoke device"
              >
                <Icon :name="revokingDeviceId === device.id ? 'spinner' : 'trash'" :class="{ 'fa-spin': revokingDeviceId === device.id }" />
                {{ revokingDeviceId === device.id ? 'Revoking…' : 'Revoke' }}
              </button>
            </div>
          </div>
        </div>
      </fieldset>

      <!-- Empty State -->
      <div v-if="pairedDevices.length === 0 && !showPairingFlow" class="empty-state">
        <Icon name="mobile-alt" class="empty-icon" />
        <h4>No Paired Devices</h4>
        <p>Pair your first mobile device to receive push notifications and sync conversations across devices.</p>
      </div>
    </div>
  </form>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, watch } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { createLogger } from '@/utils/debugUtils'
import apiClient from '@/utils/ApiClient'
import QRCode from 'qrcode'

const logger = createLogger('DevicePairingSettingsPanel')
const { showToast } = useNotificationBus()

// Reactive state
const pairedDevices = ref<Array<{
  id: string
  name: string
  platform: string
  lastSeenAt: string
}>>([])

const pairingCode = ref<string>('')
const pairingStep = ref<1 | 2>(1)
const showPairingFlow = ref(false)
const pairingInProgress = ref(false)
const deviceName = ref('')
const confirmationReceived = ref(false)
const revokingDeviceId = ref<string | null>(null)
const pairingError = ref('')
const pairingTimeoutWarning = ref('')
const confirmationTimeout = ref('')
const pairingStatus = ref<{ type: string; message: string; icon: IconName } | null>(null)

const qrCanvas = ref<HTMLCanvasElement | null>(null)

// Load paired devices on mount
onMounted(async () => {
  await loadPairedDevices()
})

// Methods
async function loadPairedDevices() {
  try {
    // GH#9851: canonical list route is GET /api/devices → { devices: [...] }.
    // ApiClient returns parsed JSON directly (no axios .data envelope).
    const response = await apiClient.get<{ devices: typeof pairedDevices.value }>('/api/devices')
    pairedDevices.value = response.devices || []
  } catch (error) {
    logger.error('Failed to load paired devices', error)
    showToast('Failed to load paired devices', 'error')
  }
}

async function startPairingFlow() {
  try {
    pairingInProgress.value = true
    pairingError.value = ''

    // GH#9851: backend issues a QR challenge token via GET /api/devices/pair-qr.
    // The mobile app scans it and completes pairing by POSTing to /api/devices/pair.
    const response = await apiClient.get<{ challenge_token: string }>('/api/devices/pair-qr')
    pairingCode.value = response.challenge_token

    // Reset UI state
    pairingStep.value = 1
    showPairingFlow.value = true
    deviceName.value = ''
    confirmationReceived.value = false

    // Render QR code
    await renderQRCode(pairingCode.value)

    // Set timeout warning (e.g., 5 minutes)
    setTimeoutWarning()
  } catch (error) {
    logger.error('Failed to generate pairing code', error)
    pairingError.value = 'Failed to generate pairing code. Please try again.'
    showToast('Failed to generate pairing code', 'error')
  } finally {
    pairingInProgress.value = false
  }
}

async function renderQRCode(code: string) {
  if (!qrCanvas.value) return

  try {
    await QRCode.toCanvas(qrCanvas.value, code, {
      width: 200,
      margin: 2,
      color: {
        dark: '#000000',
        light: '#ffffff'
      },
      errorCorrectionLevel: 'H'
    })
  } catch (error) {
    logger.error('Failed to render QR code', error)
    pairingError.value = 'Failed to generate QR code. Please try again.'
  }
}

function setTimeoutWarning() {
  // Warn after 4 minutes
  setTimeout(() => {
    if (showPairingFlow.value && pairingStep.value === 1) {
      pairingTimeoutWarning.value = 'Pairing code expires in 1 minute. Please complete the pairing soon.'
    }
  }, 240000)
}

function nextPairingStep() {
  pairingStep.value = 2
  confirmationReceived.value = true // In production, this would be set by backend notification
  setConfirmationTimeout()
}

function setConfirmationTimeout() {
  // Warn after 2 minutes
  setTimeout(() => {
    if (showPairingFlow.value && pairingStep.value === 2) {
      confirmationTimeout.value = 'Waiting for confirmation. Please check your mobile device.'
    }
  }, 120000)
}

async function completePairing() {
  try {
    pairingInProgress.value = true

    // GH#9851: there is no desktop-side "confirm" endpoint — pairing is completed
    // by the mobile device POSTing the scanned challenge token to /api/devices/pair.
    // The desktop confirms by refreshing the device list and checking the device
    // now appears.
    await loadPairedDevices()

    // Show success message
    pairingStatus.value = {
      type: 'success',
      message: `Device "${deviceName.value}" paired successfully!`,
      icon: 'check-circle'
    }

    showToast(`Device "${deviceName.value}" paired successfully`, 'success')

    // Reset pairing flow
    resetPairingFlow()
  } catch (error) {
    logger.error('Failed to complete pairing', error)
    pairingError.value = 'Failed to complete pairing. Please try again.'
    showToast('Failed to complete pairing', 'error')
  } finally {
    pairingInProgress.value = false
  }
}

function cancelPairingFlow() {
  resetPairingFlow()
}

function resetPairingFlow() {
  showPairingFlow.value = false
  pairingStep.value = 1
  pairingCode.value = ''
  deviceName.value = ''
  confirmationReceived.value = false
  pairingError.value = ''
  pairingTimeoutWarning.value = ''
  confirmationTimeout.value = ''
  pairingStatus.value = null
}

async function revokeDevice(deviceId: string) {
  try {
    revokingDeviceId.value = deviceId

    // Revoke device via backend
    await apiClient.delete(`/api/devices/${deviceId}`)

    // Update list
    pairedDevices.value = pairedDevices.value.filter(d => d.id !== deviceId)

    showToast('Device revoked successfully', 'success')
  } catch (error) {
    logger.error('Failed to revoke device', error)
    showToast('Failed to revoke device', 'error')
  } finally {
    revokingDeviceId.value = null
  }
}

function formatLastSeen(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    const now = new Date()
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

    if (seconds < 60) return 'just now'
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
    return `${Math.floor(seconds / 86400)}d ago`
  } catch {
    return 'unknown'
  }
}
</script>

<style scoped>
/* Device Pairing Panel Styles */

.device-pairing-panel {
  width: 100%;
}

.panel-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

/* Preference Section */
.preference-section {
  border: none;
  padding: var(--spacing-lg);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  margin: 0;
}

.preference-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 var(--spacing-md) 0;
}

.preference-label svg {
  width: var(--text-lg);
  height: var(--text-lg);
  color: var(--color-primary);
}

.preference-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-md) 0;
}

/* Pair Device Actions */
.pair-device-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.pair-device-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.pair-device-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.pair-device-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Pairing Flow */
.pairing-flow {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 2px solid var(--border-default);
}

.pairing-step {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.step-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--color-primary);
  color: white;
  border-radius: 50%;
  font-size: var(--text-sm);
  font-weight: 700;
}

.step-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

/* QR Code Container */
.qr-code-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-lg);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 2px dashed var(--border-default);
}

.qr-code {
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  padding: var(--spacing-lg);
  border-radius: var(--radius-md);
}

.qr-canvas {
  width: 200px;
  height: 200px;
  border: 1px solid var(--border-subtle);
}

.qr-code-alt {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  text-align: center;
  margin: 0;
}

.qr-code-alt code {
  font-family: monospace;
  background: var(--bg-secondary);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  color: var(--color-primary);
}

/* Device Info */
.device-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.info-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.info-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.info-input {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-base);
  background: var(--bg-secondary);
  color: var(--text-primary);
  transition: border-color 0.2s ease;
}

.info-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

/* Step Actions */
.step-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.primary-btn,
.secondary-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-md) var(--spacing-lg);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.primary-btn {
  background: var(--color-primary);
  color: white;
}

.primary-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-2px);
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.secondary-btn {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.secondary-btn:hover {
  background: var(--bg-tertiary);
}

/* Status Messages */
.pairing-status,
.error-box,
.warning-box {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.pairing-status.success,
.pairing-status.success svg {
  background: rgba(34, 197, 94, 0.1);
  color: rgb(34, 197, 94);
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.error-box {
  background: rgba(239, 68, 68, 0.1);
  color: rgb(239, 68, 68);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.error-box svg {
  color: rgb(239, 68, 68);
  flex-shrink: 0;
}

.warning-box {
  background: rgba(245, 158, 11, 0.1);
  color: rgb(245, 158, 11);
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.warning-box svg {
  color: rgb(245, 158, 11);
  flex-shrink: 0;
}

/* Devices List */
.devices-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.device-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transition: all 0.2s ease;
}

.device-item:hover {
  border-color: var(--border-focus);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.device-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  flex: 1;
}

.device-icon {
  width: var(--text-2xl);
  height: var(--text-2xl);
  color: var(--color-primary);
  flex-shrink: 0;
}

.device-details {
  flex: 1;
}

.device-name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.device-meta {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.revoke-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  color: rgb(239, 68, 68);
  border: 1px solid rgb(239, 68, 68);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.revoke-btn:hover:not(:disabled) {
  background: rgb(239, 68, 68);
  color: white;
}

.revoke-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl) var(--spacing-lg);
  text-align: center;
  color: var(--text-secondary);
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-md);
  opacity: 0.5;
}

.empty-state h4 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.empty-state p {
  font-size: var(--text-sm);
  margin: 0;
  max-width: 300px;
}
</style>
