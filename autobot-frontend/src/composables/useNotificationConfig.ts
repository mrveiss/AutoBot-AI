// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Composable for managing per-workflow notification configuration.
 *
 * Issue #3139: Notification Config UI for Workflows.
 * Issue #19903: the one notification-config composable. It replaces the
 * pair `useNotificationConfig` + `useWorkflowNotificationConfig`, which both
 * read and wrote the same endpoint with two different payload shapes: the
 * panel sent `enabled` and an empty `templates` (wiping stored templates on
 * every save), the modal sent neither. This keeps the whole stored shape
 * round-tripping, so a save changes only what the user edited.
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { ref } from 'vue';
import { getApiBase } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';
import { useLoadingState } from '@/composables/useLoadingState';
import apiClient from '@/utils/ApiClient';
import type { NotificationChannel, NotificationEvent } from '@/types/_generated/workflow';

const logger = createLogger('NotificationConfig');

/** Request timeout for the notification-config endpoint (ms). */
const REQUEST_TIMEOUT_MS = 30_000;

export type { NotificationChannel, NotificationEvent };

/**
 * The events and channels the notification config UI offers: typed SUBSETS of the generated
 * backend vocabulary (#19334), checked by `satisfies` so a value the backend lacks fails to compile.
 * `service_failed` and `telegram` are not offered here -- the form has no telegram_chat_id field.
 */
export const NOTIFICATION_EVENTS = [
  'workflow_completed',
  'workflow_failed',
  'step_failed',
  'approval_needed',
] as const satisfies readonly NotificationEvent[];

/** Channels available for each event. */
export const NOTIFICATION_CHANNELS = [
  'email',
  'slack',
  'webhook',
  'in_app',
] as const satisfies readonly NotificationChannel[];

/** Shape of the notification config, as read from and written to the API. */
export interface NotificationConfigData {
  enabled: boolean;
  email_recipients: string[];
  slack_webhook_url: string | null;
  webhook_url: string | null;
  channels: Record<string, string[]>;
  templates: Record<string, string>;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** True for a syntactically valid email address. */
export function isValidEmail(value: string): boolean {
  return EMAIL_REGEX.test(value);
}

/** True for an absolute http(s) URL. */
export function isValidUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

/** Split a comma-separated recipient field into trimmed, non-empty addresses. */
export function parseRecipients(raw: string): string[] {
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export function emptyNotificationConfig(): NotificationConfigData {
  return {
    enabled: false,
    email_recipients: [],
    slack_webhook_url: null,
    webhook_url: null,
    channels: {},
    templates: {},
  };
}

/** Pick the stored fields; the GET response also carries workflow_id and user_id. */
function fromApi(stored: Partial<NotificationConfigData>): NotificationConfigData {
  return {
    enabled: true,
    email_recipients: stored.email_recipients ?? [],
    slack_webhook_url: stored.slack_webhook_url ?? null,
    webhook_url: stored.webhook_url ?? null,
    channels: { ...(stored.channels ?? {}) },
    templates: { ...(stored.templates ?? {}) },
  };
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function configUrl(workflowId: string): string {
  return `${getApiBase()}/workflow-automation/notification_config/${workflowId}`;
}

export function useNotificationConfig() {
  const config = ref<NotificationConfigData>(emptyNotificationConfig());
  const { isLoading: loading, wrap } = useLoadingState();
  const { isLoading: saving, wrap: wrapSaving } = useLoadingState();
  const error = ref<string | null>(null);

  function reset(): void {
    config.value = emptyNotificationConfig();
    error.value = null;
  }

  /** Load a workflow's config. Resolves true when one was stored, false when none exists or the load failed. */
  async function fetchConfig(workflowId: string): Promise<boolean> {
    reset();
    return wrap(async () => {
      try {
        const data = await apiClient.get<{
          notification_config?: Partial<NotificationConfigData> | null;
        }>(configUrl(workflowId), { timeout: REQUEST_TIMEOUT_MS });
        if (!data.notification_config) return false;
        config.value = fromApi(data.notification_config);
        logger.info('Fetched notification config for workflow', workflowId);
        return true;
      } catch (err) {
        error.value = errorMessage(err);
        logger.error('Failed to fetch notification config', error.value);
        return false;
      }
    });
  }

  async function saveConfig(workflowId: string): Promise<boolean> {
    error.value = null;
    return wrapSaving(async () => {
      try {
        await apiClient.put<unknown>(configUrl(workflowId), config.value, {
          timeout: REQUEST_TIMEOUT_MS,
        });
        logger.info('Saved notification config for workflow', workflowId);
        return true;
      } catch (err) {
        error.value = errorMessage(err);
        logger.error('Failed to save notification config', error.value);
        return false;
      }
    });
  }

  function isChannelEnabled(event: string, channel: string): boolean {
    return config.value.channels[event]?.includes(channel) ?? false;
  }

  function toggleChannel(event: string, channel: string): void {
    const list = (config.value.channels[event] ??= []);
    const idx = list.indexOf(channel);
    if (idx >= 0) {
      list.splice(idx, 1);
    } else {
      list.push(channel);
    }
  }

  return {
    config,
    loading,
    saving,
    error,
    reset,
    fetchConfig,
    saveConfig,
    isChannelEnabled,
    toggleChannel,
  };
}
