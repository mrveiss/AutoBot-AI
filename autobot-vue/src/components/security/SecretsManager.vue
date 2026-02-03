<template>
  <div class="secrets-manager-n8n">
    <!-- Sidebar Navigation -->
    <aside class="secrets-sidebar">
      <div class="sidebar-header">
        <h3><i class="fas fa-key"></i> Credentials</h3>
      </div>

      <!-- Search -->
      <div class="sidebar-search">
        <div class="search-wrapper">
          <i class="fas fa-search"></i>
          <input
            type="text"
            v-model="searchQuery"
            placeholder="Search credentials..."
            class="search-input"
          />
          <button v-if="searchQuery" @click="searchQuery = ''" class="clear-search">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav">
        <div
          class="category-item"
          :class="{ active: selectedCategory === 'all' }"
          @click="selectCategory('all')"
        >
          <i class="fas fa-layer-group"></i>
          <span>All Credentials</span>
          <span class="count">{{ secrets.length }}</span>
        </div>

        <div class="category-divider">
          <span>By Type</span>
        </div>

        <div
          v-for="category in credentialCategories"
          :key="category.type"
          class="category-item"
          :class="{ active: selectedCategory === category.type }"
          @click="selectCategory(category.type)"
        >
          <i :class="category.icon"></i>
          <span>{{ category.label }}</span>
          <span class="count">{{ getCategoryCount(category.type) }}</span>
        </div>

        <div class="category-divider">
          <span>By Scope</span>
        </div>

        <div
          class="category-item"
          :class="{ active: selectedScope === 'general' }"
          @click="selectScope('general')"
        >
          <i class="fas fa-globe"></i>
          <span>General</span>
          <span class="count">{{ stats?.by_scope?.general || 0 }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: selectedScope === 'chat' }"
          @click="selectScope('chat')"
        >
          <i class="fas fa-comments"></i>
          <span>Chat-scoped</span>
          <span class="count">{{ stats?.by_scope?.chat || 0 }}</span>
        </div>

        <div class="category-divider" v-if="stats?.expired_count > 0">
          <span>Alerts</span>
        </div>

        <div
          v-if="stats?.expired_count > 0"
          class="category-item alert"
          :class="{ active: showExpiredOnly }"
          @click="toggleExpiredFilter"
        >
          <i class="fas fa-exclamation-triangle"></i>
          <span>Expired</span>
          <span class="count alert">{{ stats.expired_count }}</span>
        </div>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="openCreateModal" class="btn-create">
          <i class="fas fa-plus"></i> New Credential
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="secrets-content">
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ currentCategoryLabel }}</h2>
          <span class="subtitle">{{ filteredSecrets.length }} credential{{ filteredSecrets.length !== 1 ? 's' : '' }}</span>
        </div>
        <div class="header-actions">
          <button @click="loadSecrets" class="btn-icon" :disabled="loading" title="Refresh">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          </button>
          <button @click="toggleView" class="btn-icon" :title="viewMode === 'grid' ? 'List view' : 'Grid view'">
            <i :class="viewMode === 'grid' ? 'fas fa-list' : 'fas fa-th'"></i>
          </button>
        </div>
      </header>

      <!-- Stats Bar -->
      <div class="stats-bar" v-if="stats">
        <div class="stat-item">
          <i class="fas fa-key"></i>
          <span class="stat-value">{{ stats.total_secrets }}</span>
          <span class="stat-label">Total</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-globe"></i>
          <span class="stat-value">{{ stats.by_scope?.general || 0 }}</span>
          <span class="stat-label">General</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-comments"></i>
          <span class="stat-value">{{ stats.by_scope?.chat || 0 }}</span>
          <span class="stat-label">Chat</span>
        </div>
        <div class="stat-item warning" v-if="stats.expired_count > 0">
          <i class="fas fa-clock"></i>
          <span class="stat-value">{{ stats.expired_count }}</span>
          <span class="stat-label">Expired</span>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>Loading credentials...</p>
      </div>

      <!-- Empty State -->
      <EmptyState
        v-else-if="filteredSecrets.length === 0"
        :icon="emptyStateIcon"
        :message="emptyStateMessage"
      >
        <template #actions>
          <button @click="openCreateModal()" class="btn-primary">
            <i class="fas fa-plus"></i> Create Credential
          </button>
          <button v-if="hasActiveFilters" @click="clearFilters" class="btn-secondary">
            Clear Filters
          </button>
        </template>
      </EmptyState>

      <!-- Credentials Grid/List -->
      <div v-else :class="['credentials-container', viewMode]">
        <div
          v-for="secret in filteredSecrets"
          :key="secret.id"
          class="credential-card"
          :class="{ expired: isExpired(secret), selected: selectedSecretId === secret.id }"
          @click="selectSecret(secret)"
        >
          <!-- Card Icon -->
          <div class="card-icon" :style="{ backgroundColor: getTypeColor(secret.type) }">
            <i :class="getTypeIcon(secret.type)"></i>
          </div>

          <!-- Card Content -->
          <div class="card-content">
            <div class="card-header">
              <h4>{{ secret.name }}</h4>
              <div class="card-badges">
                <span class="badge" :class="secret.scope">{{ secret.scope }}</span>
                <span v-if="isExpired(secret)" class="badge expired">
                  <i class="fas fa-exclamation-triangle"></i> Expired
                </span>
              </div>
            </div>

            <p class="card-description" v-if="secret.description">
              {{ truncate(secret.description, 80) }}
            </p>

            <div class="card-meta">
              <span class="meta-item">
                <i class="fas fa-clock"></i>
                {{ formatRelativeTime(secret.created_at) }}
              </span>
              <span v-if="secret.expires_at" class="meta-item" :class="{ 'text-warning': isExpiringSoon(secret) }">
                <i class="fas fa-hourglass-half"></i>
                Expires {{ formatRelativeTime(secret.expires_at) }}
              </span>
            </div>

            <div class="card-tags" v-if="secret.tags?.length">
              <span v-for="tag in secret.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
              <span v-if="secret.tags.length > 3" class="tag more">+{{ secret.tags.length - 3 }}</span>
            </div>
          </div>

          <!-- Card Actions -->
          <div class="card-actions">
            <button @click.stop="viewSecret(secret)" class="action-btn" title="View">
              <i class="fas fa-eye"></i>
            </button>
            <button @click.stop="editSecret(secret)" class="action-btn" title="Edit">
              <i class="fas fa-edit"></i>
            </button>
            <button
              v-if="secret.scope === 'chat'"
              @click.stop="transferSecret(secret)"
              class="action-btn"
              title="Make General"
            >
              <i class="fas fa-share"></i>
            </button>
            <button @click.stop="confirmDelete(secret)" class="action-btn delete" title="Delete">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
      </div>

      <!-- Templates Section -->
      <div v-if="showTemplates && filteredSecrets.length === 0" class="templates-section">
        <h3><i class="fas fa-magic"></i> Quick Add Templates</h3>
        <p class="templates-subtitle">Choose a template to quickly add common credentials</p>
        <div class="templates-grid">
          <div
            v-for="template in credentialTemplates"
            :key="template.id"
            class="template-card"
            @click="useTemplate(template)"
          >
            <div class="template-icon" :style="{ backgroundColor: template.color }">
              <i :class="template.icon"></i>
            </div>
            <div class="template-info">
              <h4>{{ template.name }}</h4>
              <p>{{ template.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Create/Edit Modal -->
    <BaseModal
      :modelValue="showCreateModal || showEditModal"
      @update:modelValue="val => !val && closeModals()"
      :title="modalTitle"
      size="large"
      :closeOnOverlay="!saving"
    >
      <form @submit.prevent="saveSecret" class="credential-form">
        <!-- Template Selection (only for new) -->
        <div v-if="!showEditModal && !secretForm.type" class="template-selection">
          <h4>Choose Credential Type</h4>
          <div class="type-grid">
            <div
              v-for="category in credentialCategories"
              :key="category.type"
              class="type-option"
              @click="selectType(category.type)"
            >
              <div class="type-icon" :style="{ backgroundColor: category.color }">
                <i :class="category.icon"></i>
              </div>
              <span>{{ category.label }}</span>
            </div>
          </div>
        </div>

        <!-- Form Fields -->
        <div v-else class="form-fields">
          <!-- Selected Type Display -->
          <div class="selected-type">
            <div class="type-icon" :style="{ backgroundColor: getTypeColor(secretForm.type) }">
              <i :class="getTypeIcon(secretForm.type)"></i>
            </div>
            <div class="type-info">
              <span class="type-label">{{ getTypeLabel(secretForm.type) }}</span>
              <button v-if="!showEditModal" type="button" @click="secretForm.type = ''" class="change-type">
                Change type
              </button>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Name <span class="required">*</span></label>
              <input
                type="text"
                v-model="secretForm.name"
                required
                placeholder="e.g., Production API Key"
                class="form-input"
              />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Scope <span class="required">*</span></label>
              <div class="scope-selector">
                <label class="scope-option" :class="{ active: secretForm.scope === 'general' }">
                  <input type="radio" v-model="secretForm.scope" value="general" />
                  <i class="fas fa-globe"></i>
                  <div>
                    <span>General</span>
                    <small>Available across all conversations</small>
                  </div>
                </label>
                <label class="scope-option" :class="{ active: secretForm.scope === 'chat' }">
                  <input type="radio" v-model="secretForm.scope" value="chat" />
                  <i class="fas fa-comments"></i>
                  <div>
                    <span>Chat-scoped</span>
                    <small>Only in current conversation</small>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <!-- Infrastructure Host Form Fields -->
          <template v-if="secretForm.type === 'infrastructure_host'">
            <!-- Host & Port Row -->
            <div class="form-row two-col">
              <div class="form-group">
                <label>Host/IP <span class="required">*</span></label>
                <input
                  type="text"
                  v-model="secretForm.host"
                  required
                  placeholder="192.168.1.100 or hostname.example.com"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>SSH Port</label>
                <input
                  type="number"
                  v-model.number="secretForm.ssh_port"
                  placeholder="22"
                  class="form-input"
                  min="1"
                  max="65535"
                />
              </div>
            </div>

            <!-- Username & Auth Type -->
            <div class="form-row two-col">
              <div class="form-group">
                <label>Username <span class="required">*</span></label>
                <input
                  type="text"
                  v-model="secretForm.username"
                  required
                  placeholder="root"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>Authentication <span class="required">*</span></label>
                <select v-model="secretForm.auth_type" class="form-input">
                  <option value="ssh_key">SSH Key</option>
                  <option value="password">Password</option>
                </select>
              </div>
            </div>

            <!-- SSH Key (if auth_type is ssh_key) -->
            <div class="form-row" v-if="secretForm.auth_type === 'ssh_key' && !showEditModal">
              <div class="form-group">
                <label>SSH Private Key <span class="required">*</span></label>
                <div class="secret-input-wrapper">
                  <textarea
                    v-model="secretForm.ssh_key"
                    required
                    placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
                    class="form-input secret-input"
                    :class="{ 'secret-masked': !showValue }"
                    rows="6"
                  ></textarea>
                  <button
                    type="button"
                    @click="toggleValueVisibility"
                    class="toggle-visibility"
                    :title="showValue ? 'Hide key' : 'Show key'"
                  >
                    <i :class="showValue ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                  </button>
                </div>
                <small class="input-hint">Paste your entire private key including BEGIN/END markers</small>
              </div>
            </div>

            <!-- SSH Password (if auth_type is password) -->
            <div class="form-row" v-if="secretForm.auth_type === 'password' && !showEditModal">
              <div class="form-group">
                <label>SSH Password <span class="required">*</span></label>
                <div class="secret-input-wrapper">
                  <input
                    type="password"
                    v-model="secretForm.ssh_password"
                    required
                    placeholder="Enter SSH password"
                    class="form-input secret-input"
                    autocomplete="new-password"
                  />
                  <button
                    type="button"
                    @click="toggleValueVisibility"
                    class="toggle-visibility"
                    :title="showValue ? 'Hide password' : 'Show password'"
                  >
                    <i :class="showValue ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                  </button>
                </div>
              </div>
            </div>

            <!-- Capabilities -->
            <div class="form-row">
              <div class="form-group">
                <label>Capabilities</label>
                <div class="capability-checkboxes">
                  <label class="checkbox-option">
                    <input type="checkbox" value="ssh" v-model="secretForm.capabilities" disabled checked />
                    <i class="fas fa-terminal"></i>
                    <span>SSH (Always enabled)</span>
                  </label>
                  <label class="checkbox-option">
                    <input type="checkbox" value="vnc" v-model="secretForm.capabilities" />
                    <i class="fas fa-desktop"></i>
                    <span>VNC Desktop</span>
                  </label>
                </div>
              </div>
            </div>

            <!-- VNC Settings (if VNC enabled) -->
            <div class="form-row two-col" v-if="secretForm.capabilities.includes('vnc')">
              <div class="form-group">
                <label>VNC Port <span class="required">*</span></label>
                <input
                  type="number"
                  v-model.number="secretForm.vnc_port"
                  required
                  placeholder="5901"
                  class="form-input"
                  min="1"
                  max="65535"
                />
              </div>
              <div class="form-group" v-if="!showEditModal">
                <label>VNC Password</label>
                <input
                  type="password"
                  v-model="secretForm.vnc_password"
                  placeholder="VNC password (optional)"
                  class="form-input"
                  autocomplete="new-password"
                />
              </div>
            </div>

            <!-- OS & Purpose (metadata for knowledge base) -->
            <div class="form-row two-col">
              <div class="form-group">
                <label>Operating System</label>
                <input
                  type="text"
                  v-model="secretForm.os"
                  placeholder="e.g., Ubuntu 22.04, CentOS 8"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>Purpose/Role</label>
                <input
                  type="text"
                  v-model="secretForm.purpose"
                  placeholder="e.g., Web server, Database host"
                  class="form-input"
                />
              </div>
            </div>
          </template>

          <!-- Standard Secret Value Field (non-infrastructure_host) -->
          <div class="form-row" v-else-if="!showEditModal">
            <div class="form-group">
              <label>{{ getValueLabel(secretForm.type) }} <span class="required">*</span></label>
              <div class="secret-input-wrapper">
                <!-- Multi-line secrets (SSH keys, certificates) use textarea with CSS masking -->
                <textarea
                  v-if="isMultilineSecret(secretForm.type)"
                  v-model="secretForm.value"
                  required
                  :placeholder="getValuePlaceholder(secretForm.type)"
                  class="form-input secret-input"
                  :class="{ 'secret-masked': !showValue }"
                  :rows="getValueRows(secretForm.type)"
                ></textarea>
                <!-- Single-line secrets use password input for proper masking -->
                <input
                  v-else
                  v-model="secretForm.value"
                  :type="showValue ? 'text' : 'password'"
                  required
                  :placeholder="getValuePlaceholder(secretForm.type)"
                  class="form-input secret-input"
                  autocomplete="off"
                />
                <button
                  type="button"
                  @click="toggleValueVisibility"
                  class="toggle-visibility"
                  :title="showValue ? 'Hide value' : 'Show value'"
                >
                  <i :class="showValue ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                </button>
              </div>
              <small class="input-hint">{{ getValueHint(secretForm.type) }}</small>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Description</label>
              <textarea
                v-model="secretForm.description"
                placeholder="Optional notes about this credential"
                class="form-input"
                rows="2"
              ></textarea>
            </div>
          </div>

          <div class="form-row two-col">
            <div class="form-group">
              <label>Tags</label>
              <input
                type="text"
                v-model="tagsInput"
                placeholder="production, api, aws"
                class="form-input"
                @input="updateTags"
              />
              <small class="input-hint">Separate with commas</small>
            </div>
            <div class="form-group">
              <label>Expiration</label>
              <input
                type="datetime-local"
                v-model="secretForm.expires_at"
                class="form-input"
              />
              <small class="input-hint">Optional auto-expiry date</small>
            </div>
          </div>
        </div>
      </form>

      <template #actions>
        <button type="button" @click="closeModals" class="btn-secondary">Cancel</button>
        <button
          type="submit"
          @click="saveSecret"
          class="btn-primary"
          :disabled="saving || !isFormValid"
        >
          <i v-if="saving" class="fas fa-spinner fa-spin"></i>
          {{ saving ? 'Saving...' : (showEditModal ? 'Update Credential' : 'Create Credential') }}
        </button>
      </template>
    </BaseModal>

    <!-- View Secret Modal -->
    <BaseModal
      v-model="showViewModal"
      :title="viewingSecret?.name || 'View Credential'"
      size="medium"
    >
      <div class="view-credential">
        <div class="view-header">
          <div class="view-icon" :style="{ backgroundColor: getTypeColor(viewingSecret?.type) }">
            <i :class="getTypeIcon(viewingSecret?.type)"></i>
          </div>
          <div class="view-title">
            <h3>{{ viewingSecret?.name }}</h3>
            <span class="view-type">{{ getTypeLabel(viewingSecret?.type) }}</span>
          </div>
        </div>

        <div class="view-section">
          <label>Value</label>
          <div class="secret-display">
            <code v-if="showSecretValue">{{ viewingSecret?.value || 'Loading...' }}</code>
            <code v-else>{{ '•'.repeat(Math.min(viewingSecret?.value?.length || 20, 40)) }}</code>
            <div class="secret-actions">
              <button @click="toggleSecretValue" class="action-btn">
                <i :class="showSecretValue ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
              </button>
              <button @click="copySecretValue" class="action-btn">
                <i class="fas fa-copy"></i>
              </button>
            </div>
          </div>
        </div>

        <div class="view-grid">
          <div class="view-item">
            <label>Scope</label>
            <span class="badge" :class="viewingSecret?.scope">
              <i :class="viewingSecret?.scope === 'general' ? 'fas fa-globe' : 'fas fa-comments'"></i>
              {{ viewingSecret?.scope }}
            </span>
          </div>
          <div class="view-item">
            <label>Created</label>
            <span>{{ formatDate(viewingSecret?.created_at) }}</span>
          </div>
          <div class="view-item" v-if="viewingSecret?.expires_at">
            <label>Expires</label>
            <span :class="{ 'text-danger': isExpired(viewingSecret), 'text-warning': isExpiringSoon(viewingSecret) }">
              {{ formatDate(viewingSecret?.expires_at) }}
            </span>
          </div>
          <div class="view-item" v-if="viewingSecret?.updated_at">
            <label>Last Updated</label>
            <span>{{ formatDate(viewingSecret?.updated_at) }}</span>
          </div>
        </div>

        <div class="view-section" v-if="viewingSecret?.description">
          <label>Description</label>
          <p>{{ viewingSecret.description }}</p>
        </div>

        <div class="view-section" v-if="viewingSecret?.tags?.length">
          <label>Tags</label>
          <div class="tags-list">
            <span v-for="tag in viewingSecret.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>
      </div>

      <template #actions>
        <button @click="closeViewModal" class="btn-secondary">Close</button>
        <button @click="editSecret(viewingSecret)" class="btn-primary">
          <i class="fas fa-edit"></i> Edit
        </button>
      </template>
    </BaseModal>

    <!-- Transfer Modal -->
    <BaseModal
      v-model="showTransferModal"
      title="Transfer Credential"
      size="small"
    >
      <div class="transfer-content">
        <div class="transfer-icon">
          <i class="fas fa-share-square"></i>
        </div>
        <h4>Make "{{ transferringSecret?.name }}" available everywhere?</h4>
        <p>This will change the credential from chat-scoped to general, making it accessible across all conversations.</p>
        <div class="transfer-warning">
          <i class="fas fa-info-circle"></i>
          <span>This action cannot be undone.</span>
        </div>
      </div>

      <template #actions>
        <button @click="closeTransferModal" class="btn-secondary">Cancel</button>
        <button @click="confirmTransfer" class="btn-primary" :disabled="transferring">
          <i v-if="transferring" class="fas fa-spinner fa-spin"></i>
          {{ transferring ? 'Transferring...' : 'Transfer to General' }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete Confirmation Modal -->
    <BaseModal
      v-model="showDeleteModal"
      title="Delete Credential"
      size="small"
    >
      <div class="delete-content">
        <div class="delete-icon">
          <i class="fas fa-trash-alt"></i>
        </div>
        <h4>Delete "{{ deletingSecret?.name }}"?</h4>
        <p>This will permanently delete this credential. Any services using it will lose access.</p>
        <div class="delete-warning">
          <i class="fas fa-exclamation-triangle"></i>
          <span>This action cannot be undone.</span>
        </div>
      </div>

      <template #actions>
        <button @click="showDeleteModal = false" class="btn-secondary">Cancel</button>
        <button @click="deleteSecret" class="btn-danger" :disabled="deleting">
          <i v-if="deleting" class="fas fa-spinner fa-spin"></i>
          {{ deleting ? 'Deleting...' : 'Delete Credential' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue';
// @ts-ignore - JavaScript API client without type declarations
import { secretsApiClient } from '@/utils/SecretsApiClient';
import { useAppStore } from '@/stores/useAppStore';
import { createLogger } from '@/utils/debugUtils';
import { formatDateTime } from '@/utils/formatHelpers';
import { useDebounce } from '@/composables/useDebounce';
import { getBackendUrl } from '@/config/ssot-config';
import EmptyState from '@/components/ui/EmptyState.vue';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseModal from '@/components/ui/BaseModal.vue';

const logger = createLogger('SecretsManager');

/**
 * Helper to get CSS custom property value at runtime.
 * Used for dynamic styles that need design token colors (e.g., inline styles).
 * @param name - CSS custom property name (e.g., '--color-primary')
 * @param fallback - Fallback value for SSR/testing
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

// Credential type categories with icons and colors (using design tokens)
const credentialCategories = computed(() => [
  { type: 'api_key', label: 'API Keys', icon: 'fas fa-key', color: getCssVar('--color-primary', '#6366f1') },
  { type: 'token', label: 'Tokens', icon: 'fas fa-ticket-alt', color: getCssVar('--chart-purple', '#8b5cf6') },
  { type: 'password', label: 'Passwords', icon: 'fas fa-lock', color: getCssVar('--chart-pink', '#ec4899') },
  { type: 'ssh_key', label: 'SSH Keys', icon: 'fas fa-terminal', color: getCssVar('--chart-teal', '#14b8a6') },
  { type: 'infrastructure_host', label: 'Infrastructure Hosts', icon: 'fas fa-server', color: getCssVar('--chart-blue', '#3b82f6') },
  { type: 'database_url', label: 'Database', icon: 'fas fa-database', color: getCssVar('--color-warning', '#f59e0b') },
  { type: 'certificate', label: 'Certificates', icon: 'fas fa-certificate', color: getCssVar('--color-success', '#10b981') },
  { type: 'other', label: 'Other', icon: 'fas fa-ellipsis-h', color: getCssVar('--text-tertiary', '#6b7280') },
]);

// Quick-add templates for common services (using design tokens)
const credentialTemplates = computed(() => [
  { id: 'openai', name: 'OpenAI', description: 'GPT API access', icon: 'fas fa-brain', color: getCssVar('--color-success', '#10a37f'), type: 'api_key' },
  { id: 'anthropic', name: 'Anthropic', description: 'Claude API access', icon: 'fas fa-robot', color: getCssVar('--color-warning-hover', '#d97706'), type: 'api_key' },
  { id: 'aws', name: 'AWS', description: 'Amazon Web Services', icon: 'fab fa-aws', color: getCssVar('--chart-orange', '#ff9900'), type: 'api_key' },
  { id: 'github', name: 'GitHub', description: 'GitHub personal token', icon: 'fab fa-github', color: getCssVar('--bg-tertiary', '#333'), type: 'token' },
  { id: 'postgres', name: 'PostgreSQL', description: 'Database connection', icon: 'fas fa-database', color: getCssVar('--color-info', '#336791'), type: 'database_url' },
  { id: 'redis', name: 'Redis', description: 'Redis connection', icon: 'fas fa-layer-group', color: getCssVar('--chart-red', '#dc382d'), type: 'database_url' },
  { id: 'ssh', name: 'SSH Key', description: 'Server access', icon: 'fas fa-terminal', color: getCssVar('--bg-primary', '#000'), type: 'ssh_key' },
  { id: 'slack', name: 'Slack', description: 'Slack bot token', icon: 'fab fa-slack', color: getCssVar('--chart-purple', '#4a154b'), type: 'token' },
  { id: 'server', name: 'Server Host', description: 'SSH/VNC server access', icon: 'fas fa-server', color: getCssVar('--chart-blue', '#3b82f6'), type: 'infrastructure_host' },
]);

// State
const secrets = ref<any[]>([]);
const stats = ref<any>(null);
const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const transferring = ref(false);

// View state
const viewMode = ref<'grid' | 'list'>('grid');
const selectedCategory = ref('all');
const selectedScope = ref('');
const searchQuery = ref('');
const showExpiredOnly = ref(false);
const selectedSecretId = ref<string | null>(null);
const showTemplates = ref(true);

// Modal state
const showCreateModal = ref(false);
const showEditModal = ref(false);
const showViewModal = ref(false);
const showTransferModal = ref(false);
const showDeleteModal = ref(false);
const showSecretValue = ref(false);
const showValue = ref(false);

// Form state
const secretForm = reactive({
  id: '',
  name: '',
  type: '',
  scope: 'general',
  chat_id: '',
  value: '',
  description: '',
  expires_at: '',
  tags: [] as string[],
  // Infrastructure host specific fields
  host: '',
  ssh_port: 22,
  vnc_port: null as number | null,
  username: 'root',
  auth_type: 'ssh_key' as 'ssh_key' | 'password',
  ssh_key: '',
  ssh_password: '',
  vnc_password: '',
  capabilities: ['ssh'] as string[],
  os: '',
  purpose: ''
});
const tagsInput = ref('');
const viewingSecret = ref<any>(null);
const transferringSecret = ref<any>(null);
const deletingSecret = ref<any>(null);

// Debounced search
const debouncedSearch = useDebounce(searchQuery, 300);

// Computed
const filteredSecrets = computed(() => {
  let result = [...secrets.value];

  // Filter by category/type
  if (selectedCategory.value !== 'all') {
    result = result.filter(s => s.type === selectedCategory.value);
  }

  // Filter by scope
  if (selectedScope.value) {
    result = result.filter(s => s.scope === selectedScope.value);
  }

  // Filter expired only
  if (showExpiredOnly.value) {
    result = result.filter(s => isExpired(s));
  }

  // Search filter
  if (debouncedSearch.value) {
    const query = debouncedSearch.value.toLowerCase();
    result = result.filter(s =>
      s.name.toLowerCase().includes(query) ||
      s.description?.toLowerCase().includes(query) ||
      s.tags?.some((t: string) => t.toLowerCase().includes(query))
    );
  }

  return result;
});

const currentCategoryLabel = computed(() => {
  if (showExpiredOnly.value) return 'Expired Credentials';
  if (selectedScope.value) return `${selectedScope.value.charAt(0).toUpperCase() + selectedScope.value.slice(1)} Credentials`;
  if (selectedCategory.value === 'all') return 'All Credentials';
  const cat = credentialCategories.value.find(c => c.type === selectedCategory.value);
  return cat?.label || 'Credentials';
});

const hasActiveFilters = computed(() => {
  return selectedCategory.value !== 'all' || selectedScope.value || showExpiredOnly.value || searchQuery.value;
});

const emptyStateIcon = computed(() => {
  if (hasActiveFilters.value) return 'fas fa-search';
  return 'fas fa-key';
});

const emptyStateMessage = computed(() => {
  if (hasActiveFilters.value) return 'No credentials match your filters.';
  return 'No credentials yet. Create your first credential to get started.';
});

const modalTitle = computed(() => {
  if (showEditModal.value) return 'Edit Credential';
  if (!secretForm.type) return 'New Credential';
  return `New ${getTypeLabel(secretForm.type)}`;
});

const isFormValid = computed(() => {
  if (!secretForm.type) return false;
  if (!secretForm.name.trim()) return false;
  if (!secretForm.scope) return false;

  // Infrastructure host has different validation
  if (secretForm.type === 'infrastructure_host') {
    if (!secretForm.host.trim()) return false;
    if (!secretForm.username.trim()) return false;
    if (secretForm.auth_type === 'ssh_key' && !showEditModal.value && !secretForm.ssh_key.trim()) return false;
    if (secretForm.auth_type === 'password' && !showEditModal.value && !secretForm.ssh_password.trim()) return false;
    if (secretForm.capabilities.includes('vnc') && !secretForm.vnc_port) return false;
    return true;
  }

  // Standard secrets require value
  if (!showEditModal.value && !secretForm.value.trim()) return false;
  return true;
});

// Methods
const loadSecrets = async () => {
  loading.value = true;
  try {
    const backendUrl = getBackendUrl();

    // Fetch secrets and stats - infrastructure_host is now a regular secret type
    const [secretsResponse, statsResponse, legacyHostsResponse] = await Promise.all([
      secretsApiClient.getSecrets({}),
      secretsApiClient.getSecretsStats(),
      // Also fetch legacy hosts for backwards compatibility (will be migrated eventually)
      fetch(`${backendUrl}/api/infrastructure/hosts`).then(r => r.ok ? r.json() : { hosts: [] }).catch(() => ({ hosts: [] }))
    ]);

    // Convert legacy infrastructure hosts to secret-like format for unified display
    const legacyInfraSecrets = (legacyHostsResponse.hosts || []).map((host: any) => ({
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
        auth_type: host.auth_type,
        capabilities: host.capabilities
      },
      _isLegacyHost: true  // Flag for legacy hosts that need different delete API
    }));

    // Merge regular secrets with legacy infrastructure hosts
    // (new infra hosts are already in secrets with type=infrastructure_host)
    secrets.value = [...(secretsResponse.secrets || []), ...legacyInfraSecrets];

    // Update stats
    const legacyInfraCount = legacyInfraSecrets.length;
    stats.value = {
      ...statsResponse,
      total_secrets: (statsResponse.total_secrets || 0) + legacyInfraCount,
      by_type: {
        ...statsResponse.by_type,
        infrastructure_host: (statsResponse.by_type?.infrastructure_host || 0) + legacyInfraCount
      }
    };

    showTemplates.value = secrets.value.length === 0;
  } catch (error) {
    logger.error('Failed to load secrets:', error);
  } finally {
    loading.value = false;
  }
};

const selectCategory = (type: string) => {
  selectedCategory.value = type;
  selectedScope.value = '';
  showExpiredOnly.value = false;
};

const selectScope = (scope: string) => {
  if (selectedScope.value === scope) {
    selectedScope.value = '';
  } else {
    selectedScope.value = scope;
  }
  selectedCategory.value = 'all';
  showExpiredOnly.value = false;
};

const toggleExpiredFilter = () => {
  showExpiredOnly.value = !showExpiredOnly.value;
  if (showExpiredOnly.value) {
    selectedCategory.value = 'all';
    selectedScope.value = '';
  }
};

const clearFilters = () => {
  selectedCategory.value = 'all';
  selectedScope.value = '';
  showExpiredOnly.value = false;
  searchQuery.value = '';
};

const toggleView = () => {
  viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid';
};

const getCategoryCount = (type: string) => {
  return secrets.value.filter(s => s.type === type).length;
};

const getTypeColor = (type: string) => {
  const cat = credentialCategories.value.find(c => c.type === type);
  return cat?.color || getCssVar('--text-tertiary', '#6b7280');
};

const getTypeIcon = (type: string) => {
  const cat = credentialCategories.value.find(c => c.type === type);
  return cat?.icon || 'fas fa-key';
};

const getTypeLabel = (type: string) => {
  const cat = credentialCategories.value.find(c => c.type === type);
  return cat?.label.replace(/s$/, '') || type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || '';
};

const getValueLabel = (type: string) => {
  const labels: Record<string, string> = {
    api_key: 'API Key',
    token: 'Token',
    password: 'Password',
    ssh_key: 'Private Key',
    database_url: 'Connection String',
    certificate: 'Certificate Content',
    other: 'Secret Value'
  };
  return labels[type] || 'Value';
};

const getValuePlaceholder = (type: string) => {
  const placeholders: Record<string, string> = {
    api_key: 'sk-xxxxxxxxxxxxxxxxxxxx',
    token: 'ghp_xxxxxxxxxxxxxxxxxxxx',
    password: 'Enter password',
    ssh_key: '-----BEGIN OPENSSH PRIVATE KEY-----\n...',
    database_url: 'postgresql://user:password@host:5432/database',
    certificate: '-----BEGIN CERTIFICATE-----\n...',
    other: 'Enter secret value'
  };
  return placeholders[type] || 'Enter value';
};

const isMultilineSecret = (type: string) => {
  return ['ssh_key', 'certificate'].includes(type);
};

const getValueRows = (type: string) => {
  return isMultilineSecret(type) ? 6 : 3;
};

const getValueHint = (type: string) => {
  const hints: Record<string, string> = {
    api_key: 'Your API key will be encrypted and stored securely',
    ssh_key: 'Paste your entire private key including BEGIN/END markers',
    database_url: 'Include username, password, host, port, and database name',
    certificate: 'Paste the full certificate in PEM format',
    token: 'Access tokens are sensitive - keep them private',
    password: 'Passwords are encrypted before storage'
  };
  return hints[type] || 'This value will be encrypted and stored securely';
};

const selectSecret = (secret: any) => {
  selectedSecretId.value = secret.id;
};

const selectType = (type: string) => {
  secretForm.type = type;
};

const useTemplate = (template: any) => {
  resetForm();
  secretForm.type = template.type;
  secretForm.name = template.name;
  secretForm.tags = [template.id];
  showCreateModal.value = true;
};

const openCreateModal = () => {
  resetForm();
  showCreateModal.value = true;
};

const viewSecret = async (secret: any) => {
  try {
    // Handle infrastructure hosts - show connection info instead of raw credential
    if (secret.type === 'infrastructure_host') {
      const meta = secret.metadata || {};
      viewingSecret.value = {
        ...secret,
        value: `${meta.username || 'root'}@${meta.host || 'unknown'}:${meta.ssh_port || 22}`,
        _isInfraHost: true
      };
      showSecretValue.value = false;
      showViewModal.value = true;
      return;
    }

    const response = await secretsApiClient.getSecret(secret.id, { chatId: secret.chat_id });
    viewingSecret.value = response;
    showSecretValue.value = false;
    showViewModal.value = true;
  } catch (error) {
    logger.error('Failed to load secret details:', error);
  }
};

const editSecret = (secret: any) => {
  secretForm.id = secret.id;
  secretForm.name = secret.name;
  secretForm.type = secret.type;
  secretForm.scope = secret.scope;
  secretForm.chat_id = secret.chat_id || '';
  secretForm.description = secret.description || '';
  secretForm.expires_at = secret.expires_at ? new Date(secret.expires_at).toISOString().slice(0, 16) : '';
  secretForm.tags = [...(secret.tags || [])];
  tagsInput.value = secretForm.tags.join(', ');

  // Populate infrastructure host specific fields from metadata
  if (secret.type === 'infrastructure_host' && secret.metadata) {
    const meta = secret.metadata;
    secretForm.host = meta.host || '';
    secretForm.ssh_port = meta.ssh_port || 22;
    secretForm.vnc_port = meta.vnc_port || null;
    secretForm.username = meta.username || 'root';
    secretForm.auth_type = meta.auth_type || 'password';
    secretForm.capabilities = meta.capabilities || ['ssh'];
    secretForm.os = meta.os || '';
    secretForm.purpose = meta.purpose || '';
  }

  showViewModal.value = false;
  showEditModal.value = true;
};

const transferSecret = (secret: any) => {
  transferringSecret.value = secret;
  showTransferModal.value = true;
};

const confirmDelete = (secret: any) => {
  deletingSecret.value = secret;
  showDeleteModal.value = true;
};

const deleteSecret = async () => {
  if (!deletingSecret.value) return;

  deleting.value = true;
  try {
    // Handle legacy infrastructure hosts differently (they use old API)
    if (deletingSecret.value._isLegacyHost) {
      const backendUrl = getBackendUrl();
      const response = await fetch(`${backendUrl}/api/infrastructure/hosts/${deletingSecret.value.id}`, {
        method: 'DELETE'
      });
      if (!response.ok) {
        throw new Error('Failed to delete infrastructure host');
      }
    } else {
      // All secrets (including new infrastructure_host type) use unified secrets API
      await secretsApiClient.deleteSecret(deletingSecret.value.id, { chatId: deletingSecret.value.chat_id });
    }
    showDeleteModal.value = false;
    deletingSecret.value = null;
    await loadSecrets();
  } catch (error) {
    logger.error('Failed to delete secret:', error);
  } finally {
    deleting.value = false;
  }
};

const confirmTransfer = async () => {
  if (!transferringSecret.value) return;

  transferring.value = true;
  try {
    await secretsApiClient.transferSecrets({
      secret_ids: [transferringSecret.value.id],
      target_scope: 'general'
    }, { chatId: transferringSecret.value.chat_id });
    showTransferModal.value = false;
    transferringSecret.value = null;
    await loadSecrets();
  } catch (error) {
    logger.error('Failed to transfer secret:', error);
  } finally {
    transferring.value = false;
  }
};

const saveSecret = async () => {
  if (!isFormValid.value) return;

  saving.value = true;
  try {
    const appStore = useAppStore();

    // Build base secret data
    const secretData: any = {
      name: secretForm.name,
      type: secretForm.type,
      scope: secretForm.scope,
      chat_id: secretForm.scope === 'chat' ? (secretForm.chat_id || appStore.currentSessionId) : null,
      description: secretForm.description,
      expires_at: secretForm.expires_at ? new Date(secretForm.expires_at).toISOString() : null,
      tags: secretForm.tags
    };

    // Handle infrastructure_host type - store host info in metadata, credential in value
    if (secretForm.type === 'infrastructure_host') {
      secretData.metadata = {
        host: secretForm.host,
        ssh_port: secretForm.ssh_port,
        vnc_port: secretForm.vnc_port,
        username: secretForm.username,
        auth_type: secretForm.auth_type,
        capabilities: secretForm.capabilities,
        os: secretForm.os || null,
        purpose: secretForm.purpose || null
      };
      // Store the actual credential (password or SSH key) in the encrypted value field
      if (!showEditModal.value) {
        secretData.value = secretForm.auth_type === 'ssh_key'
          ? secretForm.ssh_key
          : secretForm.ssh_password;
      }
      // Auto-generate description if empty
      if (!secretData.description) {
        secretData.description = `${secretForm.username}@${secretForm.host}:${secretForm.ssh_port}`;
      }
    }

    if (showEditModal.value) {
      await secretsApiClient.updateSecret(secretForm.id, secretData, { chatId: secretData.chat_id });
    } else {
      // For non-infrastructure_host types, use the standard value field
      if (secretForm.type !== 'infrastructure_host') {
        secretData.value = secretForm.value;
      }
      await secretsApiClient.createSecret(secretData);
    }

    closeModals();
    await loadSecrets();
  } catch (error) {
    logger.error('Failed to save secret:', error);
  } finally {
    saving.value = false;
  }
};

const closeModals = () => {
  showCreateModal.value = false;
  showEditModal.value = false;
  resetForm();
};

const closeViewModal = () => {
  showViewModal.value = false;
  viewingSecret.value = null;
  showSecretValue.value = false;
};

const closeTransferModal = () => {
  showTransferModal.value = false;
  transferringSecret.value = null;
};

const resetForm = () => {
  Object.assign(secretForm, {
    id: '',
    name: '',
    type: '',
    scope: 'general',
    chat_id: '',
    value: '',
    description: '',
    expires_at: '',
    tags: [],
    // Infrastructure host specific fields
    host: '',
    ssh_port: 22,
    vnc_port: null,
    username: 'root',
    auth_type: 'ssh_key',
    ssh_key: '',
    ssh_password: '',
    vnc_password: '',
    capabilities: ['ssh'],
    os: '',
    purpose: ''
  });
  tagsInput.value = '';
  showValue.value = false;
};

const updateTags = () => {
  secretForm.tags = tagsInput.value
    .split(',')
    .map(tag => tag.trim())
    .filter(tag => tag.length > 0);
};

const toggleValueVisibility = () => {
  showValue.value = !showValue.value;
};

const toggleSecretValue = () => {
  showSecretValue.value = !showSecretValue.value;
};

const copySecretValue = async () => {
  if (viewingSecret.value?.value) {
    try {
      await navigator.clipboard.writeText(viewingSecret.value.value);
      // Could add toast notification here
    } catch (error) {
      logger.error('Failed to copy to clipboard:', error);
    }
  }
};

const formatDate = (dateString: string) => {
  if (!dateString) return 'N/A';
  return formatDateTime(dateString);
};

const formatRelativeTime = (dateString: string) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const absDiff = Math.abs(diff);

  if (absDiff < 60000) return diff < 0 ? 'just now' : 'in a moment';
  if (absDiff < 3600000) {
    const mins = Math.floor(absDiff / 60000);
    return diff < 0 ? `${mins}m ago` : `in ${mins}m`;
  }
  if (absDiff < 86400000) {
    const hours = Math.floor(absDiff / 3600000);
    return diff < 0 ? `${hours}h ago` : `in ${hours}h`;
  }
  const days = Math.floor(absDiff / 86400000);
  return diff < 0 ? `${days}d ago` : `in ${days}d`;
};

const truncate = (text: string, length: number) => {
  if (!text || text.length <= length) return text;
  return text.substring(0, length) + '...';
};

const isExpired = (secret: any) => {
  if (!secret?.expires_at) return false;
  return new Date(secret.expires_at) < new Date();
};

const isExpiringSoon = (secret: any) => {
  if (!secret?.expires_at || isExpired(secret)) return false;
  const expiry = new Date(secret.expires_at);
  const now = new Date();
  const daysUntilExpiry = (expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return daysUntilExpiry <= 7;
};

// Lifecycle
onMounted(() => {
  loadSecrets();
});

// Watch for scope changes to reload with filter
watch(selectedScope, () => {
  // Local filtering handles this, no need to reload
});
</script>

<style scoped>
/* Issue #704: Uses CSS design tokens via getCssVar() helper */
.secrets-manager-n8n {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.secrets-sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-header i {
  color: var(--color-primary);
}

.sidebar-search {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-wrapper i {
  position: absolute;
  left: 12px;
  color: var(--text-muted);
  font-size: 14px;
}

.search-wrapper .search-input {
  width: 100%;
  padding: 10px 36px 10px 36px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s;
  background: var(--bg-input);
  color: var(--text-primary);
}

.search-wrapper .search-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.clear-search {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: var(--text-muted);
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.category-divider {
  padding: 12px 20px 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-secondary);
}

.category-item:hover {
  background: var(--bg-hover);
}

.category-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: 14px;
}

.category-item span:first-of-type:not(.count) {
  flex: 1;
  font-size: 14px;
}

.category-item .count {
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--text-tertiary);
}

.category-item.active .count {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.category-item.alert {
  color: var(--color-error);
}

.category-item.alert .count.alert {
  background: var(--color-error);
  color: var(--text-on-error);
}

.sidebar-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-create {
  width: 100%;
  padding: 12px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-create:hover {
  background: var(--color-primary-hover);
}

/* Main Content */
.secrets-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.btn-icon:hover {
  background: var(--bg-hover);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Stats Bar */
.stats-bar {
  display: flex;
  gap: 24px;
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-item i {
  color: var(--text-muted);
  font-size: 14px;
}

.stat-item .stat-value {
  font-weight: 600;
  color: var(--text-primary);
}

.stat-item .stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.stat-item.warning {
  color: var(--color-warning);
}

.stat-item.warning i,
.stat-item.warning .stat-value {
  color: var(--color-warning);
}

/* Loading */
.loading-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-tertiary);
}

/* Credentials Container */
.credentials-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.credentials-container.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  align-content: start;
}

.credentials-container.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Credential Card */
.credential-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.credential-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md);
}

.credential-card.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.credential-card.expired {
  border-left: 3px solid var(--color-error);
}

.card-icon {
  width: 48px;
  height: 48px;
  min-width: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 18px;
}

.card-content {
  flex: 1;
  min-width: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.card-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-badges {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  text-transform: capitalize;
}

.badge.general {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.badge.chat {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge.expired {
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-description {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.card-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-muted);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta-item.text-warning {
  color: var(--color-warning);
}

.card-tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.tag {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  color: var(--text-secondary);
}

.tag.more {
  color: var(--color-primary);
}

.card-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.credential-card:hover .card-actions {
  opacity: 1;
}

.action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--bg-hover);
  color: var(--color-primary);
}

.action-btn.delete:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Templates Section */
.templates-section {
  padding: 24px;
}

.templates-section h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.templates-section h3 i {
  color: var(--color-primary);
}

.templates-subtitle {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-tertiary);
}

.templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.template-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.template-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.template-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 16px;
}

.template-info h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.template-info p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Form Styles */
.credential-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.template-selection h4 {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.type-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.type-option:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.type-option .type-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 18px;
}

.type-option span {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  text-align: center;
}

.selected-type {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  margin-bottom: 8px;
}

.selected-type .type-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 16px;
}

.selected-type .type-info {
  display: flex;
  flex-direction: column;
}

.selected-type .type-label {
  font-weight: 600;
  color: var(--text-primary);
}

.selected-type .change-type {
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: var(--color-primary);
  cursor: pointer;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row.two-col > .form-group {
  flex: 1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.form-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--color-error);
}

.form-input {
  padding: 10px 12px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s;
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.input-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.secret-input-wrapper {
  position: relative;
}

.secret-input {
  padding-right: 44px;
  font-family: var(--font-mono);
  font-size: 13px;
}

.secret-masked {
  -webkit-text-security: disc;
  text-security: disc;
  color: var(--text-tertiary);
}

.toggle-visibility {
  position: absolute;
  right: 8px;
  top: 8px;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 6px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
}

.scope-selector {
  display: flex;
  gap: 12px;
}

.scope-option {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.scope-option:hover {
  border-color: var(--color-primary);
}

.scope-option.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.scope-option input[type="radio"] {
  display: none;
}

.scope-option i {
  font-size: 20px;
  color: var(--text-muted);
  margin-top: 2px;
}

.scope-option.active i {
  color: var(--color-primary);
}

.scope-option > div {
  display: flex;
  flex-direction: column;
}

.scope-option span {
  font-weight: 500;
  color: var(--text-primary);
}

.scope-option small {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* View Modal */
.view-credential {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.view-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-default);
}

.view-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 24px;
}

.view-title h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.view-type {
  font-size: 14px;
  color: var(--text-tertiary);
}

.view-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.view-section label {
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
}

.view-section p {
  margin: 0;
  color: var(--text-primary);
}

.secret-display {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.secret-display code {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 13px;
  word-break: break-all;
  color: var(--text-primary);
}

.secret-actions {
  display: flex;
  gap: 4px;
}

.view-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.view-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.view-item label {
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
}

.view-item span {
  font-size: 14px;
  color: var(--text-primary);
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.text-danger {
  color: var(--color-error) !important;
}

.text-warning {
  color: var(--color-warning) !important;
}

/* Transfer & Delete Modals */
.transfer-content,
.delete-content {
  text-align: center;
  padding: 20px 0;
}

.transfer-icon,
.delete-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.transfer-icon {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.delete-icon {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.transfer-content h4,
.delete-content h4 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.transfer-content p,
.delete-content p {
  margin: 0 0 16px;
  color: var(--text-secondary);
}

.transfer-warning,
.delete-warning {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 14px;
}

.transfer-warning {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.delete-warning {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Buttons */
.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-danger {
  padding: 10px 20px;
  background: var(--color-error);
  color: var(--text-on-error);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-danger:hover {
  background: var(--color-error-hover);
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Infrastructure Host Form Styles */
.capability-checkboxes {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.checkbox-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.checkbox-option:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.checkbox-option input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.checkbox-option input[type="checkbox"]:disabled {
  cursor: default;
}

.checkbox-option:has(input:checked) {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
}

.checkbox-option:has(input:disabled) {
  opacity: 0.7;
  cursor: default;
}

.checkbox-option i {
  font-size: 14px;
  color: var(--text-muted);
}

.checkbox-option:has(input:checked) i {
  color: var(--color-primary);
}

.checkbox-option span {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

/* Responsive */
@media (max-width: 768px) {
  .secrets-manager-n8n {
    flex-direction: column;
  }

  .secrets-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
  }

  .credentials-container.grid {
    grid-template-columns: 1fr;
  }

  .form-row.two-col {
    flex-direction: column;
  }

  .scope-selector {
    flex-direction: column;
  }

  .view-grid {
    grid-template-columns: 1fr;
  }
}
</style>
