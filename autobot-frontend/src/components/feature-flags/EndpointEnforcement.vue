<template>
  <div class="endpoint-enforcement">
    <div class="section-header">
      <div class="header-info">
        <h3><i class="fas fa-sitemap"></i> Endpoint Overrides</h3>
        <p class="description">
          Configure custom enforcement modes for specific API endpoints. Endpoints without overrides use the global mode.
        </p>
      </div>
      <button @click="showAddModal = true" class="btn-add">
        <i class="fas fa-plus"></i> Add Override
      </button>
    </div>

    <!-- Empty State -->
    <div v-if="Object.keys(overrides).length === 0" class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-sitemap"></i>
      </div>
      <h4>No Endpoint Overrides</h4>
      <p>All endpoints are using the global enforcement mode: <strong>{{ globalModeLabel }}</strong></p>
      <button @click="showAddModal = true" class="btn-primary">
        <i class="fas fa-plus"></i> Add First Override
      </button>
    </div>

    <!-- Overrides List -->
    <div v-else class="overrides-list">
      <div class="global-mode-banner">
        <i class="fas fa-globe"></i>
        <span>Global Mode: <strong>{{ globalModeLabel }}</strong></span>
      </div>

      <div
        v-for="(mode, endpoint) in overrides"
        :key="endpoint"
        class="override-item"
      >
        <div class="override-info">
          <div class="endpoint-path">
            <code>{{ endpoint }}</code>
          </div>
          <div class="override-mode">
            <span class="mode-badge" :class="mode">
              <i :class="getModeIcon(mode)"></i>
              {{ getModeLabel(mode) }}
            </span>
            <span class="vs-global" v-if="mode !== globalMode">
              (Override)
            </span>
          </div>
        </div>
        <div class="override-actions">
          <button
            @click="editOverride(endpoint, mode)"
            class="action-btn"
            title="Edit"
          >
            <i class="fas fa-edit"></i>
          </button>
          <button
            @click="confirmRemove(endpoint)"
            class="action-btn delete"
            title="Remove"
          >
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <BaseModal
      v-model="showAddModal"
      :title="editingEndpoint ? 'Edit Override' : 'Add Endpoint Override'"
      size="medium"
    >
      <form @submit.prevent="saveOverride" class="override-form">
        <div class="form-group">
          <label>Endpoint Path <span class="required">*</span></label>
          <input
            type="text"
            v-model="form.endpoint"
            :disabled="!!editingEndpoint"
            required
            placeholder="/api/chat/sessions/{session_id}"
            class="form-input"
          />
          <small class="input-hint">The API endpoint path (supports path parameters like {id})</small>
        </div>

        <div class="form-group">
          <label>Enforcement Mode <span class="required">*</span></label>
          <div class="mode-selector">
            <label
              v-for="option in modeOptions"
              :key="option.value"
              class="mode-option"
              :class="{ active: form.mode === option.value }"
            >
              <input type="radio" v-model="form.mode" :value="option.value" />
              <div class="option-icon" :class="option.value">
                <i :class="option.icon"></i>
              </div>
              <div class="option-content">
                <span class="option-label">{{ option.label }}</span>
                <span class="option-desc">{{ option.shortDesc }}</span>
              </div>
            </label>
          </div>
        </div>
      </form>

      <template #actions>
        <button type="button" @click="closeModal" class="btn-secondary">Cancel</button>
        <button
          type="submit"
          @click="saveOverride"
          class="btn-primary"
          :disabled="!isFormValid || loading"
        >
          <i v-if="loading" class="fas fa-spinner fa-spin"></i>
          {{ editingEndpoint ? 'Update' : 'Add' }} Override
        </button>
      </template>
    </BaseModal>

    <!-- Remove Confirmation Modal -->
    <BaseModal
      v-model="showRemoveModal"
      title="Remove Override"
      size="small"
    >
      <div class="remove-content">
        <div class="remove-icon">
          <i class="fas fa-undo"></i>
        </div>
        <h4>Revert to Global Mode?</h4>
        <p>
          This will remove the override for <code>{{ removingEndpoint }}</code>
          and the endpoint will use the global enforcement mode.
        </p>
      </div>

      <template #actions>
        <button @click="showRemoveModal = false" class="btn-secondary">Cancel</button>
        <button @click="removeOverride" class="btn-primary" :disabled="loading">
          <i v-if="loading" class="fas fa-spinner fa-spin"></i>
          Remove Override
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue';
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient';
import BaseModal from '@/components/ui/BaseModal.vue';

const props = defineProps<{
  overrides: Record<string, EnforcementMode>;
  globalMode: EnforcementMode;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'add', endpoint: string, mode: EnforcementMode): void;
  (e: 'update', endpoint: string, mode: EnforcementMode): void;
  (e: 'remove', endpoint: string): void;
}>();

