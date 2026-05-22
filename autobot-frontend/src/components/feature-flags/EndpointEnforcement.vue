<template>
  <div class="endpoint-enforcement">
    <div class="section-header">
      <div class="header-info">
        <h3><Icon name="sitemap" /> {{ $t('featureFlags.enforcement.title') }}</h3>
        <p class="description">
          {{ $t('featureFlags.enforcement.description') }}
        </p>
      </div>
      <button @click="showAddModal = true" class="btn-add">
        <Icon name="plus" /> {{ $t('featureFlags.enforcement.addOverride') }}
      </button>
    </div>

    <!-- Empty State -->
    <div v-if="Object.keys(overrides).length === 0" class="empty-state">
      <div class="empty-icon">
        <Icon name="sitemap" />
      </div>
      <h4>{{ $t('featureFlags.enforcement.noOverrides') }}</h4>
      <p>{{ $t('featureFlags.enforcement.noOverridesDesc') }}</p>
      <button @click="showAddModal = true" class="btn-primary">
        <Icon name="plus" /> {{ $t('featureFlags.enforcement.addOverride') }}
      </button>
    </div>

    <!-- Overrides List -->
    <div v-else class="overrides-list">
      <div class="global-mode-banner">
        <Icon name="globe" />
        <span>{{ $t('featureFlags.enforcement.globalMode') }} <strong>{{ globalModeLabel }}</strong></span>
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
              <Icon :name="getModeIcon(mode)" />
              {{ getModeLabel(mode) }}
            </span>
            <span class="vs-global" v-if="mode !== globalMode">
              ({{ t('featureFlags.enforcement.override') }})
            </span>
          </div>
        </div>
        <div class="override-actions">
          <button
            @click="editOverride(endpoint, mode)"
            class="action-btn"
            :title="t('featureFlags.enforcement.edit')"
          >
            <Icon name="edit" />
          </button>
          <button
            @click="confirmRemove(endpoint)"
            class="action-btn delete"
            :title="t('featureFlags.enforcement.removeLabel')"
          >
            <Icon name="trash" />
          </button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <BaseModal
      v-model="showAddModal"
      :title="editingEndpoint ? $t('featureFlags.enforcement.editOverride') : $t('featureFlags.enforcement.addEndpointOverride')"
      size="md"
    >
      <form @submit.prevent="saveOverride" class="override-form">
        <div class="form-group">
          <label>{{ $t('featureFlags.enforcement.endpointPath') }} <span class="required">*</span></label>
          <input
            type="text"
            v-model="form.endpoint"
            :disabled="!!editingEndpoint"
            required
            :placeholder="$t('featureFlags.enforcement.endpointPlaceholder')"
            class="form-input"
          />
          <small class="input-hint">{{ t('featureFlags.enforcement.endpointHint') }}</small>
        </div>

        <div class="form-group">
          <label>{{ $t('featureFlags.enforcement.mode') }} <span class="required">*</span></label>
          <div class="mode-selector">
            <label
              v-for="option in modeOptions"
              :key="option.value"
              class="mode-option"
              :class="{ active: form.mode === option.value }"
            >
              <input type="radio" v-model="form.mode" :value="option.value" />
              <div class="option-icon" :class="option.value">
                <Icon :name="option.icon" />
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
        <button type="button" @click="closeModal" class="btn-secondary">{{ $t('featureFlags.enforcement.cancel') }}</button>
        <button
          type="submit"
          @click="saveOverride"
          class="btn-primary"
          :disabled="!isFormValid || loading"
        >
          <Icon name="spinner" class="animate-spin" v-if="loading" />
          {{ $t('featureFlags.enforcement.save') }}
        </button>
      </template>
    </BaseModal>

    <!-- Remove Confirmation Modal -->
    <BaseModal
      v-model="showRemoveModal"
      :title="$t('featureFlags.enforcement.removeOverride')"
      size="sm"
    >
      <div class="remove-content">
        <div class="remove-icon">
          <Icon name="undo" />
        </div>
        <h4>{{ t('featureFlags.enforcement.revertTitle') }}</h4>
        <p>
          {{ t('featureFlags.enforcement.revertDescription', { endpoint: removingEndpoint }) }}
        </p>
      </div>

      <template #actions>
        <button @click="showRemoveModal = false" class="btn-secondary">{{ $t('featureFlags.enforcement.cancel') }}</button>
        <button @click="removeOverride" class="btn-primary" :disabled="loading">
          <Icon name="spinner" class="animate-spin" v-if="loading" />
          {{ $t('featureFlags.enforcement.remove') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, reactive } from 'vue';
import { useI18n } from 'vue-i18n';
import type { EnforcementMode } from '@/utils/FeatureFlagsApiClient';
import BaseModal from '@/components/ui/BaseModal.vue';

const { t } = useI18n();

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
const modeOptions = computed(() => [
  {
    value: 'disabled' as EnforcementMode,
    label: t('featureFlags.enforcement.modeDisabled'),
    icon: 'ban',
    shortDesc: t('featureFlags.enforcement.modeDisabledDesc'),
  },
  {
    value: 'log_only' as EnforcementMode,
    label: t('featureFlags.enforcement.modeLogOnly'),
    icon: 'clipboard-list',
    shortDesc: t('featureFlags.enforcement.modeLogOnlyDesc'),
  },
  {
    value: 'enforced' as EnforcementMode,
    label: t('featureFlags.enforcement.modeEnforced'),
    icon: 'shield-alt',
    shortDesc: t('featureFlags.enforcement.modeEnforcedDesc'),
  },
]);

// Computed
const globalModeLabel = computed(() => getModeLabel(props.globalMode));

const isFormValid = computed(() => {
  return form.endpoint.trim() !== '' && form.mode;
});

// Methods
const getModeLabel = (mode: EnforcementMode) => {
  const labels: Record<EnforcementMode, string> = {
    disabled: t('featureFlags.enforcement.modeDisabled'),
    log_only: t('featureFlags.enforcement.modeLogOnly'),
    enforced: t('featureFlags.enforcement.modeEnforced'),
  };
  return labels[mode] || mode;
};

const getModeIcon = (mode: EnforcementMode) => {
  const icons: Record<EnforcementMode, string> = {
    disabled: 'ban',
    log_only: 'clipboard-list',
    enforced: 'shield-alt',
  };
  return icons[mode] || 'question';
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
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-5);
}

