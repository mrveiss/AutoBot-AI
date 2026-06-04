<template>
  <teleport to="body">
    <div v-if="visible" class="notif-overlay" @click.self="$emit('close')">
      <div
        ref="dialogRef"
        class="notif-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="$t('workflow.notifications.title')"
        tabindex="-1"
        @keydown="onFocusTrapKeydown"
        @keydown.escape="$emit('close')"
      >
        <!-- Header -->
        <div class="notif-header">
          <h3><Icon name="bell" /> {{ $t('workflow.notifications.title') }}</h3>
          <button class="btn-close" @click="$emit('close')" :aria-label="$t('common.close')">
            <Icon name="times" />
          </button>
        </div>

        <!-- Loading state -->
        <div v-if="loading" class="notif-loading">
          <Icon name="spinner" class="animate-spin" />
          <span>{{ $t('common.loading') }}</span>
        </div>

        <!-- Form -->
        <form v-else class="notif-body" @submit.prevent="handleSave">
          <!-- Error banner -->
          <div v-if="error" class="notif-error">
            <Icon name="exclamation-triangle" /> {{ error }}
          </div>

          <!-- Email Recipients -->
          <fieldset class="notif-field">
            <legend>{{ $t('workflow.notifications.emailRecipients') }}</legend>
            <div class="tag-input-wrapper">
              <div class="tag-list">
                <span v-for="(email, idx) in config.email_recipients" :key="idx" class="tag">
                  {{ email }}
                  <button type="button" class="tag-remove" @click="removeEmail(idx)" :aria-label="`Remove ${email}`">
                    <Icon name="times" />
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
            <Icon name="spinner" class="animate-spin" v-if="saving" />
            <Icon name="save" v-else />
            {{ $t('common.save') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch, toRef } from 'vue';
import {
  useNotificationConfig,
  NOTIFICATION_EVENTS,
  NOTIFICATION_CHANNELS,
  type NotificationEvent,
  type NotificationChannel,
} from '@/composables/useNotificationConfig';
import { useFocusTrap } from '@/composables/useFocusTrap';
import { useFocusRestore } from '@/composables/useFocusRestore';
import { useInitialFocus } from '@/composables/useInitialFocus';
import { useBodyScrollLock } from '@/composables/useBodyScrollLock';

const props = defineProps<{
  visible: boolean;
  workflowId: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'saved'): void;
}>();

const dialogRef = ref<HTMLElement | null>(null);
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef);
useFocusRestore(toRef(props, 'visible'));
useBodyScrollLock(toRef(props, 'visible'));
const { focusFirst } = useInitialFocus(dialogRef);
watch(() => props.visible, (open) => { if (open) focusFirst() }, { immediate: true });

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
  z-index: var(--z-modal);
}

.notif-modal {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  width: 560px;
  max-width: 95vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}

.notif-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.notif-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.notif-header h3 i { color: var(--color-primary); }

.btn-close {
  padding: var(--spacing-1-5) var(--spacing-2);
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
}
.btn-close:hover { background: var(--bg-hover); color: var(--text-primary); }

.notif-loading {
  padding: var(--spacing-12);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  color: var(--text-tertiary);
}

.notif-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.notif-error {
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.notif-field {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
  margin: var(--spacing-0);
}

.notif-field legend {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  padding: var(--spacing-0) var(--spacing-1-5);
}

.notif-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
}
.notif-input:focus { border-color: var(--color-primary); }
.notif-input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

.tag-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1) var(--spacing-2-5);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-2xl);
  font-size: var(--text-xs);
  font-weight: 500;
}

.tag-remove {
  padding: var(--spacing-0);
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: var(--text-xs);
  opacity: 0.7;
}
.tag-remove:hover { opacity: 1; }

.tag-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
}
.tag-input:focus { border-color: var(--color-primary); }
.tag-input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }

.field-error {
  margin: var(--spacing-1-5) var(--spacing-0) var(--spacing-0);
  font-size: var(--text-xs);
  color: var(--color-error);
}

.field-hint {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2-5);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.channel-grid {
  display: grid;
  grid-template-columns: 1fr repeat(4, 64px);
  gap: var(--spacing-1);
  align-items: center;
}

.channel-header {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-tertiary);
  text-align: center;
  text-transform: uppercase;
  padding: var(--spacing-1);
}

.event-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--spacing-1-5) var(--spacing-1);
}

.channel-cell {
  display: flex;
  justify-content: center;
  padding: var(--spacing-1-5) var(--spacing-1);
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
  gap: var(--spacing-2-5);
  padding: var(--spacing-3-5) var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  padding: var(--spacing-2) var(--spacing-5);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
}
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-5);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
}
.btn-secondary:hover { background: var(--bg-hover); }
</style>
