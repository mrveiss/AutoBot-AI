<template>
  <div class="notification-config">
    <!-- Workflow Selector -->
    <div class="config-section">
      <label class="field-label" for="nc-workflow-select">
        {{ $t('workflow.notifications.selectWorkflow') }}
      </label>
      <select
        id="nc-workflow-select"
        class="field-input"
        :value="selectedWorkflowId"
        @change="handleWorkflowChange(($event.target as HTMLSelectElement).value)"
        :disabled="loadingConfig"
      >
        <option value="">{{ $t('workflow.notifications.chooseWorkflow') }}</option>
        <option
          v-for="wf in workflows"
          :key="wf.workflow_id"
          :value="wf.workflow_id"
        >
          {{ wf.name }} ({{ wf.workflow_id.slice(0, 8) }})
        </option>
      </select>
    </div>

    <!-- Loading -->
    <div v-if="loadingConfig" class="loading-indicator">
      <svg class="spinner" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-dasharray="30 70" />
      </svg>
      <span>{{ $t('workflow.notifications.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-if="configError" class="error-banner" role="alert">
      <span>{{ configError }}</span>
    </div>

    <!-- Config Form -->
    <template v-if="selectedWorkflowId && !loadingConfig">
      <!-- Enable Toggle -->
      <div class="config-section toggle-section">
        <label class="toggle-label">
          <input
            type="checkbox"
            v-model="enabled"
            class="toggle-input"
          />
          <span class="toggle-text">{{ $t('workflow.notifications.enableNotifications') }}</span>
        </label>
      </div>

      <fieldset :disabled="!enabled" class="config-fieldset">
        <!-- Email Recipients -->
        <div class="config-section">
          <label class="field-label" for="nc-email-recipients">
            {{ $t('workflow.notifications.emailRecipients') }}
          </label>
          <input
            id="nc-email-recipients"
            type="text"
            class="field-input"
            v-model="emailRecipientsRaw"
            :placeholder="$t('workflow.notifications.emailPlaceholder')"
          />
          <span class="field-hint">{{ $t('workflow.notifications.emailHint') }}</span>
        </div>

        <!-- Slack Webhook -->
        <div class="config-section">
          <label class="field-label" for="nc-slack-webhook">
            {{ $t('workflow.notifications.slackWebhookUrl') }}
          </label>
          <input
            id="nc-slack-webhook"
            type="url"
            class="field-input"
            v-model="slackWebhookUrl"
            placeholder="https://hooks.slack.com/services/..."
          />
        </div>

        <!-- Generic Webhook -->
        <div class="config-section">
          <label class="field-label" for="nc-webhook-url">
            {{ $t('workflow.notifications.webhookUrl') }}
          </label>
          <input
            id="nc-webhook-url"
            type="url"
            class="field-input"
            v-model="webhookUrl"
            placeholder="https://example.com/webhook"
          />
        </div>

        <!-- Channel-to-Event Routing Matrix -->
        <div class="config-section">
          <h4 class="section-heading">{{ $t('workflow.notifications.eventRouting') }}</h4>
          <p class="field-hint">{{ $t('workflow.notifications.eventRoutingHint') }}</p>

          <div class="routing-matrix" role="group" :aria-label="$t('workflow.notifications.eventRouting')">
            <!-- Header row -->
            <div class="matrix-row matrix-header">
              <div class="matrix-cell matrix-label-cell"></div>
              <div
                v-for="channel in availableChannels"
                :key="channel"
                class="matrix-cell matrix-channel-header"
              >
                {{ channelLabel(channel) }}
              </div>
            </div>
            <!-- Event rows -->
            <div
              v-for="event in allEvents"
              :key="event"
              class="matrix-row"
            >
              <div class="matrix-cell matrix-label-cell">
                {{ eventLabel(event) }}
              </div>
              <div
                v-for="channel in availableChannels"
                :key="`${event}-${channel}`"
                class="matrix-cell"
              >
                <input
                  type="checkbox"
                  :checked="isChannelEnabled(event, channel)"
                  @change="toggleChannel(event, channel)"
                  :aria-label="`${eventLabel(event)} via ${channelLabel(channel)}`"
                  class="matrix-checkbox"
                />
              </div>
            </div>
          </div>
        </div>
      </fieldset>

      <!-- Save Button -->
      <div class="config-actions">
        <button
          class="btn-save"
          :disabled="saving"
          @click="handleSave"
        >
          <svg v-if="saving" class="spinner btn-spinner" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-dasharray="30 70" />
          </svg>
          {{ saving ? $t('workflow.notifications.saving') : $t('workflow.notifications.save') }}
        </button>
        <span v-if="saveSuccess" class="save-success">
          {{ $t('workflow.notifications.saved') }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import {
  useWorkflowNotificationConfig,
  ALL_EVENTS,
  type NotificationEvent,
  type NotificationChannel,
  type NotificationConfigPayload,
} from '@/composables/useWorkflowNotificationConfig';

const logger = createLogger('WorkflowNotificationConfig');
const { t } = useI18n();

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface WorkflowSummary {
  workflow_id: string;
  name: string;
  [key: string]: unknown;
}

defineProps<{
  workflows: WorkflowSummary[];
}>();

const emit = defineEmits<{
  (e: 'saved', workflowId: string): void;
}>();

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

const {
  saving,
  loadingConfig,
  configError,
  fetchNotificationConfig,
  saveNotificationConfig,
} = useWorkflowNotificationConfig();

// ---------------------------------------------------------------------------
// Local state
// ---------------------------------------------------------------------------

const selectedWorkflowId = ref('');
const enabled = ref(false);
const emailRecipientsRaw = ref('');
const slackWebhookUrl = ref('');
const webhookUrl = ref('');
const channels = ref<Record<string, string[]>>({});
const saveSuccess = ref(false);

const allEvents = ALL_EVENTS;

/** Only show channels for which the user has provided a target. */
const availableChannels = computed<NotificationChannel[]>(() => {
  const result: NotificationChannel[] = [];
  if (emailRecipientsRaw.value.trim()) result.push('email');
  if (slackWebhookUrl.value.trim()) result.push('slack');
  if (webhookUrl.value.trim()) result.push('webhook');
  result.push('in_app');
  return result;
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function channelLabel(ch: NotificationChannel): string {
  const map: Record<NotificationChannel, string> = {
    email: t('workflow.notifications.channelEmail'),
    slack: t('workflow.notifications.channelSlack'),
    webhook: t('workflow.notifications.channelWebhook'),
    in_app: t('workflow.notifications.channelInApp'),
  };
  return map[ch] ?? ch;
}

function eventLabel(ev: NotificationEvent): string {
  const map: Record<NotificationEvent, string> = {
    workflow_completed: t('workflow.notifications.eventCompleted'),
    workflow_failed: t('workflow.notifications.eventFailed'),
    step_failed: t('workflow.notifications.eventStepFailed'),
    approval_needed: t('workflow.notifications.eventApprovalNeeded'),
  };
  return map[ev] ?? ev;
}

function isChannelEnabled(event: string, channel: string): boolean {
  return channels.value[event]?.includes(channel) ?? false;
}

function toggleChannel(event: string, channel: string): void {
  if (!channels.value[event]) {
    channels.value[event] = [];
  }
  const idx = channels.value[event].indexOf(channel);
  if (idx >= 0) {
    channels.value[event].splice(idx, 1);
  } else {
    channels.value[event].push(channel);
  }
}

function resetForm(): void {
  enabled.value = false;
  emailRecipientsRaw.value = '';
  slackWebhookUrl.value = '';
  webhookUrl.value = '';
  channels.value = {};
  saveSuccess.value = false;
}

// ---------------------------------------------------------------------------
// Load config when workflow selection changes
// ---------------------------------------------------------------------------

async function handleWorkflowChange(workflowId: string): Promise<void> {
  selectedWorkflowId.value = workflowId;
  resetForm();
  if (!workflowId) return;

  const config = await fetchNotificationConfig(workflowId);
  if (config) {
    enabled.value = true;
    emailRecipientsRaw.value = (config.email_recipients ?? []).join(', ');
    slackWebhookUrl.value = config.slack_webhook_url ?? '';
    webhookUrl.value = config.webhook_url ?? '';
    channels.value = { ...config.channels };
  }
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

async function handleSave(): Promise<void> {
  if (!selectedWorkflowId.value) return;
  saveSuccess.value = false;

  const recipients = emailRecipientsRaw.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  const payload: NotificationConfigPayload = {
    enabled: enabled.value,
    email_recipients: recipients,
    slack_webhook_url: slackWebhookUrl.value || null,
    webhook_url: webhookUrl.value || null,
    channels: channels.value,
    templates: {},
  };

  const ok = await saveNotificationConfig(selectedWorkflowId.value, payload);
  if (ok) {
    saveSuccess.value = true;
    logger.info('Notification config saved for %s', selectedWorkflowId.value);
    emit('saved', selectedWorkflowId.value);
  }
}

// Clear success flash after 3 seconds
watch(saveSuccess, (val) => {
  if (val) {
    setTimeout(() => { saveSuccess.value = false; }, 3000);
  }
});
</script>

<style scoped>
.notification-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  max-width: 48rem;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
}

.field-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary, #e2e8f0);
}

.field-input {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default, #374151);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary, #1e293b);
  color: var(--text-primary, #e2e8f0);
  font-size: var(--text-sm);
  transition: border-color var(--duration-150);
}
.field-input:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
}
.field-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.field-hint {
  font-size: var(--text-xs);
  color: var(--text-secondary, #94a3b8);
}

.toggle-section {
  flex-direction: row;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  user-select: none;
}

.toggle-input {
  width: 1.125rem;
  height: 1.125rem;
  accent-color: var(--color-primary, #3b82f6);
}

.toggle-text {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary, #e2e8f0);
}

.config-fieldset {
  border: none;
  padding: var(--spacing-0);
  margin: var(--spacing-0);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}
.config-fieldset:disabled {
  opacity: 0.45;
  pointer-events: none;
}

.section-heading {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin: var(--spacing-0);
}

/* Routing matrix */
.routing-matrix {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default, #374151);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-top: var(--spacing-2);
}

.matrix-row {
  display: flex;
  align-items: center;
}

.matrix-row:not(:last-child) {
  border-bottom: 1px solid var(--border-default, #374151);
}

.matrix-header {
  background: var(--color-bg-tertiary, #0f172a);
  font-weight: 600;
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary, #94a3b8);
}

.matrix-cell {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  text-align: center;
  font-size: 0.8125rem;
}

.matrix-label-cell {
  flex: 2;
  text-align: left;
  font-weight: 500;
  color: var(--text-primary, #e2e8f0);
}

.matrix-channel-header {
  color: var(--text-secondary, #94a3b8);
}

.matrix-checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: var(--color-primary, #3b82f6);
  cursor: pointer;
}

/* Actions */
.config-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding-top: var(--spacing-2);
}

.btn-save {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-5);
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-primary, #3b82f6);
  color: #fff;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background var(--duration-150);
}
.btn-save:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
}
.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-success {
  font-size: 0.8125rem;
  color: var(--color-success, #22c55e);
  font-weight: 500;
}

/* Loading / Error */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary, #94a3b8);
  padding: var(--spacing-3) var(--spacing-0);
}

.spinner {
  width: 1.25rem;
  height: 1.25rem;
  animation: spin 0.8s linear infinite;
}

.btn-spinner {
  width: 1rem;
  height: 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-banner {
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
  font-size: 0.8125rem;
}
</style>
