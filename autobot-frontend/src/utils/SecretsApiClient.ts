// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Secrets Management API Client
 *
 * Provides a clean interface for interacting with the secrets management API
 * with proper error handling and chat scope management.
 *
 * Transport: routed through the canonical apiClient singleton (#12152) — the
 * get/post/put/delete convenience methods already centralise base-URL
 * resolution, auth-token injection and org-context headers. Converted from
 * the previous .js + hand-written .d.ts pair to a single typed module
 * (#12363 Phase 1); behaviour and public surface are unchanged.
 */

import apiClient from './ApiClient';
import { getApiBase } from '@/config/ssot-config';

export interface SecretData {
  name: string;
  type: string;
  scope: 'global' | 'chat' | string;
  value: string;
  chat_id?: string | null;
  description?: string;
  tags?: string[];
  expires_at?: string | null;
}

export type SecretUpdateData = Partial<SecretData>;

export interface TransferData {
  secret_ids: string[];
  target_scope: string;
  target_chat_id?: string | null;
}

export interface GetSecretsOptions {
  scope?: string;
  chatId?: string | null;
}

export interface GetSecretOptions {
  chatId?: string | null;
}

export interface UpdateSecretOptions {
  chatId?: string | null;
}

export interface DeleteSecretOptions {
  chatId?: string | null;
}

export interface TransferSecretsOptions {
  chatId?: string | null;
}

export interface ValidationResult {
  isValid: boolean;
  errors: string[];
}

export interface FormattedSecret {
  type_label: string;
  scope_label: string;
  created_at_formatted: string;
  expires_at_formatted: string | null;
  updated_at_formatted: string;
  is_expired: boolean;
  chat_id_short: string | null;
  [key: string]: unknown;
}

class SecretsApiClient {
  private apiClient: typeof apiClient;
  currentChatId: string | null;

  constructor() {
    this.apiClient = apiClient;
    this.currentChatId = null;
  }

  /**
   * Set the current chat ID for chat-scoped operations
   */
  setCurrentChatId(chatId: string | null): void {
    this.currentChatId = chatId;
  }

  /**
   * Get all secrets with optional filtering
   */
  async getSecrets(options: GetSecretsOptions = {}): Promise<unknown> {
    const params = new URLSearchParams();

    if (options.scope) {
      params.append('scope', options.scope);
    }

    if (options.chatId || this.currentChatId) {
      params.append('chat_id', (options.chatId || this.currentChatId) as string);
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.get(`${getApiBase()}/secrets/?${params.toString()}`);
    return response;
  }

  /**
   * Get a specific secret by ID
   */
  async getSecret(secretId: string, options: GetSecretOptions = {}): Promise<unknown> {
    const params = new URLSearchParams();

    if (options.chatId || this.currentChatId) {
      params.append('chat_id', (options.chatId || this.currentChatId) as string);
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.get(`${getApiBase()}/secrets/${secretId}?${params.toString()}`);
    return response;
  }

  /**
   * Create a new secret
   */
  async createSecret(secretData: SecretData): Promise<unknown> {
    // Auto-set chat_id for chat-scoped secrets
    if (secretData.scope === 'chat' && !secretData.chat_id) {
      secretData.chat_id = this.currentChatId;
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.post(`${getApiBase()}/secrets/`, secretData);
    return response;
  }

  /**
   * Update an existing secret
   */
  async updateSecret(
    secretId: string,
    updateData: SecretUpdateData,
    options: UpdateSecretOptions = {}
  ): Promise<unknown> {
    const params = new URLSearchParams();

    if (options.chatId || this.currentChatId) {
      params.append('chat_id', (options.chatId || this.currentChatId) as string);
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.put(`${getApiBase()}/secrets/${secretId}?${params.toString()}`, updateData);
    return response;
  }

  /**
   * Delete a secret
   */
  async deleteSecret(secretId: string, options: DeleteSecretOptions = {}): Promise<unknown> {
    const params = new URLSearchParams();

    if (options.chatId || this.currentChatId) {
      params.append('chat_id', (options.chatId || this.currentChatId) as string);
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.delete(`${getApiBase()}/secrets/${secretId}?${params.toString()}`);
    return response;
  }

  /**
   * Transfer secrets between scopes
   */
  async transferSecrets(transferData: TransferData, options: TransferSecretsOptions = {}): Promise<unknown> {
    const params = new URLSearchParams();

    if (options.chatId || this.currentChatId) {
      params.append('chat_id', (options.chatId || this.currentChatId) as string);
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.post(`${getApiBase()}/secrets/transfer?${params.toString()}`, transferData);
    return response;
  }

  /**
   * Get secrets cleanup information for a chat
   */
  async getChatCleanupInfo(chatId: string): Promise<unknown> {
    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.get(`${getApiBase()}/secrets/chat/${chatId}/cleanup`);
    return response;
  }

  /**
   * Delete secrets for a specific chat
   */
  async deleteChatSecrets(chatId: string, secretIds: string[] | null = null): Promise<unknown> {
    const params = new URLSearchParams();

    if (secretIds && Array.isArray(secretIds)) {
      secretIds.forEach(id => params.append('secret_ids', id));
    }

    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.delete(`${getApiBase()}/secrets/chat/${chatId}?${params.toString()}`);
    return response;
  }

  /**
   * Get available secret types and scopes
   */
  async getSecretTypes(): Promise<unknown> {
    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.get(`${getApiBase()}/secrets/types`);
    return response;
  }

  /**
   * Get secrets statistics
   */
  async getSecretsStats(): Promise<unknown> {
    // Issue #552: Fixed path - removed duplicate /secrets prefix
    const response = await this.apiClient.get(`${getApiBase()}/secrets/stats`);
    return response;
  }

  /**
   * Utility method to validate secret data before creation
   */
  validateSecretData(secretData: Partial<SecretData>): ValidationResult {
    const errors: string[] = [];

    if (!secretData.name || secretData.name.trim().length === 0) {
      errors.push('Secret name is required');
    }

    if (!secretData.type) {
      errors.push('Secret type is required');
    }

    if (!secretData.scope) {
      errors.push('Secret scope is required');
    }

    if (secretData.scope === 'chat' && !secretData.chat_id && !this.currentChatId) {
      errors.push('Chat ID is required for chat-scoped secrets');
    }

    if (!secretData.value || secretData.value.trim().length === 0) {
      errors.push('Secret value is required');
    }

    if (secretData.expires_at) {
      const expiryDate = new Date(secretData.expires_at);
      if (expiryDate <= new Date()) {
        errors.push('Expiry date must be in the future');
      }
    }

    return {
      isValid: errors.length === 0,
      errors
    };
  }

  /**
   * Utility method to format secret data for display
   */
  formatSecretForDisplay(secret: Record<string, unknown>): FormattedSecret {
    const type = secret.type as string | undefined;
    const scope = secret.scope as string | undefined;
    const createdAt = secret.created_at as string | undefined;
    const expiresAt = secret.expires_at as string | undefined;
    const updatedAt = secret.updated_at as string | undefined;
    const chatId = secret.chat_id as string | undefined;

    return {
      ...secret,
      type_label: type ? type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) : '',
      scope_label: scope ? scope.charAt(0).toUpperCase() + scope.slice(1) : '',
      created_at_formatted: createdAt ? new Date(createdAt).toLocaleString() : '',
      expires_at_formatted: expiresAt ? new Date(expiresAt).toLocaleString() : null,
      updated_at_formatted: updatedAt ? new Date(updatedAt).toLocaleString() : '',
      is_expired: expiresAt ? new Date(expiresAt) < new Date() : false,
      chat_id_short: chatId ? chatId.substring(0, 8) + '...' : null
    };
  }

  /**
   * Utility method to group secrets by scope
   */
  groupSecretsByScope(
    secrets: Record<string, unknown>[]
  ): Record<string, Record<string, unknown>[]> {
    return secrets.reduce((groups: Record<string, Record<string, unknown>[]>, secret) => {
      const scope = (secret.scope as string) || 'unknown';
      if (!groups[scope]) {
        groups[scope] = [];
      }
      groups[scope].push(secret);
      return groups;
    }, {});
  }

  /**
   * Utility method to group secrets by type
   */
  groupSecretsByType(
    secrets: Record<string, unknown>[]
  ): Record<string, Record<string, unknown>[]> {
    return secrets.reduce((groups: Record<string, Record<string, unknown>[]>, secret) => {
      const type = (secret.type as string) || 'unknown';
      if (!groups[type]) {
        groups[type] = [];
      }
      groups[type].push(secret);
      return groups;
    }, {});
  }

  /**
   * Utility method to filter secrets by search query
   */
  filterSecrets(
    secrets: Record<string, unknown>[],
    searchQuery: string
  ): Record<string, unknown>[] {
    if (!searchQuery || searchQuery.trim().length === 0) {
      return secrets;
    }

    const query = searchQuery.toLowerCase().trim();

    return secrets.filter(secret => {
      // Search in name
      const name = secret.name as string | undefined;
      if (name && name.toLowerCase().includes(query)) {
        return true;
      }

      // Search in description
      const description = secret.description as string | undefined;
      if (description && description.toLowerCase().includes(query)) {
        return true;
      }

      // Search in tags
      const tags = secret.tags as string[] | undefined;
      if (tags && Array.isArray(tags)) {
        return tags.some(tag => tag.toLowerCase().includes(query));
      }

      // Search in type
      const type = secret.type as string | undefined;
      if (type && type.toLowerCase().includes(query)) {
        return true;
      }

      return false;
    });
  }

  /**
   * Utility method to sort secrets
   */
  sortSecrets(
    secrets: Record<string, unknown>[],
    sortBy: string = 'created_at',
    sortOrder: 'asc' | 'desc' = 'desc'
  ): Record<string, unknown>[] {
    return [...secrets].sort((a, b) => {
      let aVal: unknown = a[sortBy];
      let bVal: unknown = b[sortBy];

      // Handle dates
      if (sortBy.includes('_at')) {
        aVal = new Date(aVal as string);
        bVal = new Date(bVal as string);
      }

      // Handle strings
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }

      if (sortOrder === 'desc') {
        return (bVal as number | string) > (aVal as number | string) ? 1 : -1;
      } else {
        return (aVal as number | string) > (bVal as number | string) ? 1 : -1;
      }
    });
  }

  /**
   * Utility method to get expired secrets
   */
  getExpiredSecrets(secrets: Record<string, unknown>[]): Record<string, unknown>[] {
    const now = new Date();
    return secrets.filter(secret => {
      const expiresAt = secret.expires_at as string | undefined;
      return expiresAt && new Date(expiresAt) < now;
    });
  }

  /**
   * Utility method to get secrets expiring soon (within specified days)
   */
  getSecretsExpiringSoon(
    secrets: Record<string, unknown>[],
    days: number = 7
  ): Record<string, unknown>[] {
    const now = new Date();
    const futureDate = new Date(now.getTime() + (days * 24 * 60 * 60 * 1000));

    return secrets.filter(secret => {
      const expiresAt = secret.expires_at as string | undefined;
      if (!expiresAt) return false;
      const expiryDate = new Date(expiresAt);
      return expiryDate > now && expiryDate <= futureDate;
    });
  }
}

// Export singleton instance
export const secretsApiClient = new SecretsApiClient();
export default SecretsApiClient;
