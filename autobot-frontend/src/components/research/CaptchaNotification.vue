<template>
  <Teleport to="body">
    <Transition name="slide-up">
      <div v-if="activeCaptcha" class="captcha-notification">
        <div class="captcha-card">
          <!-- Header -->
          <div class="captcha-header">
            <div class="captcha-icon">
              <Icon name="shield-alt" />
            </div>
            <div class="captcha-title">
              <h3>{{ $t('research.captcha.detected') }}</h3>
              <p class="captcha-type">{{ captchaTypeLabel }}</p>
            </div>
            <div class="captcha-timer" :class="{ 'timer-warning': timeRemaining < 30 }">
              <Icon name="clock" />
              {{ formatTime(timeRemaining) }}
            </div>
          </div>

          <!-- Content -->
          <div class="captcha-content">
            <p class="captcha-message">
              {{ $t('research.captcha.message') }}
            </p>
            <p class="captcha-url">
              <Icon name="link" />
              <a :href="activeCaptcha.url" target="_blank" rel="noopener">{{ truncatedUrl }}</a>
            </p>

            <!-- Screenshot preview (if available) -->
            <div v-if="activeCaptcha.screenshot" class="captcha-preview">
              <img
                :src="'data:image/png;base64,' + activeCaptcha.screenshot"
                :alt="$t('research.captcha.screenshotAlt')"
                loading="lazy"
                @click="openVnc"
              />
              <div class="preview-overlay" @click="openVnc">
                <Icon name="external-link-alt" />
                {{ $t('research.captcha.clickToSolve') }}
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="captcha-actions">
            <button class="btn-vnc" @click="openVnc">
              <Icon name="desktop" />
              {{ $t('research.captcha.openVnc') }}
            </button>
            <button class="btn-solved" @click="markSolved" :disabled="isSubmitting">
              <Icon name="check" />
              {{ $t('research.captcha.solved') }}
            </button>
            <button class="btn-skip" @click="skipCaptcha" :disabled="isSubmitting">
              <Icon name="times" />
              {{ $t('research.captcha.skipSource') }}
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
import Icon from '@/components/ui/Icon.vue'
import { useCaptchaStatus } from '@/composables/research/useCaptchaStatus'


const {
  activeCaptcha,
  timeRemaining,
  isSubmitting,
  captchaTypeLabel,
  truncatedUrl,
  progressPercentage,
  formatTime,
  openVnc,
  markSolved,
  skipCaptcha,
} = useCaptchaStatus()
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
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.captcha-type {
  margin: var(--spacing-0-5) var(--spacing-0) var(--spacing-0);
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
  transition: width var(--duration-1000) linear;
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