.header-info h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-info h3 i {
  color: var(--color-primary);
}

.header-info .description {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  max-width: 500px;
}

.btn-add {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-add:hover {
  background: var(--color-primary-hover);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: var(--spacing-10) var(--spacing-5);
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
  font-size: var(--text-2xl);
}

.empty-state h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-5);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Overrides List */
.overrides-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.global-mode-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.global-mode-banner i {
  color: var(--color-primary);
}

.override-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  transition: all var(--duration-150);
}

.override-item:hover {
  border-color: var(--color-primary);
}

.override-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.endpoint-path code {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
}

.override-mode {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.mode-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
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
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.override-actions {
  display: flex;
  gap: var(--spacing-2);
}

.action-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: var(--radius-lg);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-150);
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
  gap: var(--spacing-5);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.form-group label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--color-error);
}

.form-input {
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  transition: all var(--duration-200);
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}
.form-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.input-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.mode-selector {
  display: flex;
  gap: var(--spacing-3);
}

.mode-selector .mode-option {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--duration-200);
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
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-base);
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
  font-size: var(--text-sm);
}

.mode-selector .option-desc {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-1);
}

/* Remove Modal */
.remove-content {
  text-align: center;
  padding: var(--spacing-5) var(--spacing-0);
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
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.remove-content p {
  margin: var(--spacing-0);
  color: var(--text-secondary);
}

.remove-content code {
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
}

/* Buttons */
.btn-primary {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

/* Responsive */
@media (max-width: 600px) {
  .section-header {
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .mode-selector {
    flex-direction: column;
  }
}
</style>
