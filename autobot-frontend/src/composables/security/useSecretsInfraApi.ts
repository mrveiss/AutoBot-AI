// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useSecretsInfraApi — thin fetch wrappers for infrastructure-host and
 * secrets-usage endpoints used by SecretsManager. Renamed from
 * useSecretsAuditApi (#12160): it fetches infra hosts, not audit logs — the
 * old name collided with the real composables/useSecretsAuditApi (audit-log
 * entries).
 *
 * Extracted from SecretsManager.vue (issue #6081).
 */

import apiClient from '@/utils/ApiClient';
import { secretsApiClient } from '@/utils/SecretsApiClient';

export interface InfraHost {
  id: string;
  name: string;
  scope?: string;
  chat_id?: string;
  description?: string;
  tags?: string[];
  created_at?: string;
  updated_at?: string;
  host: string;
  ssh_port: number;
  vnc_port?: number | null;
  username: string;
  auth_type: string;
  capabilities?: Record<string, unknown>;
}

export interface InfraHostsResponse {
  hosts: InfraHost[];
}

export interface SecretsUsageResponse {
  secrets_usage: Record<string, unknown[]>;
}

/** A legacy infrastructure host shaped as a secret row, flagged so delete uses the legacy API. */
export function infraHostToSecret(host: InfraHost) {
  return {
    id: host.id,
    name: host.name,
    type: 'infrastructure_host',
    scope: host.scope || 'general',
    chat_id: host.chat_id,
    description: host.description || `${host.username}@${host.host}:${host.ssh_port}`,
    tags: host.tags || [],
    created_at: host.created_at,
    updated_at: host.updated_at,
    expires_at: null,
    metadata: {
      host: host.host,
      ssh_port: host.ssh_port,
      vnc_port: host.vnc_port,
      username: host.username,
      auth_type: host.auth_type as 'ssh_key' | 'password',
      capabilities: host.capabilities as string[] | undefined
    },
    _isLegacyHost: true // Flag for legacy hosts that need different delete API
  };
}

/** The metadata key linking a host's VNC password secret to the host (read by api/vnc_host_target.py). */
const VNC_COMPANION_HOST_KEY = 'vnc_host_id';

type SecretLike = { id: string; type?: string; metadata?: Record<string, unknown> };

/**
 * #22145: a host's VNC password is its own secret, linked by host id, so the chat
 * Desktop can authenticate to that host's VNC endpoint with it. Creates it, or replaces
 * the value of the one already linked (so an EXISTING host can get or change its password).
 * `created` is a create response (`{ data: { id } }`) or the same shape built from a known host id.
 */
export async function createVncCompanion(
  created: unknown,
  form: { type: string; name: string; host: string; capabilities: string[]; vnc_password: string },
  hostData: Record<string, unknown>,
  t: (key: string, params?: Record<string, unknown>) => string,
  existing: SecretLike[] = []
): Promise<void> {
  if (form.type !== 'infrastructure_host' || !form.capabilities.includes('vnc') || !form.vnc_password) return;
  const hostId = (created as { data?: { id?: string } } | null)?.data?.id;
  if (!hostId) throw new Error(t('security.secretsManager.vncCompanionNoHostId'));
  const linked = existing.find((s) => s.type === 'password' && s.metadata?.[VNC_COMPANION_HOST_KEY] === hostId);
  if (linked) {
    await secretsApiClient.updateSecret(linked.id, { value: form.vnc_password } as never, {
      chatId: hostData.chat_id as string | null | undefined
    });
    return;
  }
  await secretsApiClient.createSecret({
    name: t('security.secretsManager.vncCompanionName', { name: form.name }),
    type: 'password',
    scope: hostData.scope,
    chat_id: hostData.chat_id,
    value: form.vnc_password,
    description: t('security.secretsManager.vncCompanionDescription', { host: form.host }),
    metadata: { [VNC_COMPANION_HOST_KEY]: hostId }
  } as unknown as Parameters<typeof secretsApiClient.createSecret>[0]);
}

export function useSecretsInfraApi() {
  /** Fetch legacy infrastructure hosts from the old API. */
  async function fetchInfraHosts(): Promise<InfraHostsResponse> {
    return apiClient.get<InfraHostsResponse>(`/api/infrastructure/hosts`)
      .catch(() => ({ hosts: [] }));
  }

  /** Fetch workflow-usage mapping for secrets (#1415). */
  async function fetchSecretsUsage(): Promise<SecretsUsageResponse> {
    return apiClient.get<SecretsUsageResponse>(`/api/templates/templates/secrets-usage`)
      .catch(() => ({ secrets_usage: {} }));
  }

  /** Delete a legacy infrastructure host by id. */
  async function deleteInfraHost(id: string): Promise<void> {
    await apiClient.delete<unknown>(`/api/infrastructure/hosts/${id}`);
  }

  return { fetchInfraHosts, fetchSecretsUsage, deleteInfraHost };
}
