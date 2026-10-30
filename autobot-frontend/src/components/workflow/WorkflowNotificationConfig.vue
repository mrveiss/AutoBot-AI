<template>
  <div class="notification-config">
    <!-- Workflow Selector -->
    <div v-if="!workflowId" class="config-section">
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
          v-for="wf in workflows ?? []"
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
            v-model="config.enabled"
            class="toggle-input"
          />
          <span class="toggle-text">{{ $t('workflow.notifications.enableNotifications') }}</span>
        </label>
      </div>

      <fieldset :disabled="!config.enabled" class="config-fieldset">
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
          <p v-if="invalidEmails.length" class="field-error">
            {{ $t('workflow.notifications.invalidEmail', { emails: invalidEmails.join(', ') }) }}
          </p>
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
            v-model="config.slack_webhook_url"
            placeholder="https://hooks.slack.com/services/..."
          />
          <p v-if="slackUrlInvalid" class="field-error">{{ $t('workflow.notifications.invalidUrl') }}</p>
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
            v-model="config.webhook_url"
            placeholder="https://example.com/webhook"
          />
          <p v-if="webhookUrlInvalid" class="field-error">{{ $t('workflow.notifications.invalidUrl') }}</p>
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
          :disabled="saving || hasValidationErrors"
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
/**
 * WorkflowNotificationConfig -- the one per-workflow notification form (#3139).
 *
 * Two uses, one component (#19903): the Notifications section of the workflow
 * builder passes `workflows` and gets a workflow picker; the workflow runner's
 * dialog passes `workflowId` and gets the form for that workflow alone.
 */
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import {
  useNotificationConfig,
  isValidEmail,
  isValidUrl,
  parseRecipients,
  NOTIFICATION_EVENTS,
  type NotificationEvent,
  type NotificationChannel,
} from '@/composables/useNotificationConfig';

const logger = createLogger('WorkflowNotificationConfig');
const { t } = useI18n();

interface WorkflowSummary {
  workflow_id: string;
  name: string;
  [key: string]: unknown;
}

const props = defineProps<{
  /** Offered in a picker. Omit when `workflowId` fixes the workflow. */
  workflows?: WorkflowSummary[];
  /** Fixes the workflow and hides the picker. */
  workflowId?: string;
}>();

const emit = defineEmits<{
  (e: 'saved', workflowId: string): void;
}>();

const {
  config,
  loading: loadingConfig,
  saving,
  error: configError,
  reset,
  fetchConfig,
  saveConfig,
  isChannelEnabled,
  toggleChannel,
} = useNotificationConfig();

const selectedWorkflowId = ref(props.workflowId ?? '');
const emailRecipientsRaw = ref('');
const saveSuccess = ref(false);
const allEvents = NOTIFICATION_EVENTS;

/** Only show channels for which the user has provided a target. */
const availableChannels = computed<NotificationChannel[]>(() => {
  const result: NotificationChannel[] = [];
  if (emailRecipientsRaw.value.trim()) result.push('email');
  if (config.value.slack_webhook_url?.trim()) result.push('slack');
  if (config.value.webhook_url?.trim()) result.push('webhook');
  result.push('in_app');
  return result;
});

const invalidEmails = computed(() => parseRecipients(emailRecipientsRaw.value).filter((e) => !isValidEmail(e)));
const slackUrlInvalid = computed(() => !!config.value.slack_webhook_url && !isValidUrl(config.value.slack_webhook_url));
const webhookUrlInvalid = computed(() => !!config.value.webhook_url && !isValidUrl(config.value.webhook_url));
const hasValidationErrors = computed(
  () => invalidEmails.value.length > 0 || slackUrlInvalid.value || webhookUrlInvalid.value,
);

function channelLabel(ch: NotificationChannel): string {
  const map: Record<NotificationChannel, string> = {
    email: t('workflow.notifications.channelEmail'),
    slack: t('workflow.notifications.channelSlack'),
    webhook: t('workflow.notifications.channelWebhook'),
    in_app: t('workflow.notifications.channelInApp'),
    telegram: t('workflow.notifications.channelTelegram'),
  };
  return map[ch] ?? ch;
}

function eventLabel(ev: NotificationEvent): string {
  const map: Record<NotificationEvent, string> = {
    workflow_completed: t('workflow.notifications.eventCompleted'),
    workflow_failed: t('workflow.notifications.eventFailed'),
    step_failed: t('workflow.notifications.eventStepFailed'),
    approval_needed: t('workflow.notifications.eventApprovalNeeded'),
    service_failed: t('workflow.notifications.eventServiceFailed'),
  };
  return map[ev] ?? ev;
}

async function handleWorkflowChange(workflowId: string): Promise<void> {
  selectedWorkflowId.value = workflowId;
  saveSuccess.value = false;
  emailRecipientsRaw.value = '';
  reset();
  if (!workflowId) return;
  await fetchConfig(workflowId);
  emailRecipientsRaw.value = config.value.email_recipients.join(', ');
}

watch(
  () => props.workflowId,
  (id) => {
    if (id) void handleWorkflowChange(id);
  },
  { immediate: true },
);

async function handleSave(): Promise<void> {
  if (!selectedWorkflowId.value || hasValidationErrors.value) return;
  saveSuccess.value = false;
  config.value.email_recipients = parseRecipients(emailRecipientsRaw.value);
  config.value.slack_webhook_url = config.value.slack_webhook_url || null;
  config.value.webhook_url = config.value.webhook_url || null;

  if (await saveConfig(selectedWorkflowId.value)) {
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
  color: var(--text-primary);
}

.field-input {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-secondary, var(--wfnotif-input-bg));
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: border-color var(--duration-150);
}
.field-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
}
.field-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.field-hint {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.field-error {
  font-size: var(--text-xs);
  color: var(--wfnotif-error-text);
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
  accent-color: var(--color-primary);
}

.toggle-text {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
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
  color: var(--text-primary);
  margin: var(--spacing-0);
}

/* Routing matrix */
.routing-matrix {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-top: var(--spacing-2);
}

.matrix-row {
  display: flex;
  align-items: center;
}

.matrix-row:not(:last-child) {
  border-bottom: 1px solid var(--border-default);
}

.matrix-header {
  background: var(--color-bg-tertiary, var(--wfnotif-header-bg));
  font-weight: 600;
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
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
  color: var(--text-primary);
}

.matrix-channel-header {
  color: var(--text-secondary);
}

.matrix-checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: var(--color-primary);
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
  background: var(--color-primary);
  color: var(--wfnotif-on-accent);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background var(--duration-150);
}
.btn-save:hover:not(:disabled) {
  background: var(--color-primary-hover);
}
.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-success {
  font-size: 0.8125rem;
  color: var(--color-success);
  font-weight: 500;
}

/* Loading / Error */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
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
  color: var(--wfnotif-error-text);
  font-size: 0.8125rem;
}
</style>
