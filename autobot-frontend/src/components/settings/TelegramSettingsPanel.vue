<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2026 mrveiss
Author: mrveiss

TelegramSettingsPanel.vue - Telegram Bot Configuration (MVA-2074)
-->

<template>
  <form class="telegram-panel" @submit.prevent>
    <div class="panel-header">
      <h3 class="panel-title">
        <Icon name="paper-plane" />
        Telegram Bot
      </h3>
    </div>

    <div class="panel-content">

      <!-- Status indicator -->
      <div class="status-row" :class="statusClass">
        <Icon :name="statusIcon" />
        <span>{{ statusText }}</span>
      </div>

      <!-- Bot token field -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="key" />
          Bot Token
        </legend>
        <p class="preference-hint">
          Create a bot via <strong>@BotFather</strong> on Telegram and paste the token here.
        </p>
        <div class="token-row">
          <input
            v-model="botToken"
            :type="showToken ? 'text' : 'password'"
            class="token-input"
            placeholder="123456789:ABCdefGhi..."
            autocomplete="off"
            aria-label="Telegram bot token"
          />
          <button type="button" class="icon-btn" :aria-label="showToken ? 'Hide token' : 'Show token'" @click="showToken = !showToken">
            <Icon :name="showToken ? 'eye-slash' : 'eye'" />
          </button>
        </div>
      </fieldset>

      <!-- Webhook URL field -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="globe" />
          Webhook URL
        </legend>
        <p class="preference-hint">
          Public HTTPS URL where Telegram will deliver updates.
          AutoBot registers <code>/api/telegram/webhook</code> at this base URL.
        </p>
        <input
          v-model="webhookUrl"
          type="url"
          class="token-input"
          placeholder="https://your-autobot.example.com"
          aria-label="Webhook base URL"
        />
      </fieldset>

      <!-- Current webhook info -->
      <div v-if="currentWebhookUrl" class="info-box">
        <Icon name="info-circle" />
        <span>Active webhook: <code>{{ currentWebhookUrl }}</code></span>
      </div>

      <!-- Error message -->
      <div v-if="errorMessage" class="error-box">
        <Icon name="exclamation-triangle" />
        <span>{{ errorMessage }}</span>
      </div>

      <!-- Actions -->
      <div class="panel-actions">
        <button
          type="button"
          class="save-btn"
          :disabled="!botToken || saving"
          @click="save"
        >
          <Icon :name="saving ? 'spinner' : 'save'" :class="{ 'fa-spin': saving }" />
          {{ saving ? 'Saving…' : 'Save & Verify' }}
        </button>
      </div>

    </div>
  </form>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TelegramSettingsPanel')
const api = useApiClient()

const botToken = ref('')
const webhookUrl = ref('')
const currentWebhookUrl = ref<string | null>(null)
const showToken = ref(false)
const saving = ref(false)
const configured = ref(false)
const errorMessage = ref<string | null>(null)

const statusClass = computed(() =>
  configured.value ? 'status-row--ok' : 'status-row--off'
)
const statusIcon = computed(() => (configured.value ? 'check-circle' : 'times-circle'))
const statusText = computed(() =>
  configured.value ? 'Bot configured and active' : 'Bot not configured'
)

async function loadConfig(): Promise<void> {
  try {
    const data = await api.get<{ status: string; webhook_url: string | null }>(
      '/api/telegram/config'
    )
    configured.value = data.status === 'configured'
    currentWebhookUrl.value = data.webhook_url ?? null
    if (data.webhook_url) {
      webhookUrl.value = new URL(data.webhook_url).origin
    }
  } catch (err) {
    logger.error('Failed to load Telegram config', err)
  }
}

async function save(): Promise<void> {
  if (!botToken.value) return
  saving.value = true
  errorMessage.value = null
  try {
    const payload: { bot_token: string; webhook_url?: string } = {
      bot_token: botToken.value,
    }
    if (webhookUrl.value) {
      const base = webhookUrl.value.replace(/\/$/, '')
      payload.webhook_url = `${base}/api/telegram/webhook`
    }
    const data = await api.post<{ status: string; webhook_url: string | null }>(
      '/api/telegram/config',
      payload
    )
    configured.value = data.status === 'success'
    currentWebhookUrl.value = data.webhook_url ?? null
    botToken.value = ''
    logger.info('Telegram bot configured successfully')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to save configuration'
    errorMessage.value = msg
    logger.error('Failed to configure Telegram bot', err)
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.telegram-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.panel-content {
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.preference-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  border: none;
  padding: var(--spacing-0);
  margin: var(--spacing-0);
}

.preference-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preference-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: var(--leading-normal);
}

.token-row {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.token-input {
  flex: 1;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-family: monospace;
  transition: border-color var(--transition-fast);
}

.token-input:hover { border-color: var(--color-primary); }
.token-input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-sm);
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.icon-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }

.status-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.status-row--ok { background: color-mix(in srgb, var(--color-success) 15%, transparent); color: var(--color-success); }
.status-row--off { background: var(--bg-tertiary); color: var(--text-tertiary); }

.info-box {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: color-mix(in srgb, var(--color-primary) 10%, transparent);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.error-box {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-error);
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color);
}

.save-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.save-btn:hover:not(:disabled) { opacity: 0.85; }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
