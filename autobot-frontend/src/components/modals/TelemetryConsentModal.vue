<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

TelemetryConsentModal.vue - First-run local usage metrics notice
Issue #9035: Operator-controlled local usage metrics (never transmitted)
-->

<template>
  <BaseModal
    :close-label="t('ui.modal.closeDialog')"
    v-model="isVisible"
    title="Local Usage Metrics"
    size="sm"
    :show-close="false"
    :close-on-overlay="false"
  >
    <div class="modal-body">
      <p class="consent-intro">
        AutoBot can record <strong>anonymous operational metrics</strong> locally to power your
        own monitoring dashboards. This data stays on your infrastructure and is
        <strong>never sent to anyone</strong>.
      </p>

      <div class="data-summary">
        <h3 class="summary-title">
          <Icon name="chart-line" aria-hidden="true" />
          What's recorded locally:
        </h3>
        <ul class="data-list">
          <li>API endpoint usage and response times</li>
          <li>Voice session duration and token counts</li>
          <li>Feature usage patterns</li>
        </ul>
      </div>

      <div class="privacy-note">
        <Icon name="lock" aria-hidden="true" />
        <span>
          <strong>Never recorded:</strong> personal data, code content, or chat messages.
        </span>
      </div>

      <p class="consent-footer">
        You can change this preference anytime in <strong>Settings → Privacy</strong>.
      </p>
    </div>

    <template #actions>
      <button
        type="button"
        class="btn btn-secondary"
        @click="handleDecline"
        :disabled="isProcessing"
      >
        <Icon name="times" aria-hidden="true" />
        Keep Off
      </button>
      <button
        type="button"
        class="btn btn-primary"
        @click="handleAccept"
        :disabled="isProcessing"
      >
        <Icon name="check" aria-hidden="true" />
        {{ isProcessing ? 'Saving...' : 'Enable' }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'
import { BaseModal } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const logger = createLogger('TelemetryConsentModal')
const api = useApiClient()

const isVisible = ref(false)
const isProcessing = ref(false)

const CONSENT_STORAGE_KEY = 'autobot_telemetry_consent_shown'

onMounted(async () => {
  await checkShouldShow()
})

async function checkShouldShow() {
  // Check localStorage first for quick client-side check
  const localShown = localStorage.getItem(CONSENT_STORAGE_KEY)
  if (localShown === 'true') {
    logger.debug('Consent prompt already shown (localStorage)')
    return
  }

  try {
    // Check server-side state
    const response = await api.get<{
      enabled: boolean
      anonymous_usage_stats: boolean
      first_run_prompt_shown: boolean
    }>('/api/settings/telemetry')

    if (response.first_run_prompt_shown) {
      logger.debug('Consent prompt already shown (server)')
      localStorage.setItem(CONSENT_STORAGE_KEY, 'true')
      return
    }

    // Show the prompt
    isVisible.value = true
    logger.debug('Showing first-run telemetry consent prompt')
  } catch (error) {
    logger.error('Failed to check telemetry consent status', error)
    // Don't show prompt on error to avoid blocking the user
  }
}

async function handleAccept() {
  await updateConsent(true)
}

async function handleDecline() {
  await updateConsent(false)
}

async function updateConsent(enabled: boolean) {
  isProcessing.value = true

  try {
    // Persist the enable/disable choice (admin-gated). Non-admins will get a
    // 403 here — that is expected and handled below by the prompt-shown call.
    await api.post('/api/settings/telemetry', {
      enabled,
      anonymous_usage_stats: enabled,
      first_run_prompt_shown: true,
    })
    logger.debug(`Telemetry consent: ${enabled ? 'accepted' : 'declined'}`)
  } catch (error) {
    logger.error('Failed to save telemetry consent', error)
  } finally {
    // Record the dismissal for ANY authenticated user (#11344). This is a
    // non-admin endpoint, so it persists server-side even when the admin POST
    // above 403s. Best-effort: a failure here still falls through to the
    // localStorage flag so the modal never re-nags on this browser.
    try {
      await api.post('/api/settings/telemetry/prompt-shown', {})
    } catch (error) {
      logger.error('Failed to persist telemetry prompt dismissal', error)
    }

    // Always mark shown locally and close, regardless of POST success/failure,
    // so the consent modal never re-appears on refresh (#11344).
    localStorage.setItem(CONSENT_STORAGE_KEY, 'true')
    isVisible.value = false
    isProcessing.value = false
  }
}
</script>

<style scoped>
.modal-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.consent-intro {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  line-height: 1.6;
  margin: 0;
}

.data-summary {
  padding: var(--spacing-md);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.summary-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.summary-title i {
  color: var(--color-info);
}

.data-list {
  margin: 0;
  padding-left: var(--spacing-lg);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.data-list li {
  margin-bottom: var(--spacing-xs);
}

.privacy-note {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-success-bg);
  border-left: 3px solid var(--color-success);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.privacy-note i {
  color: var(--color-success);
  flex-shrink: 0;
  margin-top: 2px;
}

.consent-footer {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  text-align: center;
  margin: var(--spacing-sm) 0 0 0;
}

.btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-hover);
}
</style>
