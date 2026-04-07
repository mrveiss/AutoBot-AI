// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Workflow Notification Config Composable
 *
 * Provides API methods for reading and updating per-workflow
 * notification configuration (#3139).
 */

import { ref } from 'vue';
import { getBackendUrl, getApiBase } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';
import { getAuthToken } from '@/utils/fetchWithAuth';
import type { ApiResponse } from '@/types/api';

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
// API helpers
// ---------------------------------------------------------------------------

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<ApiResponse<T>> {
  const url = `${getBackendUrl()}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);

  try {
    const token = getAuthToken();
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      return {
        success: false,
        error: (err as Record<string, string>).detail || `HTTP ${response.status}`,
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    clearTimeout(timeoutId);
    const message = error instanceof Error ? error.message : 'Unknown error';
    logger.error('Notification config API request failed: %s', message);
    return { success: false, error: message };
  }
}

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
      const res = await apiRequest<{
        success: boolean;
        notification_config: NotificationConfig | null;
      }>(`${getApiBase()}/workflow-automation/notification_config/${workflowId}`);

      if (!res.success || !res.data) {
        configError.value = res.error ?? 'Failed to load config';
        return null;
      }
      return res.data.notification_config;
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
      const res = await apiRequest<{ success: boolean }>(
        `${getApiBase()}/workflow-automation/notification_config/${workflowId}`,
        { method: 'PUT', body: JSON.stringify(payload) },
      );
      if (!res.success) {
        configError.value = res.error ?? 'Failed to save config';
        return false;
      }
      return true;
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
