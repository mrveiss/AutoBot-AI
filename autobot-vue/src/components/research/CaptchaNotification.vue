<template>
  <Teleport to="body">
    <Transition name="slide-up">
      <div v-if="activeCaptcha" class="captcha-notification">
        <div class="captcha-card">
          <!-- Header -->
          <div class="captcha-header">
            <div class="captcha-icon">
              <i class="fas fa-shield-alt"></i>
            </div>
            <div class="captcha-title">
              <h3>CAPTCHA Detected</h3>
              <p class="captcha-type">{{ captchaTypeLabel }}</p>
            </div>
            <div class="captcha-timer" :class="{ 'timer-warning': timeRemaining < 30 }">
              <i class="fas fa-clock"></i>
              {{ formatTime(timeRemaining) }}
            </div>
          </div>

          <!-- Content -->
          <div class="captcha-content">
            <p class="captcha-message">
              A CAPTCHA was detected during web research. Please solve it manually via VNC to continue.
            </p>
            <p class="captcha-url">
              <i class="fas fa-link"></i>
              <a :href="activeCaptcha.url" target="_blank" rel="noopener">{{ truncatedUrl }}</a>
            </p>

            <!-- Screenshot preview (if available) -->
            <div v-if="activeCaptcha.screenshot" class="captcha-preview">
              <img
                :src="'data:image/png;base64,' + activeCaptcha.screenshot"
                alt="CAPTCHA Screenshot"
                @click="openVnc"
              />
              <div class="preview-overlay" @click="openVnc">
                <i class="fas fa-external-link-alt"></i>
                Click to solve in VNC
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="captcha-actions">
            <button class="btn-vnc" @click="openVnc">
              <i class="fas fa-desktop"></i>
              Open VNC Desktop
            </button>
            <button class="btn-solved" @click="markSolved" :disabled="isSubmitting">
              <i class="fas fa-check"></i>
              I've Solved It
            </button>
            <button class="btn-skip" @click="skipCaptcha" :disabled="isSubmitting">
              <i class="fas fa-times"></i>
              Skip Source
            </button>
          </div>

          <!-- Progress bar -->
          <div class="timeout-progress">
            <div
              class="timeout-bar"
              :style="{ width: progressPercentage + '%' }"
              :class="{ 'bar-warning': timeRemaining < 30 }"
            ></div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
// @ts-ignore - JS module without type declarations
import { useGlobalWebSocket } from '@/composables/useGlobalWebSocket'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CaptchaNotification')

// ============================================================================
// Types
// ============================================================================

interface CaptchaEvent {
  captcha_id: string
  url: string
  captcha_type: string
  screenshot?: string
  vnc_url: string
  timeout_seconds: number
  timestamp: string
  message: string
}

// ============================================================================
// State
// ============================================================================

const activeCaptcha = ref<CaptchaEvent | null>(null)
const timeRemaining = ref(0)
const isSubmitting = ref(false)
let timerInterval: ReturnType<typeof setInterval> | null = null

// ============================================================================
// WebSocket
// ============================================================================

const { on } = useGlobalWebSocket()

function handleCaptchaDetected(data: CaptchaEvent | { payload: CaptchaEvent }) {
  // Handle both direct event and wrapped payload format
  const eventData = 'payload' in data ? data.payload : data
  activeCaptcha.value = eventData
  timeRemaining.value = eventData.timeout_seconds
  startTimer()
}

function handleCaptchaTimeout(data: { captcha_id: string } | { payload: { captcha_id: string } }) {
  const eventData = 'payload' in data ? data.payload : data
  if (activeCaptcha.value?.captcha_id === eventData.captcha_id) {
    activeCaptcha.value = null
    stopTimer()
  }
}

function handleCaptchaResolved(data: { captcha_id: string } | { payload: { captcha_id: string } }) {
  const eventData = 'payload' in data ? data.payload : data
  if (activeCaptcha.value?.captcha_id === eventData.captcha_id) {
    activeCaptcha.value = null
    stopTimer()
  }
}

// Subscribe to WebSocket events (unsubscribe is handled by the composable on unmount)
on('captcha_detected', handleCaptchaDetected)
on('captcha_timeout', handleCaptchaTimeout)
on('captcha_resolved', handleCaptchaResolved)

// ============================================================================
// Computed
// ============================================================================

const captchaTypeLabel = computed(() => {
  const types: Record<string, string> = {
    recaptcha: 'reCAPTCHA',
    hcaptcha: 'hCaptcha',
    cloudflare: 'Cloudflare Challenge',
    unknown: 'Unknown CAPTCHA'
  }
  return types[activeCaptcha.value?.captcha_type || 'unknown'] || 'CAPTCHA'
})

