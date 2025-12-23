/**
 * Secrets Management API Client
 * 
 * Provides a clean interface for interacting with the secrets management API
 * with proper error handling and chat scope management.
 */

import { ApiClient } from './ApiClient.js';

class SecretsApiClient {
    constructor() {
        this.apiClient = new ApiClient();
        this.currentChatId = null;
    }

    /**
     * Set the current chat ID for chat-scoped operations
     */
    setCurrentChatId(chatId) {
        this.currentChatId = chatId;
    }

    /**
     * Get all secrets with optional filtering
     */
    async getSecrets(options = {}) {
        const params = new URLSearchParams();
        
        if (options.scope) {
            params.append('scope', options.scope);
        }
        
        if (options.chatId || this.currentChatId) {
            params.append('chat_id', options.chatId || this.currentChatId);
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.get(`/api/secrets/?${params.toString()}`);
        return response;
    }

    /**
     * Get a specific secret by ID
     */
    async getSecret(secretId, options = {}) {
        const params = new URLSearchParams();
        
        if (options.chatId || this.currentChatId) {
            params.append('chat_id', options.chatId || this.currentChatId);
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.get(`/api/secrets/${secretId}?${params.toString()}`);
        return response;
    }

    /**
     * Create a new secret
     */
    async createSecret(secretData) {
        // Auto-set chat_id for chat-scoped secrets
        if (secretData.scope === 'chat' && !secretData.chat_id) {
            secretData.chat_id = this.currentChatId;
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.post('/api/secrets/', secretData);
        return response;
    }

    /**
     * Update an existing secret
     */
    async updateSecret(secretId, updateData, options = {}) {
        const params = new URLSearchParams();
        
        if (options.chatId || this.currentChatId) {
            params.append('chat_id', options.chatId || this.currentChatId);
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.put(`/api/secrets/${secretId}?${params.toString()}`, updateData);
        return response;
    }

    /**
     * Delete a secret
     */
    async deleteSecret(secretId, options = {}) {
        const params = new URLSearchParams();
        
        if (options.chatId || this.currentChatId) {
            params.append('chat_id', options.chatId || this.currentChatId);
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.delete(`/api/secrets/${secretId}?${params.toString()}`);
        return response;
    }

    /**
     * Transfer secrets between scopes
     */
    async transferSecrets(transferData, options = {}) {
        const params = new URLSearchParams();
        
        if (options.chatId || this.currentChatId) {
            params.append('chat_id', options.chatId || this.currentChatId);
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.post(`/api/secrets/transfer?${params.toString()}`, transferData);
        return response;
    }

    /**
     * Get secrets cleanup information for a chat
     */
    async getChatCleanupInfo(chatId) {
        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.get(`/api/secrets/chat/${chatId}/cleanup`);
        return response;
    }

    /**
     * Delete secrets for a specific chat
     */
    async deleteChatSecrets(chatId, secretIds = null) {
        const params = new URLSearchParams();
        
        if (secretIds && Array.isArray(secretIds)) {
            secretIds.forEach(id => params.append('secret_ids', id));
        }

        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.delete(`/api/secrets/chat/${chatId}?${params.toString()}`);
        return response;
    }

    /**
     * Get available secret types and scopes
     */
    async getSecretTypes() {
        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.get('/api/secrets/types');
        return response;
    }

    /**
     * Get secrets statistics
     */
    async getSecretsStats() {
        // Issue #552: Fixed path - removed duplicate /secrets prefix
        const response = await this.apiClient.get('/api/secrets/stats');
        return response;
    }

    /**
     * Utility method to validate secret data before creation
     */
    validateSecretData(secretData) {
        const errors = [];

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
    formatSecretForDisplay(secret) {
        return {
            ...secret,
            type_label: secret.type ? secret.type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) : '',
            scope_label: secret.scope ? secret.scope.charAt(0).toUpperCase() + secret.scope.slice(1) : '',
            created_at_formatted: secret.created_at ? new Date(secret.created_at).toLocaleString() : '',
            expires_at_formatted: secret.expires_at ? new Date(secret.expires_at).toLocaleString() : null,
            updated_at_formatted: secret.updated_at ? new Date(secret.updated_at).toLocaleString() : '',
            is_expired: secret.expires_at ? new Date(secret.expires_at) < new Date() : false,
            chat_id_short: secret.chat_id ? secret.chat_id.substring(0, 8) + '...' : null
        };
    }

    /**
     * Utility method to group secrets by scope
     */
    groupSecretsByScope(secrets) {
        return secrets.reduce((groups, secret) => {
            const scope = secret.scope || 'unknown';
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
    groupSecretsByType(secrets) {
        return secrets.reduce((groups, secret) => {
            const type = secret.type || 'unknown';
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
    filterSecrets(secrets, searchQuery) {
        if (!searchQuery || searchQuery.trim().length === 0) {
            return secrets;
        }

        const query = searchQuery.toLowerCase().trim();
        
        return secrets.filter(secret => {
            // Search in name
            if (secret.name && secret.name.toLowerCase().includes(query)) {
                return true;
            }
            
            // Search in description
            if (secret.description && secret.description.toLowerCase().includes(query)) {
                return true;
            }
            
            // Search in tags
            if (secret.tags && Array.isArray(secret.tags)) {
                return secret.tags.some(tag => tag.toLowerCase().includes(query));
            }
            
            // Search in type
            if (secret.type && secret.type.toLowerCase().includes(query)) {
                return true;
            }
            
            return false;
        });
    }

    /**
     * Utility method to sort secrets
     */
    sortSecrets(secrets, sortBy = 'created_at', sortOrder = 'desc') {
        return [...secrets].sort((a, b) => {
            let aVal = a[sortBy];
            let bVal = b[sortBy];
            
            // Handle dates
            if (sortBy.includes('_at')) {
                aVal = new Date(aVal);
                bVal = new Date(bVal);
            }
            
            // Handle strings
            if (typeof aVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }
            
            if (sortOrder === 'desc') {
                return bVal > aVal ? 1 : -1;
            } else {
                return aVal > bVal ? 1 : -1;
            }
        });
    }

    /**
     * Utility method to get expired secrets
     */
    getExpiredSecrets(secrets) {
        const now = new Date();
        return secrets.filter(secret => {
            return secret.expires_at && new Date(secret.expires_at) < now;
        });
    }

    /**
     * Utility method to get secrets expiring soon (within specified days)
     */
    getSecretsExpiringSoon(secrets, days = 7) {
        const now = new Date();
        const futureDate = new Date(now.getTime() + (days * 24 * 60 * 60 * 1000));
        
        return secrets.filter(secret => {
            if (!secret.expires_at) return false;
            const expiryDate = new Date(secret.expires_at);
            return expiryDate > now && expiryDate <= futureDate;
        });
    }
}

// Export singleton instance
export const secretsApiClient = new SecretsApiClient();
export default SecretsApiClient;