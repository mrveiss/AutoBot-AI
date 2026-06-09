// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useSecretsAuditApi — thin fetch wrappers for infrastructure-host and
 * workflow-usage endpoints used by SecretsManager.
 *
 * Extracted from SecretsManager.vue (issue #6081).
 */

import { getBackendUrl } from '@/config/ssot-config';
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

export function useSecretsAuditApi() {
  /** Fetch legacy infrastructure hosts from the old API. */
  async function fetchInfraHosts(): Promise<InfraHostsResponse> {
    const backendUrl = getBackendUrl();
    return apiClient.get<InfraHostsResponse>(`${backendUrl}/api/infrastructure/hosts`)
      .catch(() => ({ hosts: [] }));
  }

  /** Fetch workflow-usage mapping for secrets (#1415). */
  async function fetchSecretsUsage(): Promise<SecretsUsageResponse> {
    const backendUrl = getBackendUrl();
    return apiClient.get<SecretsUsageResponse>(`${backendUrl}/api/templates/templates/secrets-usage`)
      .catch(() => ({ secrets_usage: {} }));
  }

  /** Delete a legacy infrastructure host by id. */
  async function deleteInfraHost(id: string): Promise<void> {
    const backendUrl = getBackendUrl();
    await apiClient.delete<any>(`${backendUrl}/api/infrastructure/hosts/${id}`);
  }

  return { fetchInfraHosts, fetchSecretsUsage, deleteInfraHost };
}
