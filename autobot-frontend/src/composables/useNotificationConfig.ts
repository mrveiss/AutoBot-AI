/**
 * Composable for managing per-workflow notification configuration.
 *
 * Issue #3139: Notification Config UI for Workflows.
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref } from 'vue';
import { getBackendUrl } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('NotificationConfig');

/** Notification events that can trigger channel delivery. */
export const NOTIFICATION_EVENTS = [
  'workflow_completed',
  'workflow_failed',
  'step_failed',
  'approval_needed',
] as const;

export type NotificationEvent = (typeof NOTIFICATION_EVENTS)[number];

/** Channels available for each event. */
export const NOTIFICATION_CHANNELS = [
  'email',
  'slack',
  'webhook',
  'in_app',
] as const;

export type NotificationChannel = (typeof NOTIFICATION_CHANNELS)[number];

/** Shape of the notification config as returned by the API. */
export interface NotificationConfigData {
  email_recipients: string[];
  slack_webhook_url: string | null;
  webhook_url: string | null;
  channels: Record<string, string[]>;
}

function emptyConfig(): NotificationConfigData {
  return {
    email_recipients: [],
    slack_webhook_url: null,
    webhook_url: null,
    channels: {},
  };
}

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || localStorage.getItem('access_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export function useNotificationConfig() {
  const config = ref<NotificationConfigData>(emptyConfig());
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);

  async function fetchConfig(workflowId: string): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const base = getBackendUrl();
      const url = `${base}/workflow-automation/notification_config/${workflowId}`;
      const resp = await fetch(url, { headers: getAuthHeaders() });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      config.value = data.notification_config ?? emptyConfig();
      logger.info('Fetched notification config for workflow', workflowId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      error.value = msg;
      logger.error('Failed to fetch notification config', msg);
    } finally {
      loading.value = false;
    }
  }

  async function saveConfig(workflowId: string): Promise<boolean> {
    saving.value = true;
    error.value = null;
    try {
      const base = getBackendUrl();
      const url = `${base}/workflow-automation/notification_config/${workflowId}`;
      const resp = await fetch(url, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(config.value),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      logger.info('Saved notification config for workflow', workflowId);
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      error.value = msg;
      logger.error('Failed to save notification config', msg);
      return false;
    } finally {
      saving.value = false;
    }
  }

  return { config, loading, saving, error, fetchConfig, saveConfig };
}
