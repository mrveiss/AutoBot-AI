<template>
  <div
    v-if="showDialog"
    class="host-selection-overlay"
    @click.self="!isProcessing && handleCancel()"
  >
    <div
      ref="dialogRef"
      class="host-selection-dialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="dialogTitleId"
      :aria-describedby="dialogDescId"
      tabindex="-1"
      @keydown="onFocusTrapKeydown"
    >
      <div class="dialog-header">
        <div class="dialog-icon" aria-hidden="true">
          <Icon name="server" size="md" />
        </div>
        <div class="dialog-title">
          <h3 :id="dialogTitleId">{{ t('ui.hostSelection.title') }}</h3>
          <p :id="dialogDescId" class="dialog-subtitle">{{ purpose || t('ui.hostSelection.defaultPurpose') }}</p>
        </div>
        <button
          v-if="!isProcessing"
          class="close-button"
          type="button"
          @click="handleCancel"
          :aria-label="t('ui.hostSelection.close')"
        >
          <Icon name="times" size="sm" />
        </button>
      </div>

      <div class="dialog-body">
        <!-- Command Preview -->
        <div v-if="command" class="command-preview">
          <h4>{{ t('ui.hostSelection.commandToExecute') }}:</h4>
          <div class="command-box">
            <code>{{ command }}</code>
          </div>
        </div>

        <!-- Host Selection -->
        <div class="host-selection-section">
          <h4 :id="hostListLabelId">{{ t('ui.hostSelection.availableHosts') }}</h4>

          <!-- Loading State -->
          <div v-if="loading" class="loading-state" role="status" aria-live="polite">
            <LoadingSpinner size="md" />
            <span>{{ t('ui.hostSelection.loadingHosts') }}</span>
          </div>

          <!-- No Hosts State -->
          <div v-else-if="hosts.length === 0" class="empty-state">
            <Icon name="exclamation-circle" size="md" />
            <span>{{ t('ui.hostSelection.noHostsConfigured') }}</span>
            <button type="button" @click="openSecretsManager" class="add-host-link">
              <Icon name="plus" size="sm" /> {{ t('ui.hostSelection.addHost') }}
            </button>
          </div>

          <!-- Host List -->
          <div
            v-else
            class="host-list"
            role="radiogroup"
            :aria-labelledby="hostListLabelId"
          >
            <div
              v-for="host in hosts"
              :key="host.id"
              class="host-card"
              :class="{
                selected: selectedHostId === host.id,
                'is-default': host.id === defaultHostId
              }"
              @click="selectHost(host)"
            >
              <div class="host-radio">
                <input
                  type="radio"
                  :id="'host-' + host.id"
                  :value="host.id"
                  v-model="selectedHostId"
                  :disabled="isProcessing"
                  :aria-label="host.name"
                />
              </div>
              <div class="host-icon" aria-hidden="true">
                <Icon :name="getHostIcon(host)" size="sm" />
              </div>
              <div class="host-info">
                <div class="host-name">
                  {{ host.name }}
                  <span v-if="host.id === defaultHostId" class="default-badge">
                    <Icon name="star" size="xs" /> {{ t('ui.hostSelection.default') }}
                  </span>
                </div>
                <div class="host-details">
                  <span class="host-connection">
                    <Icon name="user" size="xs" /> {{ host.username || 'root' }}@{{ host.host }}:{{ host.ssh_port || 22 }}
                  </span>
                  <span v-if="host.capabilities?.includes('vnc')" class="host-capability">
                    <Icon name="desktop" size="xs" /> VNC
                  </span>
                </div>
                <div v-if="host.purpose" class="host-purpose">
                  {{ host.purpose }}
                </div>
              </div>
              <div class="host-actions">
                <button
                  v-if="host.id !== defaultHostId"
                  type="button"
                  class="set-default-btn"
                  @click.stop="setAsDefault(host)"
                  :aria-label="t('ui.hostSelection.setAsDefault')"
                  :title="t('ui.hostSelection.setAsDefault')"
                  :disabled="isProcessing"
                >
                  <Icon name="star" size="sm" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Remember Choice Option -->
        <div class="options-section">
          <label class="checkbox-label">
            <input
              type="checkbox"
              v-model="rememberChoice"
              :disabled="isProcessing"
            />
            <span class="checkmark"></span>
            {{ t('ui.hostSelection.rememberChoice') }}
          </label>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="error-message" role="alert" aria-live="assertive">
          <Icon name="exclamation-triangle" size="sm" />
          <span>{{ error }}</span>
        </div>
      </div>

      <div class="dialog-footer">
        <div class="button-group">
          <button
            type="button"
            class="btn btn-secondary"
            @click="handleCancel"
            :disabled="isProcessing"
          >
            <Icon name="times" size="sm" />
            {{ t('ui.hostSelection.cancel') }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            @click="handleConfirm"
            :disabled="!selectedHostId || isProcessing"
            :aria-busy="isProcessing"
          >
            <LoadingSpinner v-if="isProcessing" size="sm" />
            <Icon v-else name="check" size="sm" />
            {{ isProcessing ? t('ui.hostSelection.connecting') : t('ui.hostSelection.connectAndExecute') }}
          </button>
        </div>

        <div class="security-note">
          <Icon name="lock" size="sm" />
          <span>{{ t('ui.hostSelection.securityNote') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, useId, toRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { secretsApiClient } from '@/utils/SecretsApiClient';
import { getBackendUrl } from '@/config/ssot-config';
import { fetchWithAuth } from '@/utils/fetchWithAuth';
import { createLogger } from '@/utils/debugUtils';
import Icon, { type IconName } from '@/components/ui/Icon.vue';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import { useFocusTrap } from '@/composables/useFocusTrap';
import { useFocusRestore } from '@/composables/useFocusRestore';
import { useInitialFocus } from '@/composables/useInitialFocus';
import { useBodyScrollLock } from '@/composables/useBodyScrollLock';

const logger = createLogger('HostSelectionDialog');
const { t } = useI18n();

// Types
interface InfrastructureHost {
  id: string;
  name: string;
  host: string;
  ssh_port?: number;
  username?: string;
  auth_type?: 'ssh_key' | 'password';
  capabilities?: string[];
  purpose?: string;
  os?: string;
  metadata?: Record<string, unknown>;
  _isLegacyHost?: boolean;
}

// Minimal shapes for raw secrets / legacy hosts returned by the backend APIs,
// mapped into InfrastructureHost in loadHosts().
interface RawSecretMetadata {
  host?: string;
  ssh_port?: number;
  username?: string;
  auth_type?: 'ssh_key' | 'password';
  capabilities?: string[];
  purpose?: string;
  os?: string;
}

interface RawSecret {
  id: string;
  name: string;
  type?: string;
  description?: string;
  metadata?: RawSecretMetadata;
}

interface RawLegacyHost {
  id: string;
  name: string;
  host: string;
  ssh_port?: number;
  username?: string;
  auth_type?: 'ssh_key' | 'password';
  capabilities?: string[];
  purpose?: string;
  description?: string;
  os?: string;
}

// Props
interface Props {
  show: boolean;
  command?: string;
  purpose?: string;
  requestId?: string;
  agentSessionId?: string;
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  command: '',
  purpose: '',
  requestId: '',
  agentSessionId: ''
});

// Emits
const emit = defineEmits<{
  'selected': [{ host: InfrastructureHost; rememberChoice: boolean }];
  'cancelled': [];
  'close': [];
}>();

// #1721: In-memory session host preference (avoids clear-text sessionStorage)
let _sessionHostChoice: string | null = null;

// Stable IDs for ARIA labeling (Vue 3.5+ useId)
const _uid = useId();
const dialogTitleId = `host-dialog-title-${_uid}`;
const dialogDescId = `host-dialog-desc-${_uid}`;
const hostListLabelId = `host-list-label-${_uid}`;

// Focus management
const dialogRef = ref<HTMLElement | null>(null);
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef);
useFocusRestore(toRef(props, 'show'));
useBodyScrollLock(toRef(props, 'show'));
const { focusFirst } = useInitialFocus(dialogRef);

// State
const showDialog = ref(false);
const hosts = ref<InfrastructureHost[]>([]);
const selectedHostId = ref<string | null>(null);
const defaultHostId = ref<string | null>(null);
const rememberChoice = ref(false);
const loading = ref(false);
const isProcessing = ref(false);
const error = ref<string | null>(null);

// Load hosts from secrets API
const loadHosts = async () => {
  loading.value = true;
  error.value = null;

  try {
    const backendUrl = getBackendUrl();

    // Fetch both secrets (infrastructure_host type) and legacy hosts
    const [secretsResponse, legacyHostsResponse] = await Promise.all([
      secretsApiClient.getSecrets({}) as Promise<{ secrets?: RawSecret[] }>,
      fetchWithAuth(`${backendUrl}/api/infrastructure/hosts`)
        .then(r => r.ok ? r.json() : { hosts: [] })
        .catch(() => ({ hosts: [] }))
    ]);

    // Filter to infrastructure_host type secrets
    const infraSecrets = (secretsResponse.secrets || [])
      .filter((s: RawSecret) => s.type === 'infrastructure_host')
      .map((s: RawSecret) => ({
        id: s.id,
        name: s.name,
        host: s.metadata?.host || '',
        ssh_port: s.metadata?.ssh_port || 22,
        username: s.metadata?.username || 'root',
        auth_type: s.metadata?.auth_type || 'password',
        capabilities: s.metadata?.capabilities || ['ssh'],
        purpose: s.metadata?.purpose || s.description,
        os: s.metadata?.os,
        metadata: s.metadata,
        _isLegacyHost: false
      }));

    // Convert legacy hosts
    const legacyHosts = (legacyHostsResponse.hosts || []).map((h: RawLegacyHost) => ({
      id: h.id,
      name: h.name,
      host: h.host,
      ssh_port: h.ssh_port || 22,
      username: h.username || 'root',
      auth_type: h.auth_type || 'password',
      capabilities: h.capabilities || ['ssh'],
      purpose: h.purpose || h.description,
      os: h.os,
      metadata: h,
      _isLegacyHost: true
    }));

    // Combine and deduplicate by host+port
    const hostMap = new Map<string, InfrastructureHost>();
    [...infraSecrets, ...legacyHosts].forEach(h => {
      const key = `${h.host}:${h.ssh_port}`;
      if (!hostMap.has(key)) {
        hostMap.set(key, h);
      }
    });

    hosts.value = Array.from(hostMap.values());

    // Load default host from localStorage
    const savedDefault = localStorage.getItem('autobot_default_ssh_host');
    if (savedDefault && hosts.value.some(h => h.id === savedDefault)) {
      defaultHostId.value = savedDefault;
      selectedHostId.value = savedDefault;
    } else if (hosts.value.length > 0) {
      // Auto-select first host if no default
      selectedHostId.value = hosts.value[0].id;
    }

    logger.info('Loaded infrastructure hosts:', { count: hosts.value.length });
  } catch (err) {
    logger.error('Failed to load hosts:', err);
    error.value = t('ui.hostSelection.failedToLoadHosts');
  } finally {
    loading.value = false;
  }
};

// Select a host
const selectHost = (host: InfrastructureHost) => {
  if (!isProcessing.value) {
    selectedHostId.value = host.id;
  }
};

// Set host as default
const setAsDefault = (host: InfrastructureHost) => {
  defaultHostId.value = host.id;
  // host.id is a non-secret UI preference (selected hostname), not a credential or token
  localStorage.setItem('autobot_default_ssh_host', host.id); // codeql[js/clear-text-storage-of-sensitive-data]
  logger.info('Set default host:', { hostId: host.id, hostName: host.name });
};

// Get host icon based on capabilities
const getHostIcon = (host: InfrastructureHost): IconName => {
  if (host.capabilities?.includes('vnc')) {
    return 'desktop';
  }
  return 'server';
};

// Open secrets manager to add new host
const openSecretsManager = () => {
  // Navigate to secrets page
  window.location.href = '/secrets';
};

// Handle confirm selection
const handleConfirm = async () => {
  if (!selectedHostId.value) {
    error.value = t('ui.hostSelection.pleaseSelectHost');
    return;
  }

  const selectedHost = hosts.value.find(h => h.id === selectedHostId.value);
  if (!selectedHost) {
    error.value = t('ui.hostSelection.hostNotFound');
    return;
  }

  isProcessing.value = true;
  error.value = null;

  try {
    // If remember choice is checked, save as session default
    // #1721: Use in-memory storage instead of sessionStorage for host IDs
    if (rememberChoice.value) {
      _sessionHostChoice = selectedHostId.value;
    }

    // Emit selection event with host data
    emit('selected', {
      host: selectedHost,
      rememberChoice: rememberChoice.value
    });

    closeDialog();
  } catch (err) {
    logger.error('Failed to confirm host selection:', err);
    error.value = t('ui.hostSelection.failedToConnect');
  } finally {
    isProcessing.value = false;
  }
};

// Handle cancel
const handleCancel = () => {
  emit('cancelled');
  closeDialog();
};

// Close dialog
const closeDialog = () => {
  showDialog.value = false;
  emit('close');
};

// Handle escape key
const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && showDialog.value && !isProcessing.value) {
    handleCancel();
  }
};

