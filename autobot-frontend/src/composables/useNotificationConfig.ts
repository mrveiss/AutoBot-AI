// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Composable for managing per-workflow notification configuration.
 *
 * Issue #3139: Notification Config UI for Workflows.
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { ref } from 'vue';
import { getApiBase } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';
import { useLoadingState } from '@/composables/useLoadingState';
import apiClient from '@/utils/ApiClient';

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


export function useNotificationConfig() {
  const config = ref<NotificationConfigData>(emptyConfig());
  const { isLoading: loading, wrap } = useLoadingState();
  const { isLoading: saving, wrap: wrapSaving } = useLoadingState();
  const error = ref<string | null>(null);

  async function fetchConfig(workflowId: string): Promise<void> {
    error.value = null;
    await wrap(async () => {
      try {
        const url = `${getApiBase()}/workflow-automation/notification_config/${workflowId}`;
        const data = await apiClient.get<{ notification_config?: NotificationConfigData }>(url);
        config.value = data.notification_config ?? emptyConfig();
        logger.info('Fetched notification config for workflow', workflowId);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        error.value = msg;
        logger.error('Failed to fetch notification config', msg);
      }
    });
  }

  async function saveConfig(workflowId: string): Promise<boolean> {
    error.value = null;
    return wrapSaving(async () => {
      try {
        const url = `${getApiBase()}/workflow-automation/notification_config/${workflowId}`;
        await apiClient.put<unknown>(url, config.value);
        logger.info('Saved notification config for workflow', workflowId);
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        error.value = msg;
        logger.error('Failed to save notification config', msg);
        return false;
      }
    });
  }

  return { config, loading, saving, error, fetchConfig, saveConfig };
}
