<template>
  <div class="secrets-manager">
    <div class="secrets-header">
      <h2>Secrets Management</h2>
      <div class="secrets-actions">
        <button @click="openCreateModal" class="btn-primary">
          <i class="icon-plus"></i> Add Secret
        </button>
        <button @click="loadSecrets" class="btn-secondary" :disabled="loading">
          <i class="icon-refresh" :class="{ spinning: loading }"></i> Refresh
        </button>
      </div>
    </div>

    <div class="secrets-filters">
      <div class="filter-group">
        <label>Scope:</label>
        <select v-model="selectedScope" @change="loadSecrets">
          <option value="">All Scopes</option>
          <option value="chat">Chat-scoped</option>
          <option value="general">General</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Type:</label>
        <select v-model="selectedType" @change="loadSecrets">
          <option value="">All Types</option>
          <option v-for="type in secretTypes" :key="type.value" :value="type.value">
            {{ type.label }}
          </option>
        </select>
      </div>
      <div class="filter-group">
        <input 
          type="text" 
          v-model="searchQuery" 
          @input="filterSecrets"
          placeholder="Search secrets..."
          class="search-input"
        />
      </div>
    </div>

    <div class="secrets-stats" v-if="stats">
      <BasePanel variant="elevated" size="small">
        <h4>Total Secrets</h4>
        <span class="stat-value">{{ stats.total_secrets }}</span>
      </BasePanel>
      <BasePanel variant="elevated" size="small">
        <h4>Chat-scoped</h4>
        <span class="stat-value">{{ stats.by_scope?.chat || 0 }}</span>
      </BasePanel>
      <BasePanel variant="elevated" size="small">
        <h4>General</h4>
        <span class="stat-value">{{ stats.by_scope?.general || 0 }}</span>
      </BasePanel>
      <BasePanel variant="elevated" size="small" v-if="stats.expired_count > 0">
        <h4>Expired</h4>
        <span class="stat-value expired">{{ stats.expired_count }}</span>
      </BasePanel>
    </div>

    <div class="secrets-list">
      <div v-if="loading" class="loading-spinner">Loading secrets...</div>
      
      <EmptyState
        v-else-if="filteredSecrets.length === 0"
        icon="fas fa-key"
        message="No secrets found matching your criteria."
      >
        <template #actions>
          <button @click="openCreateModal()" class="btn-primary">
            Create your first secret
          </button>
        </template>
      </EmptyState>

      <div v-else class="secrets-grid">
        <div 
          v-for="secret in filteredSecrets" 
          :key="secret.id"
          class="secret-card"
          :class="{ 'expired': isExpired(secret) }"
        >
          <div class="secret-header">
            <h3>{{ secret.name }}</h3>
            <div class="secret-badges">
              <StatusBadge :variant="getScopeVariant(secret.scope)" size="small">{{ secret.scope }}</StatusBadge>
              <StatusBadge :variant="getTypeVariant(secret.type)" size="small">{{ secret.type.replace('_', ' ') }}</StatusBadge>
            </div>
          </div>
          
          <div class="secret-info">
            <p v-if="secret.description" class="secret-description">{{ secret.description }}</p>
            <div class="secret-metadata">
              <small>Created: {{ formatDate(secret.created_at) }}</small>
              <small v-if="secret.expires_at">Expires: {{ formatDate(secret.expires_at) }}</small>
              <small v-if="secret.chat_id">Chat: {{ secret.chat_id.substring(0, 8) }}...</small>
            </div>
            <div v-if="secret.tags && secret.tags.length > 0" class="secret-tags">
              <span v-for="tag in secret.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
          </div>

          <div class="secret-actions">
            <button @click="viewSecret(secret)" class="btn-view" title="View secret">
              <i class="icon-eye"></i>
            </button>
            <button @click="editSecret(secret)" class="btn-edit" title="Edit secret">
              <i class="icon-edit"></i>
            </button>
            <button 
              @click="transferSecret(secret)" 
              class="btn-transfer" 
              title="Transfer scope"
              v-if="secret.scope === 'chat'"
            >
              <i class="icon-transfer"></i>
            </button>
            <button @click="deleteSecret(secret)" class="btn-delete" title="Delete secret">
              <i class="icon-trash"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Secret Modal -->
    <BaseModal
      :modelValue="showCreateModal || showEditModal"
      @update:modelValue="val => !val && closeModals()"
      :title="showEditModal ? 'Edit Secret' : 'Create New Secret'"
      size="medium"
      :closeOnOverlay="!saving"
    >
      <form @submit.prevent="saveSecret">
          <div class="form-group">
            <label>Name <span class="required">*</span></label>
            <input 
              type="text" 
              v-model="secretForm.name" 
              required 
              placeholder="Enter secret name"
              class="form-input"
            />
          </div>

          <div class="form-group">
            <label>Type <span class="required">*</span></label>
            <select v-model="secretForm.type" required class="form-input">
              <option value="">Select type...</option>
              <option v-for="type in secretTypes" :key="type.value" :value="type.value">
                {{ type.label }}
              </option>
            </select>
          </div>

          <div class="form-group">
            <label>Scope <span class="required">*</span></label>
            <select v-model="secretForm.scope" required class="form-input" @change="onScopeChange">
              <option value="">Select scope...</option>
              <option value="chat">Chat-scoped (current conversation only)</option>
              <option value="general">General (all conversations)</option>
            </select>
          </div>

          <div v-if="secretForm.scope === 'chat'" class="form-group">
            <label>Chat ID</label>
            <input 
              type="text" 
              v-model="secretForm.chat_id" 
              placeholder="Current chat ID (auto-filled)"
              class="form-input"
              readonly
            />
          </div>

          <div class="form-group" v-if="!showEditModal">
            <label>Secret Value <span class="required">*</span></label>
            <textarea 
              v-model="secretForm.value" 
              required 
              placeholder="Enter the secret value"
              class="form-input"
              rows="3"
            ></textarea>
          </div>

          <div class="form-group">
            <label>Description</label>
            <textarea 
              v-model="secretForm.description" 
              placeholder="Optional description"
              class="form-input"
              rows="2"
            ></textarea>
          </div>

          <div class="form-group">
            <label>Tags</label>
            <input 
              type="text" 
              v-model="tagsInput" 
              placeholder="Comma-separated tags"
              class="form-input"
              @input="updateTags"
            />
          </div>

          <div class="form-group">
            <label>Expiration Date</label>
            <input
              type="datetime-local"
              v-model="secretForm.expires_at"
              class="form-input"
            />
          </div>
        </form>

      <template #actions>
        <button type="button" @click="closeModals" class="btn-secondary">Cancel</button>
        <button type="submit" @click="saveSecret" class="btn-primary" :disabled="saving">
          {{ saving ? 'Saving...' : (showEditModal ? 'Update' : 'Create') }}
        </button>
      </template>
    </BaseModal>

    <!-- View Secret Modal -->
    <BaseModal
      v-model="showViewModal"
      :title="`View Secret: ${viewingSecret?.name || ''}`"
      size="medium"
    >
          <div class="secret-details">
            <div class="detail-group">
              <label>Type:</label>
              <span>{{ viewingSecret?.type?.replace('_', ' ') || 'N/A' }}</span>
            </div>
            <div class="detail-group">
              <label>Scope:</label>
              <span>{{ viewingSecret?.scope }}</span>
            </div>
            <div class="detail-group" v-if="viewingSecret?.description">
              <label>Description:</label>
              <p>{{ viewingSecret.description }}</p>
            </div>
            <div class="detail-group">
              <label>Secret Value:</label>
              <div class="secret-value-container">
                <input 
                  :type="showSecretValue ? 'text' : 'password'" 
                  :value="viewingSecret?.value || 'Loading...'" 
                  readonly 
                  class="secret-value-input"
                />
                <button 
                  type="button" 
                  @click="toggleSecretValue()" 
                  class="btn-toggle-secret"
                >
                  {{ showSecretValue ? 'Hide' : 'Show' }}
                </button>
              </div>
            </div>
            <div class="detail-group" v-if="viewingSecret?.tags?.length > 0">
              <label>Tags:</label>
              <div class="tags-list">
                <span v-for="tag in viewingSecret.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
            </div>
            <div class="detail-group">
              <label>Created:</label>
              <span>{{ formatDate(viewingSecret?.created_at) }}</span>
            </div>
            <div class="detail-group" v-if="viewingSecret?.expires_at">
              <label>Expires:</label>
              <span :class="{ 'expired': isExpired(viewingSecret) }">
                {{ formatDate(viewingSecret.expires_at) }}
              </span>
            </div>
          </div>

      <template #actions>
        <button @click="closeViewModal()" class="btn-secondary">Close</button>
        <button @click="copySecretValue" class="btn-primary">
          Copy Value
        </button>
      </template>
    </BaseModal>

    <!-- Transfer Modal -->
    <BaseModal
      v-model="showTransferModal"
      :title="`Transfer Secret: ${transferringSecret?.name || ''}`"
      size="medium"
      :closeOnOverlay="!transferring"
    >
      <form @submit.prevent="confirmTransfer">
          <p>This will move the secret from chat-scoped to general scope, making it accessible across all conversations.</p>
          
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="transferConfirmed" />
              I understand this action cannot be undone
            </label>
          </div>
        </form>

      <template #actions>
        <button type="button" @click="closeTransferModal()" class="btn-secondary">Cancel</button>
        <button type="submit" @click="confirmTransfer" class="btn-primary" :disabled="!transferConfirmed || transferring">
          {{ transferring ? 'Transferring...' : 'Transfer to General' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted } from 'vue';
import { secretsApiClient } from '../utils/SecretsApiClient';
import { useAppStore } from '../stores/useAppStore.ts';
import { formatDateTime } from '@/utils/formatHelpers';
import { useDebounce } from '@/composables/useDebounce';
import { useModal } from '@/composables/useModal';
import { useAsyncOperation } from '@/composables/useAsyncOperation';
import EmptyState from '@/components/ui/EmptyState.vue';
import StatusBadge from '@/components/ui/StatusBadge.vue';
import BaseModal from '@/components/ui/BaseModal.vue';
import BasePanel from '@/components/base/BasePanel.vue';

export default {
  name: 'SecretsManager',
  components: {
    EmptyState,
    StatusBadge,
    BaseModal,
    BasePanel
  },
  setup() {
    // State
    const secrets = ref([]);
    const secretTypes = ref([]);
    const stats = ref(null);

    // Filters
    const selectedScope = ref('');
    const selectedType = ref('');
    const searchQuery = ref('');
    const debouncedSearchQuery = useDebounce(searchQuery, 300); // Debounce search for better performance

    // Use composables for modals
    const { isOpen: showCreateModal, open: openCreateModal, close: closeCreateModal } = useModal('create-secret');
    const { isOpen: showEditModal, open: openEditModal, close: closeEditModal } = useModal('edit-secret');
    const { isOpen: showViewModal, open: openViewModal, close: closeViewModal } = useModal('view-secret');
    const { isOpen: showTransferModal, open: openTransferModal, close: closeTransferModal } = useModal('transfer-secret');
    const { isOpen: showSecretValue, toggle: toggleSecretValue } = useModal('secret-value');

    // Use composables for async operations
    const { execute: loadSecretsOp, loading } = useAsyncOperation();
    const { execute: saveSecretOp, loading: saving } = useAsyncOperation();
    const { execute: transferSecretOp, loading: transferring } = useAsyncOperation();
    
    // Forms
    const secretForm = reactive({
      id: '',
      name: '',
      type: '',
      scope: '',
      chat_id: '',
      value: '',
      description: '',
      expires_at: '',
      tags: []
    });
    
    const tagsInput = ref('');
    const viewingSecret = ref(null);
    const transferringSecret = ref(null);
    const transferConfirmed = ref(false);
    
    // Computed
    const filteredSecrets = computed(() => {
      let filtered = secrets.value;

      if (selectedScope.value) {
        filtered = filtered.filter(s => s.scope === selectedScope.value);
      }

      if (selectedType.value) {
        filtered = filtered.filter(s => s.type === selectedType.value);
      }

      // Use debounced search for better performance
      if (debouncedSearchQuery.value) {
        const query = debouncedSearchQuery.value.toLowerCase();
        filtered = filtered.filter(s =>
          s.name.toLowerCase().includes(query) ||
          s.description?.toLowerCase().includes(query) ||
          s.tags?.some(tag => tag.toLowerCase().includes(query))
        );
      }

      return filtered;
    });
    
    // Methods
    const loadSecrets = async () => {
      loading.value = true;
      try {
        const response = await secretsApiClient.getSecrets({ scope: selectedScope.value });
        secrets.value = response.secrets || [];
      } catch (error) {
        console.error('Failed to load secrets:', error);
      } finally {
        loading.value = false;
      }
    };
    
    const loadSecretTypes = async () => {
      try {
        const response = await secretsApiClient.getSecretTypes();
        secretTypes.value = response.types || [];
      } catch (error) {
        console.error('Failed to load secret types:', error);
      }
    };
    
    const loadStats = async () => {
      try {
        const response = await secretsApiClient.getSecretsStats();
        stats.value = response;
      } catch (error) {
        console.error('Failed to load secrets stats:', error);
      }
    };
    
    const filterSecrets = () => {
      // Filtering is handled by computed property
    };
    
    const viewSecret = async (secret) => {
      try {
        const response = await secretsApiClient.getSecret(secret.id, { chatId: secret.chat_id });
        viewingSecret.value = response;
        showSecretValue.value = false;
        showViewModal.value = true;
      } catch (error) {
        console.error('Failed to load secret details:', error);
        alert('Failed to load secret details');
      }
    };
    
    const editSecret = (secret) => {
      secretForm.id = secret.id;
      secretForm.name = secret.name;
      secretForm.type = secret.type;
      secretForm.scope = secret.scope;
      secretForm.chat_id = secret.chat_id || '';
      secretForm.description = secret.description || '';
      secretForm.expires_at = secret.expires_at ? new Date(secret.expires_at).toISOString().slice(0, 16) : '';
      secretForm.tags = [...(secret.tags || [])];
      tagsInput.value = secretForm.tags.join(', ');
      showEditModal.value = true;
    };
    
    const deleteSecret = async (secret) => {
      if (!confirm(`Are you sure you want to delete "${secret.name}"?`)) return;
      
      try {
        await secretsApiClient.deleteSecret(secret.id, { chatId: secret.chat_id });
        await loadSecrets();
        await loadStats();
      } catch (error) {
        console.error('Failed to delete secret:', error);
        alert('Failed to delete secret');
      }
    };
    
    const transferSecret = (secret) => {
      transferringSecret.value = secret;
      transferConfirmed.value = false;
      showTransferModal.value = true;
    };
    
    const confirmTransfer = async () => {
      if (!transferConfirmed.value) return;
      
      transferring.value = true;
      try {
        const requestData = {
          secret_ids: [transferringSecret.value.id],
          target_scope: 'general'
        };
        
        await secretsApiClient.transferSecrets(requestData, { chatId: transferringSecret.value.chat_id });
        showTransferModal.value = false;
        await loadSecrets();
        await loadStats();
      } catch (error) {
        console.error('Failed to transfer secret:', error);
        alert('Failed to transfer secret');
      } finally {
        transferring.value = false;
      }
    };
    
    const saveSecret = async () => {
      saving.value = true;
      try {
        const secretData = {
          name: secretForm.name,
          type: secretForm.type,
          scope: secretForm.scope,
          chat_id: secretForm.scope === 'chat' ? (secretForm.chat_id || getCurrentChatId()) : null,
          description: secretForm.description,
          expires_at: secretForm.expires_at ? new Date(secretForm.expires_at).toISOString() : null,
          tags: secretForm.tags
        };
        
        if (showEditModal.value) {
          // Update existing secret
          await secretsApiClient.updateSecret(secretForm.id, secretData, { chatId: secretData.chat_id });
        } else {
          // Create new secret
          secretData.value = secretForm.value;
          await secretsApiClient.createSecret(secretData);
        }
        
        closeModals();
        await loadSecrets();
        await loadStats();
      } catch (error) {
        console.error('Failed to save secret:', error);
        alert('Failed to save secret');
      } finally {
        saving.value = false;
      }
    };
    
    const closeModals = () => {
      showCreateModal.value = false;
      showEditModal.value = false;
      showViewModal.value = false;
      showTransferModal.value = false;
      resetForm();
    };
    
    const resetForm = () => {
      Object.assign(secretForm, {
        id: '',
        name: '',
        type: '',
        scope: '',
        chat_id: '',
        value: '',
        description: '',
        expires_at: '',
        tags: []
      });
      tagsInput.value = '';
    };
    
    const updateTags = () => {
      secretForm.tags = tagsInput.value
        .split(',')
        .map(tag => tag.trim())
        .filter(tag => tag.length > 0);
    };
    
    const onScopeChange = () => {
      if (secretForm.scope === 'chat') {
        secretForm.chat_id = getCurrentChatId();
      } else {
        secretForm.chat_id = '';
      }
    };
    
    const getCurrentChatId = () => {
      // Use actual current chat ID from app store
      const appStore = useAppStore();
      return appStore.activeChatId;
    };
    
    const copySecretValue = async () => {
      if (viewingSecret.value?.value) {
        try {
          await navigator.clipboard.writeText(viewingSecret.value.value);
          alert('Secret value copied to clipboard');
        } catch (error) {
          console.error('Failed to copy to clipboard:', error);
          alert('Failed to copy to clipboard');
        }
      }
    };
    
    const formatDate = (dateString) => {
      if (!dateString) return 'N/A';
      return formatDateTime(dateString);
    };
    
    const isExpired = (secret) => {
      if (!secret?.expires_at) return false;
      return new Date(secret.expires_at) < new Date();
    };
    
    // Lifecycle
    onMounted(async () => {
      await Promise.all([
        loadSecrets(),
        loadSecretTypes(),
        loadStats()
      ]);
    });

    // StatusBadge variant mapping functions
    const getScopeVariant = (scope) => {
      const variantMap = {
        'chat': 'info',
        'general': 'primary'
      };
      return variantMap[scope] || 'secondary';
    };

    const getTypeVariant = (type) => {
      const variantMap = {
        'ssh_key': 'warning',
        'password': 'danger',
        'api_key': 'success'
      };
      return variantMap[type] || 'secondary';
    };

    return {
      // State
      secrets,
      secretTypes,
      stats,
      loading,
      saving,
      transferring,
      
      // Filters
      selectedScope,
      selectedType,
      searchQuery,
      filteredSecrets,
      
      // Modals
      showCreateModal,
      showEditModal,
      showViewModal,
      showTransferModal,
      showSecretValue,
      
      // Forms
      secretForm,
      tagsInput,
      viewingSecret,
      transferringSecret,
      transferConfirmed,
      
      // Methods
      loadSecrets,
      filterSecrets,
      viewSecret,
      editSecret,
      deleteSecret,
      transferSecret,
      confirmTransfer,
      saveSecret,
      closeModals,
      updateTags,
      onScopeChange,
      copySecretValue,
      formatDate,
      isExpired,

      // StatusBadge variant mappers
      getScopeVariant,
      getTypeVariant
    };
  }
};
</script>

<style scoped>
.secrets-manager {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.secrets-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.secrets-header h2 {
  margin: 0;
  color: #333;
}

.secrets-actions {
  display: flex;
  gap: 10px;
}

.secrets-filters {
  display: flex;
  gap: 15px;
  margin-bottom: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.filter-group label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
}

.filter-group select, .search-input {
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.search-input {
  min-width: 200px;
}

.secrets-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

/* Stat card content styles - BasePanel handles structure */
.secrets-stats h4 {
  margin: 0 0 5px 0;
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  display: block;
  text-align: center;
}

.stat-value.expired {
  color: #dc3545;
}

.secrets-list {
  min-height: 300px;
}

.loading-spinner {
  text-align: center;
  padding: 50px;
  color: #666;
}

.secrets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.secret-card {
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  transition: transform 0.2s;
}

.secret-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.secret-card.expired {
  border-left: 4px solid #dc3545;
  background: #fff5f5;
}

.secret-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.secret-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.secret-badges {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.secret-description {
  margin: 10px 0;
  color: #666;
  font-size: 14px;
}

.secret-metadata {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 10px 0;
}

.secret-metadata small {
  color: #999;
  font-size: 12px;
}

.secret-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 10px 0;
}

.tag {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  color: #666;
}

.secret-actions {
  display: flex;
  gap: 8px;
  margin-top: 15px;
  justify-content: flex-end;
}

.secret-actions button {
  padding: 6px 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background-color 0.2s;
}

.btn-view {
  background: #e3f2fd;
  color: #1976d2;
}

.btn-edit {
  background: #fff3e0;
  color: #f57c00;
}

.btn-transfer {
  background: #f3e5f5;
  color: #7b1fa2;
}

.btn-delete {
  background: #ffebee;
  color: #c62828;
}

.secret-actions button:hover {
  opacity: 0.8;
}

/* Form Styles */
.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
  color: #333;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: #4caf50;
  box-shadow: 0 0 5px rgba(76, 175, 80, 0.3);
}

.secret-value-container {
  display: flex;
  gap: 10px;
}

.secret-value-input {
  flex: 1;
}

.btn-toggle-secret {
  padding: 8px 12px;
  background: #f8f9fa;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
}

.secret-details {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.detail-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.detail-group label {
  font-weight: 500;
  color: #666;
  font-size: 12px;
  text-transform: uppercase;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.expired {
  color: #dc3545;
}

/* Button Styles */
.btn-primary {
  background: #4caf50;
  color: white;
  border: none;
  padding: 10px 15px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover {
  background: #45a049;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f8f9fa;
  color: #333;
  border: 1px solid #ddd;
  padding: 10px 15px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-secondary:hover {
  background: #e9ecef;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.icon-plus::before { content: '+'; }
.icon-refresh::before { content: '↻'; }
.icon-eye::before { content: '👁'; }
.icon-edit::before { content: '✏'; }
.icon-transfer::before { content: '↔'; }
.icon-trash::before { content: '🗑'; }

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .secrets-filters {
    flex-direction: column;
  }
  
  .secrets-grid {
    grid-template-columns: 1fr;
  }
  
  .secrets-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>