// Watchers — focus save/restore handled by useFocusRestore above,
// initial focus by useInitialFocus.
watch(() => props.show, async (newValue) => {
  showDialog.value = newValue;
  if (newValue) {
    loadHosts();
    await focusFirst();
  }
}, { immediate: true });

// Lifecycle
onMounted(() => {
  document.addEventListener('keydown', handleEscape);
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleEscape);
});
</script>

<style scoped>
/* Issue #704: Uses CSS design tokens */
.host-selection-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-maximum);
  backdrop-filter: blur(4px);
}

.host-selection-dialog {
  contain: layout style paint;
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2xl);
  width: 90vw;
  max-width: 600px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: slideIn var(--duration-300) var(--ease-out);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* Header */
.dialog-header {
  background: var(--color-primary);
  color: var(--text-on-primary);
  padding: var(--spacing-5);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.dialog-icon {
  font-size: var(--font-size-3xl);
  opacity: 0.9;
}

.dialog-title {
  flex: 1;
}

.dialog-title h3 {
  margin: 0 0 var(--spacing-1) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.dialog-subtitle {
  margin: var(--spacing-0);
  font-size: var(--font-size-sm);
  opacity: 0.9;
}

.close-button {
  background: transparent;
  border: none;
  color: var(--text-on-primary);
  font-size: var(--font-size-lg);
  cursor: pointer;
  padding: var(--spacing-2);
  border-radius: var(--radius-sm);
  opacity: 0.8;
  transition: opacity var(--duration-150);
}

.close-button:hover {
  opacity: 1;
}

.close-button:focus-visible {
  outline: 2px solid var(--text-on-primary);
  outline-offset: 2px;
}

/* Body */
.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

/* Command Preview */
.command-preview {
  margin-bottom: var(--spacing-5);
}

.command-preview h4 {
  margin: 0 0 var(--spacing-2) 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.command-box {
  background: var(--bg-inverse);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  overflow-x: auto;
}

.command-box code {
  color: var(--text-inverse);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  white-space: pre-wrap;
  word-break: break-all;
}

/* Host Selection Section */
.host-selection-section {
  margin-bottom: var(--spacing-5);
}

.host-selection-section h4 {
  margin: 0 0 var(--spacing-3) 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Loading & Empty States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  gap: var(--spacing-3);
}

.loading-state i,
.empty-state i {
  font-size: var(--font-size-2xl);
}

.add-host-link {
  background: none;
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-150);
}

.add-host-link:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

/* Host List */
.host-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  min-height: 200px; max-height: 50vh;
  overflow-y: auto;
}

.host-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150);
}

