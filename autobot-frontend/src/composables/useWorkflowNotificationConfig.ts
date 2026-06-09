// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Workflow Notification Config Composable
 *
 * Provides API methods for reading and updating per-workflow
 * notification configuration (#3139).
 */

import { ref } from 'vue';
import { getApiBase } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';
import apiClient from '@/utils/ApiClient';

const logger = createLogger('useWorkflowNotificationConfig');

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Notification events that can trigger delivery. */
export type NotificationEvent =
  | 'workflow_completed'
  | 'workflow_failed'
  | 'step_failed'
  | 'approval_needed';

/** Notification delivery channels. */
export type NotificationChannel = 'email' | 'slack' | 'webhook' | 'in_app';

/** Shape of the notification config as returned by the backend. */
export interface NotificationConfig {
  workflow_id: string;
  channels: Record<string, string[]>;
  templates: Record<string, string>;
  email_recipients: string[];
  slack_webhook_url: string | null;
  webhook_url: string | null;
  user_id: string | null;
}

/** Payload sent to the PUT endpoint. */
export interface NotificationConfigPayload {
  enabled: boolean;
  email_recipients: string[];
  slack_webhook_url: string | null;
  webhook_url: string | null;
  channels: Record<string, string[]>;
  templates: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const ALL_EVENTS: NotificationEvent[] = [
  'workflow_completed',
  'workflow_failed',
  'step_failed',
  'approval_needed',
];

export const ALL_CHANNELS: NotificationChannel[] = [
  'email',
  'slack',
  'webhook',
  'in_app',
];

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useWorkflowNotificationConfig() {
  const saving = ref(false);
  const loadingConfig = ref(false);
  const configError = ref<string | null>(null);

  /** Fetch the current notification config for a workflow. */
  async function fetchNotificationConfig(
    workflowId: string,
  ): Promise<NotificationConfig | null> {
    loadingConfig.value = true;
    configError.value = null;
    try {
      const data = await apiClient.get<{
        notification_config: NotificationConfig | null;
      }>(
        `${getApiBase()}/workflow-automation/notification_config/${workflowId}`,
        { timeout: 30_000 },
      );
      return data.notification_config;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load config';
      logger.error('Notification config fetch failed: %s', message);
      configError.value = message;
      return null;
    } finally {
      loadingConfig.value = false;
    }
  }

  /** Save notification config for a workflow. */
  async function saveNotificationConfig(
    workflowId: string,
    payload: NotificationConfigPayload,
  ): Promise<boolean> {
    saving.value = true;
    configError.value = null;
    try {
      await apiClient.put<any>(
        `${getApiBase()}/workflow-automation/notification_config/${workflowId}`,
        payload,
        { timeout: 30_000 },
      );
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save config';
      logger.error('Notification config save failed: %s', message);
      configError.value = message;
      return false;
    } finally {
      saving.value = false;
    }
  }

  return {
    saving,
    loadingConfig,
    configError,
    fetchNotificationConfig,
    saveNotificationConfig,
  };
}
