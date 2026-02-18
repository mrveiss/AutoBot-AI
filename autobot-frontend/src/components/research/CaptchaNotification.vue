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
// Casts are safe: the data IS the correct type at runtime, matching the server event schema
on('captcha_detected', handleCaptchaDetected as (data: unknown) => void)
on('captcha_timeout', handleCaptchaTimeout as (data: unknown) => void)
on('captcha_resolved', handleCaptchaResolved as (data: unknown) => void)

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
  bottom: var(--spacing-6);
  right: var(--spacing-6);
  z-index: var(--z-maximum);
  max-width: 400px;
  width: 100%;
}

.captcha-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl), 0 0 0 1px var(--border-subtle);
  overflow: hidden;
}

/* Header */
.captcha-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--color-error);
  color: var(--text-on-error);
}

.captcha-icon {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-lg);
  font-size: var(--text-xl);
}

.captcha-title {
  flex: 1;
}

.captcha-title h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.captcha-type {
  margin: 0.125rem 0 0;
  font-size: var(--text-xs);
  opacity: 0.9;
}

.captcha-timer {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  font-family: var(--font-mono);
}

.captcha-timer.timer-warning {
  background: rgba(255, 255, 255, 0.3);
  animation: pulse 1s infinite;
}

/* Content */
.captcha-content {
  padding: var(--spacing-4);
}

.captcha-message {
  margin: 0 0 var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.captcha-url {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0 0 var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.captcha-url a {
  color: var(--color-info);
  text-decoration: none;
  word-break: break-all;
}

.captcha-url a:hover {
  text-decoration: underline;
}

/* Preview */
.captcha-preview {
  position: relative;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
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
  gap: var(--spacing-2);
  background: var(--bg-overlay);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  opacity: 0;
  transition: opacity var(--duration-200) var(--ease-out);
}

.captcha-preview:hover .preview-overlay {
  opacity: 1;
}

.preview-overlay i {
  font-size: var(--text-2xl);
}

/* Actions */
.captcha-actions {
  display: flex;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.captcha-actions button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2-5) var(--spacing-3);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: background-color var(--duration-200) var(--ease-out);
}

.captcha-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-vnc {
  background: var(--color-info);
  color: var(--text-on-primary);
}

.btn-vnc:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.btn-solved {
  background: var(--color-success);
  color: var(--text-on-success);
}

.btn-solved:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.btn-skip {
  background: var(--color-secondary);
  color: var(--text-on-primary);
}

.btn-skip:hover:not(:disabled) {
  background: var(--color-secondary-hover);
}

/* Progress bar */
.timeout-progress {
  height: 3px;
  background: var(--border-subtle);
}

.timeout-bar {
  height: 100%;
  background: var(--color-info);
  transition: width 1s linear;
}

.timeout-bar.bar-warning {
  background: var(--color-error);
}

/* Animations */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all var(--duration-300) var(--ease-out);
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}
</style>