const truncatedUrl = computed(() => {
  const url = activeCaptcha.value?.url || ''
  if (url.length > 60) {
    return url.substring(0, 57) + '...'
  }
  return url
})

const progressPercentage = computed(() => {
  if (!activeCaptcha.value) return 0
  return (timeRemaining.value / activeCaptcha.value.timeout_seconds) * 100
})

// ============================================================================
// Methods
// ============================================================================

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function startTimer() {
  stopTimer()
  timerInterval = setInterval(() => {
    if (timeRemaining.value > 0) {
      timeRemaining.value--
    } else {
      activeCaptcha.value = null
      stopTimer()
    }
  }, 1000)
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
}

function openVnc() {
  // Use VNC URL from captcha response or fallback to environment variable
  const defaultVncUrl = `http://${import.meta.env.VITE_LOCALHOST || 'localhost'}:${import.meta.env.VITE_VNC_PORT || '6080'}/vnc.html`
  const vncUrl = activeCaptcha.value?.vnc_url || defaultVncUrl
  window.open(vncUrl, '_blank', 'noopener,noreferrer')
}

async function markSolved() {
  if (!activeCaptcha.value || isSubmitting.value) return

  isSubmitting.value = true
  try {
    await apiClient.post(`/api/captcha/${activeCaptcha.value.captcha_id}/resolve`)
    activeCaptcha.value = null
    stopTimer()
  } catch (error) {
    logger.error('Failed to mark CAPTCHA as solved:', error)
  } finally {
    isSubmitting.value = false
  }
}

async function skipCaptcha() {
  if (!activeCaptcha.value || isSubmitting.value) return

  isSubmitting.value = true
  try {
    await apiClient.post(`/api/captcha/${activeCaptcha.value.captcha_id}/skip`)
    activeCaptcha.value = null
    stopTimer()
  } catch (error) {
    logger.error('Failed to skip CAPTCHA:', error)
  } finally {
    isSubmitting.value = false
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

// WebSocket subscriptions are set up above and auto-cleaned by useGlobalWebSocket
// We just need to clean up the timer on unmount
onUnmounted(() => {
  stopTimer()
})

// Cleanup when captcha changes
watch(activeCaptcha, (newVal) => {
  if (!newVal) {
    stopTimer()
  }
})
</script>

<style scoped>
.captcha-notification {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  z-index: 9999;
  max-width: 400px;
  width: 100%;
}

.captcha-card {
  background: white;
  border-radius: 0.75rem;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

/* Header */
.captcha-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
}

.captcha-icon {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 0.5rem;
  font-size: 1.25rem;
}

.captcha-title {
  flex: 1;
}

.captcha-title h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.captcha-type {
  margin: 0.125rem 0 0;
  font-size: 0.75rem;
  opacity: 0.9;
}

.captcha-timer {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 600;
  font-family: monospace;
}

.captcha-timer.timer-warning {
  background: rgba(255, 255, 255, 0.3);
  animation: pulse 1s infinite;
}

/* Content */
.captcha-content {
  padding: 1rem;
}

.captcha-message {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.5;
}

.captcha-url {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 1rem;
  font-size: 0.75rem;
  color: #6b7280;
}

.captcha-url a {
  color: #3b82f6;
  text-decoration: none;
  word-break: break-all;
}

.captcha-url a:hover {
  text-decoration: underline;
}

/* Preview */
.captcha-preview {
  position: relative;
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  cursor: pointer;
}

.captcha-preview img {
  width: 100%;
  height: auto;
  display: block;
}

.preview-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  font-size: 0.875rem;
  opacity: 0;
  transition: opacity 0.2s;
}

.captcha-preview:hover .preview-overlay {
  opacity: 1;
}

.preview-overlay i {
  font-size: 1.5rem;
}

/* Actions */
.captcha-actions {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  border-top: 1px solid #e5e7eb;
}

.captcha-actions button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  padding: 0.625rem 0.75rem;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.captcha-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-vnc {
  background: #3b82f6;
  color: white;
}

.btn-vnc:hover:not(:disabled) {
  background: #2563eb;
}

.btn-solved {
  background: #10b981;
  color: white;
}

.btn-solved:hover:not(:disabled) {
  background: #059669;
}

.btn-skip {
  background: #6b7280;
  color: white;
}

.btn-skip:hover:not(:disabled) {
  background: #4b5563;
}

/* Progress bar */
.timeout-progress {
  height: 3px;
  background: #e5e7eb;
}

.timeout-bar {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #10b981);
  transition: width 1s linear;
}

.timeout-bar.bar-warning {
  background: linear-gradient(90deg, #ef4444, #f97316);
}

/* Animations */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}
</style>
