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