.host-card:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.host-card.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.host-card.is-default {
  border-color: var(--color-warning);
}

.host-card.selected.is-default {
  border-color: var(--color-primary);
}

.host-radio input {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.host-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--font-size-lg);
}

.host-card.selected .host-icon {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.host-info {
  flex: 1;
  min-width: 0;
}

.host-name {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  font-size: var(--font-size-base);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.default-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
}

.default-badge i {
  font-size: var(--text-xs);
}

.host-details {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-top: var(--spacing-1);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.host-connection,
.host-capability {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.host-capability {
  color: var(--color-info);
}

.host-purpose {
  margin-top: var(--spacing-1);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  font-style: italic;
}

.host-actions {
  display: flex;
  align-items: center;
}

.set-default-btn {
  background: transparent;
  border: 1px solid var(--border-secondary);
  color: var(--text-muted);
  min-width: 44px;
  min-height: 44px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-150);
}

.set-default-btn:hover {
  border-color: var(--color-warning);
  color: var(--color-warning);
  background: var(--color-warning-bg);
}

.set-default-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.set-default-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Options Section */
.options-section {
  margin-bottom: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.checkbox-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.checkbox-label input[type="checkbox"] {
  display: none;
}

.checkmark {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-secondary);
  border-radius: var(--radius-sm);
  margin-right: var(--spacing-2);
  position: relative;
  transition: all var(--duration-200);
}

.checkbox-label input[type="checkbox"]:checked + .checkmark {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.checkbox-label input[type="checkbox"]:checked + .checkmark::after {
  content: '\2713';
  position: absolute;
  top: -2px;
  left: 3px;
  color: var(--text-on-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

/* Error Message */
.error-message {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--color-error-dark);
  font-size: var(--font-size-sm);
}

/* Footer */
.dialog-footer {
  background: var(--bg-secondary);
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.button-group {
  display: flex;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-3);
}

.btn {
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-150);
  border: none;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.security-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  color: var(--text-muted);
  font-size: var(--font-size-xs);
}

/* Responsive */
@media (max-width: 640px) {
  .host-selection-dialog {
  contain: layout style paint;
    width: 95vw;
    max-height: 90vh;
  }

  .dialog-header {
    padding: var(--spacing-4);
  }

  .dialog-body {
    padding: var(--spacing-4);
  }

  .host-list {
    max-height: 250px;
  }

  .button-group {
    flex-direction: column;
  }

  .host-details {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-1);
  }
}
</style>