// Modal State
const showAddModal = ref(false);
const showRemoveModal = ref(false);
const editingEndpoint = ref<string | null>(null);
const removingEndpoint = ref<string>('');

// Form State
const form = reactive({
  endpoint: '',
  mode: 'log_only' as EnforcementMode,
});

// Mode Options
const modeOptions = [
  {
    value: 'disabled' as EnforcementMode,
    label: 'Disabled',
    icon: 'fas fa-ban',
    shortDesc: 'No validation',
  },
  {
    value: 'log_only' as EnforcementMode,
    label: 'Log Only',
    icon: 'fas fa-clipboard-list',
    shortDesc: 'Log but allow',
  },
  {
    value: 'enforced' as EnforcementMode,
    label: 'Enforced',
    icon: 'fas fa-shield-alt',
    shortDesc: 'Block violations',
  },
];

// Computed
const globalModeLabel = computed(() => getModeLabel(props.globalMode));

const isFormValid = computed(() => {
  return form.endpoint.trim() !== '' && form.mode;
});

// Methods
const getModeLabel = (mode: EnforcementMode) => {
  const labels: Record<EnforcementMode, string> = {
    disabled: 'Disabled',
    log_only: 'Log Only',
    enforced: 'Enforced',
  };
  return labels[mode] || mode;
};

const getModeIcon = (mode: EnforcementMode) => {
  const icons: Record<EnforcementMode, string> = {
    disabled: 'fas fa-ban',
    log_only: 'fas fa-clipboard-list',
    enforced: 'fas fa-shield-alt',
  };
  return icons[mode] || 'fas fa-question';
};

const editOverride = (endpoint: string, mode: EnforcementMode) => {
  editingEndpoint.value = endpoint;
  form.endpoint = endpoint;
  form.mode = mode;
  showAddModal.value = true;
};

const confirmRemove = (endpoint: string) => {
  removingEndpoint.value = endpoint;
  showRemoveModal.value = true;
};

const saveOverride = () => {
  if (!isFormValid.value) return;

  if (editingEndpoint.value) {
    emit('update', form.endpoint, form.mode);
  } else {
    emit('add', form.endpoint, form.mode);
  }

  closeModal();
};

const removeOverride = () => {
  emit('remove', removingEndpoint.value);
  showRemoveModal.value = false;
  removingEndpoint.value = '';
};

const closeModal = () => {
  showAddModal.value = false;
  editingEndpoint.value = null;
  form.endpoint = '';
  form.mode = 'log_only';
};
</script>

<style scoped>
.endpoint-enforcement {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.header-info h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-info h3 i {
  color: var(--color-primary);
}

.header-info .description {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
  max-width: 500px;
}

.btn-add {
  padding: 10px 16px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-add:hover {
  background: var(--color-primary-hover);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 40px 20px;
}

.empty-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.empty-state h4 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-secondary);
}

/* Overrides List */
.overrides-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.global-mode-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.global-mode-banner i {
  color: var(--color-primary);
}

.override-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  transition: all 0.15s;
}

.override-item:hover {
  border-color: var(--color-primary);
}

.override-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.endpoint-path code {
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
}

.override-mode {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.mode-badge.disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.mode-badge.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.mode-badge.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.vs-global {
  font-size: 12px;
  color: var(--text-tertiary);
}

.override-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
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

.action-btn:hover {
  background: var(--bg-hover);
  color: var(--color-primary);
}

.action-btn.delete:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Form Styles */
.override-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--color-error);
}

.form-input {
  padding: 12px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  font-family: var(--font-mono);
  transition: all 0.2s;
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.input-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.mode-selector {
  display: flex;
  gap: 12px;
}

.mode-selector .mode-option {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border: 2px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-selector .mode-option:hover {
  border-color: var(--color-primary);
}

.mode-selector .mode-option.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.mode-selector .mode-option input[type="radio"] {
  display: none;
}

.mode-selector .option-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.mode-selector .option-icon.disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.mode-selector .option-icon.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.mode-selector .option-icon.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.mode-selector .option-content {
  text-align: center;
}

.mode-selector .option-label {
  display: block;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
}

.mode-selector .option-desc {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

/* Remove Modal */
.remove-content {
  text-align: center;
  padding: 20px 0;
}

.remove-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: var(--color-warning-bg);
  color: var(--color-warning);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.remove-content h4 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.remove-content p {
  margin: 0;
  color: var(--text-secondary);
}

.remove-content code {
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
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

/* Responsive */
@media (max-width: 600px) {
  .section-header {
    flex-direction: column;
    gap: 16px;
  }

  .mode-selector {
    flex-direction: column;
  }
}
</style>
