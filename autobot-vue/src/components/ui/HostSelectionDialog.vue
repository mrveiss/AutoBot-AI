<template>
  <div v-if="showDialog" class="host-selection-overlay">
    <div class="host-selection-dialog">
      <div class="dialog-header">
        <div class="dialog-icon">
          <i class="fas fa-server"></i>
        </div>
        <div class="dialog-title">
          <h3>Select Host for SSH Action</h3>
          <p class="dialog-subtitle">{{ purpose || 'Choose a host to execute the command' }}</p>
        </div>
        <button
          v-if="!isProcessing"
          class="close-button"
          @click="handleCancel"
          aria-label="Close"
        >
          <i class="fas fa-times"></i>
        </button>
      </div>

      <div class="dialog-body">
        <!-- Command Preview -->
        <div v-if="command" class="command-preview">
          <h4>Command to Execute:</h4>
          <div class="command-box">
            <code>{{ command }}</code>
          </div>
        </div>

        <!-- Host Selection -->
        <div class="host-selection-section">
          <h4>Available Hosts:</h4>

          <!-- Loading State -->
          <div v-if="loading" class="loading-state">
            <i class="fas fa-spinner fa-spin"></i>
            <span>Loading hosts...</span>
          </div>

          <!-- No Hosts State -->
          <div v-else-if="hosts.length === 0" class="empty-state">
            <i class="fas fa-exclamation-circle"></i>
            <span>No infrastructure hosts configured.</span>
            <button @click="openSecretsManager" class="add-host-link">
              <i class="fas fa-plus"></i> Add a host
            </button>
          </div>

          <!-- Host List -->
          <div v-else class="host-list">
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
                />
              </div>
              <div class="host-icon">
                <i :class="getHostIcon(host)"></i>
              </div>
              <div class="host-info">
                <div class="host-name">
                  {{ host.name }}
                  <span v-if="host.id === defaultHostId" class="default-badge">
                    <i class="fas fa-star"></i> Default
                  </span>
                </div>
                <div class="host-details">
                  <span class="host-connection">
                    <i class="fas fa-user"></i> {{ host.username || 'root' }}@{{ host.host }}:{{ host.ssh_port || 22 }}
                  </span>
                  <span v-if="host.capabilities?.includes('vnc')" class="host-capability">
                    <i class="fas fa-desktop"></i> VNC
                  </span>
                </div>
                <div v-if="host.purpose" class="host-purpose">
                  {{ host.purpose }}
                </div>
              </div>
              <div class="host-actions">
                <button
                  v-if="host.id !== defaultHostId"
                  class="set-default-btn"
                  @click.stop="setAsDefault(host)"
                  title="Set as default"
                  :disabled="isProcessing"
                >
                  <i class="fas fa-star"></i>
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
            Use this host for all SSH commands this session
          </label>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="error-message">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ error }}</span>
        </div>
      </div>

      <div class="dialog-footer">
        <div class="button-group">
          <button
            class="btn btn-secondary"
            @click="handleCancel"
            :disabled="isProcessing"
          >
            <i class="fas fa-times"></i>
            Cancel
          </button>
          <button
            class="btn btn-primary"
            @click="handleConfirm"
            :disabled="!selectedHostId || isProcessing"
          >
            <i v-if="isProcessing" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-check"></i>
            {{ isProcessing ? 'Connecting...' : 'Connect & Execute' }}
          </button>
        </div>

        <div class="security-note">
          <i class="fas fa-lock"></i>
          <span>Connection credentials are encrypted and never exposed.</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { secretsApiClient } from '@/utils/SecretsApiClient';
import { getBackendUrl } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('HostSelectionDialog');

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
  metadata?: Record<string, any>;
  _isLegacyHost?: boolean;
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
      secretsApiClient.getSecrets({}),
      fetch(`${backendUrl}/api/infrastructure/hosts`)
        .then(r => r.ok ? r.json() : { hosts: [] })
        .catch(() => ({ hosts: [] }))
    ]);

    // Filter to infrastructure_host type secrets
    const infraSecrets = (secretsResponse.secrets || [])
      .filter((s: any) => s.type === 'infrastructure_host')
      .map((s: any) => ({
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
    const legacyHosts = (legacyHostsResponse.hosts || []).map((h: any) => ({
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
    error.value = 'Failed to load infrastructure hosts';
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
  localStorage.setItem('autobot_default_ssh_host', host.id);
  logger.info('Set default host:', { hostId: host.id, hostName: host.name });
};

// Get host icon based on capabilities
const getHostIcon = (host: InfrastructureHost): string => {
  if (host.capabilities?.includes('vnc')) {
    return 'fas fa-desktop';
  }
  return 'fas fa-server';
};

// Open secrets manager to add new host
const openSecretsManager = () => {
  // Navigate to secrets page
  window.location.href = '/secrets';
};

// Handle confirm selection
const handleConfirm = async () => {
  if (!selectedHostId.value) {
    error.value = 'Please select a host';
    return;
  }

  const selectedHost = hosts.value.find(h => h.id === selectedHostId.value);
  if (!selectedHost) {
    error.value = 'Selected host not found';
    return;
  }

  isProcessing.value = true;
  error.value = null;

  try {
    // If remember choice is checked, save as session default
    if (rememberChoice.value) {
      sessionStorage.setItem('autobot_session_ssh_host', selectedHostId.value);
    }

    // Emit selection event with host data
    emit('selected', {
      host: selectedHost,
      rememberChoice: rememberChoice.value
    });

    closeDialog();
  } catch (err) {
    logger.error('Failed to confirm host selection:', err);
    error.value = 'Failed to connect to host';
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

// Watchers
watch(() => props.show, (newValue) => {
  showDialog.value = newValue;
  if (newValue) {
    loadHosts();
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
  z-index: 10000;
  backdrop-filter: blur(4px);
}

.host-selection-dialog {
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
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
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
  margin: 0;
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
  max-height: 300px;
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
  font-size: 10px;
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
  width: 32px;
  height: 32px;
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
