<template>
  <teleport to="body">
    <div v-if="visible" class="notif-overlay" @click.self="$emit('close')">
      <div class="notif-modal" role="dialog" aria-modal="true" :aria-label="$t('workflow.notifications.title')">
        <!-- Header -->
        <div class="notif-header">
          <h3><i class="fas fa-bell"></i> {{ $t('workflow.notifications.title') }}</h3>
          <button class="btn-close" @click="$emit('close')" :aria-label="$t('common.close')">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <!-- Loading state -->
        <div v-if="loading" class="notif-loading">
          <i class="fas fa-spinner fa-spin"></i>
          <span>{{ $t('common.loading') }}</span>
        </div>

        <!-- Form -->
        <form v-else class="notif-body" @submit.prevent="handleSave">
          <!-- Error banner -->
          <div v-if="error" class="notif-error">
            <i class="fas fa-exclamation-triangle"></i> {{ error }}
          </div>

          <!-- Email Recipients -->
          <fieldset class="notif-field">
            <legend>{{ $t('workflow.notifications.emailRecipients') }}</legend>
            <div class="tag-input-wrapper">
              <div class="tag-list">
                <span v-for="(email, idx) in config.email_recipients" :key="idx" class="tag">
                  {{ email }}
                  <button type="button" class="tag-remove" @click="removeEmail(idx)" :aria-label="`Remove ${email}`">
                    <i class="fas fa-times"></i>
                  </button>
                </span>
              </div>
              <input
                v-model="emailInput"
                type="email"
                class="tag-input"
                :placeholder="$t('workflow.notifications.emailPlaceholder')"
                @keydown.enter.prevent="addEmail"
                @keydown.tab.prevent="addEmail"
              />
            </div>
            <p v-if="emailError" class="field-error">{{ emailError }}</p>
          </fieldset>

          <!-- Slack Webhook URL -->
          <fieldset class="notif-field">
            <legend>{{ $t('workflow.notifications.slackWebhook') }}</legend>
            <input
              v-model="config.slack_webhook_url"
              type="url"
              class="notif-input"
              placeholder="https://hooks.slack.com/services/..."
            />
            <p v-if="slackUrlError" class="field-error">{{ slackUrlError }}</p>
          </fieldset>

          <!-- Generic Webhook URL -->
          <fieldset class="notif-field">
            <legend>{{ $t('workflow.notifications.webhookUrl') }}</legend>
            <input
              v-model="config.webhook_url"
              type="url"
              class="notif-input"
              placeholder="https://example.com/webhook"
            />
            <p v-if="webhookUrlError" class="field-error">{{ webhookUrlError }}</p>
          </fieldset>

          <!-- Event-to-Channel Mapping -->
          <fieldset class="notif-field">
            <legend>{{ $t('workflow.notifications.channelMapping') }}</legend>
            <p class="field-hint">{{ $t('workflow.notifications.channelMappingHint') }}</p>
            <div class="channel-grid">
              <div class="channel-header"></div>
              <div v-for="ch in channels" :key="ch" class="channel-header">{{ formatChannel(ch) }}</div>

              <template v-for="evt in events" :key="evt">
                <div class="event-label">{{ formatEvent(evt) }}</div>
                <div v-for="ch in channels" :key="`${evt}-${ch}`" class="channel-cell">
                  <input
                    type="checkbox"
                    :checked="isChannelEnabled(evt, ch)"
                    @change="toggleChannel(evt, ch)"
                    :aria-label="`${formatEvent(evt)} - ${formatChannel(ch)}`"
                  />
                </div>
              </template>
            </div>
          </fieldset>
        </form>

        <!-- Footer -->
        <div class="notif-footer">
          <button type="button" class="btn-secondary" @click="$emit('close')">
            {{ $t('common.cancel') }}
          </button>
          <button
            type="button"
            class="btn-primary"
            :disabled="saving || hasValidationErrors"
            @click="handleSave"
          >
            <i v-if="saving" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-save"></i>
            {{ $t('common.save') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import {
  useNotificationConfig,
  NOTIFICATION_EVENTS,
  NOTIFICATION_CHANNELS,
  type NotificationEvent,
  type NotificationChannel,
} from '@/composables/useNotificationConfig';

const props = defineProps<{
  visible: boolean;
  workflowId: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'saved'): void;
}>();

const { config, loading, saving, error, fetchConfig, saveConfig } = useNotificationConfig();

const emailInput = ref('');
const emailError = ref('');
const events = NOTIFICATION_EVENTS;
const channels = NOTIFICATION_CHANNELS;

watch(
  () => props.visible,
  (val) => {
    if (val && props.workflowId) {
      fetchConfig(props.workflowId);
      emailInput.value = '';
      emailError.value = '';
    }
  },
);

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const slackUrlError = computed(() => {
  const url = config.value.slack_webhook_url;
  if (!url) return '';
  if (!isValidUrl(url)) return 'Invalid URL format';
  return '';
});

const webhookUrlError = computed(() => {
  const url = config.value.webhook_url;
  if (!url) return '';
  if (!isValidUrl(url)) return 'Invalid URL format';
  return '';
});

const hasValidationErrors = computed(() => {
  return !!(slackUrlError.value || webhookUrlError.value);
});

function isValidUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function addEmail(): void {
  const trimmed = emailInput.value.trim();
  if (!trimmed) return;
  if (!EMAIL_REGEX.test(trimmed)) {
    emailError.value = 'Invalid email address';
    return;
  }
  if (config.value.email_recipients.includes(trimmed)) {
    emailError.value = 'Email already added';
    return;
  }
  config.value.email_recipients.push(trimmed);
  emailInput.value = '';
  emailError.value = '';
}

function removeEmail(idx: number): void {
  config.value.email_recipients.splice(idx, 1);
}

function isChannelEnabled(evt: NotificationEvent, ch: NotificationChannel): boolean {
  const list = config.value.channels[evt];
  return Array.isArray(list) && list.includes(ch);
}

function toggleChannel(evt: NotificationEvent, ch: NotificationChannel): void {
  if (!config.value.channels[evt]) {
    config.value.channels[evt] = [];
  }
  const list = config.value.channels[evt];
  const idx = list.indexOf(ch);
  if (idx >= 0) {
    list.splice(idx, 1);
  } else {
    list.push(ch);
  }
}

function formatEvent(evt: string): string {
  return evt.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
}

function formatChannel(ch: string): string {
  if (ch === 'in_app') return 'In-App';
  return ch.charAt(0).toUpperCase() + ch.slice(1);
}

async function handleSave(): Promise<void> {
  if (hasValidationErrors.value) return;
  const ok = await saveConfig(props.workflowId);
  if (ok) {
    emit('saved');
    emit('close');
  }
}
</script>

<style scoped>
.notif-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.notif-modal {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 560px;
  max-width: 95vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.notif-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.notif-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.notif-header h3 i { color: var(--color-primary); }

.btn-close {
  padding: 6px 8px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 4px;
  font-size: 14px;
}
.btn-close:hover { background: var(--bg-hover); color: var(--text-primary); }

.notif-loading {
  padding: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-tertiary);
}

.notif-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.notif-error {
  padding: 10px 14px;
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: 6px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.notif-field {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 14px;
  margin: 0;
}

.notif-field legend {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  padding: 0 6px;
}

.notif-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.notif-input:focus { border-color: var(--color-primary); }

.tag-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: 14px;
  font-size: 12px;
  font-weight: 500;
}

.tag-remove {
  padding: 0;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 10px;
  opacity: 0.7;
}
.tag-remove:hover { opacity: 1; }

.tag-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.tag-input:focus { border-color: var(--color-primary); }

.field-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-error);
}

.field-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.channel-grid {
  display: grid;
  grid-template-columns: 1fr repeat(4, 64px);
  gap: 4px;
  align-items: center;
}

.channel-header {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-align: center;
  text-transform: uppercase;
  padding: 4px;
}

.event-label {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 6px 4px;
}

.channel-cell {
  display: flex;
  justify-content: center;
  padding: 6px 4px;
}

.channel-cell input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.notif-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  padding: 8px 20px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  padding: 8px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.btn-secondary:hover { background: var(--bg-hover); }
</style>
