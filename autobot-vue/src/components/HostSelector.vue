<template>
  <div class="host-selector">
    <!-- Collapsed state - shows current selection -->
    <div
      v-if="!expanded"
      class="host-selector-collapsed"
      @click="toggleExpanded"
    >
      <div class="selected-host" v-if="selectedHost">
        <i :class="getHostIcon(selectedHost)"></i>
        <span class="host-name">{{ selectedHost.name }}</span>
        <span class="host-address">{{ selectedHost.host }}</span>
        <span class="connection-status" :class="connectionStatus">
          <i :class="getStatusIcon()"></i>
        </span>
      </div>
      <div class="no-host-selected" v-else>
        <i class="fas fa-server"></i>
        <span>Select Host</span>
      </div>
      <i class="fas fa-chevron-down expand-icon"></i>
    </div>

    <!-- Expanded state - shows host list -->
    <div v-else class="host-selector-expanded">
      <div class="selector-header">
        <h4>Infrastructure Hosts</h4>
        <button class="btn-close" @click="toggleExpanded">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <!-- Filter by capability -->
      <div class="capability-filter" v-if="showCapabilityFilter">
        <button
          class="filter-btn"
          :class="{ active: capabilityFilter === 'ssh' }"
          @click="setCapabilityFilter('ssh')"
        >
          <i class="fas fa-terminal"></i> SSH
        </button>
        <button
          class="filter-btn"
          :class="{ active: capabilityFilter === 'vnc' }"
          @click="setCapabilityFilter('vnc')"
        >
          <i class="fas fa-desktop"></i> VNC
        </button>
        <button
          class="filter-btn"
          :class="{ active: !capabilityFilter }"
          @click="setCapabilityFilter(null)"
        >
          All
        </button>
      </div>

      <!-- Host list -->
      <div class="host-list" v-if="!loading">
        <div
          v-for="host in filteredHosts"
          :key="host.id"
          class="host-item"
          :class="{ selected: selectedHost?.id === host.id }"
          @click="selectHost(host)"
        >
          <div class="host-icon" :style="{ background: getHostColor(host) }">
            <i :class="getHostIcon(host)"></i>
          </div>
          <div class="host-info">
            <span class="host-name">{{ host.name }}</span>
            <span class="host-details">
              {{ host.host }}:{{ host.ssh_port }}
              <span v-if="host.os" class="host-os">• {{ host.os }}</span>
            </span>
          </div>
          <div class="host-capabilities">
            <span
              v-for="cap in host.capabilities"
              :key="cap"
              class="capability-badge"
              :class="cap"
            >
              {{ cap.toUpperCase() }}
            </span>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="filteredHosts.length === 0" class="empty-state">
          <i class="fas fa-server"></i>
          <p v-if="hosts.length === 0">
            No hosts configured. Add hosts in Secrets Management.
          </p>
          <p v-else>
            No hosts match the current filter.
          </p>
        </div>
      </div>

      <!-- Loading state -->
      <div v-else class="loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <span>Loading hosts...</span>
      </div>

      <!-- Actions -->
      <div class="selector-actions">
        <button class="btn-secondary" @click="refreshHosts">
          <i class="fas fa-sync-alt"></i> Refresh
        </button>
        <button class="btn-primary" @click="openSecretsManager">
          <i class="fas fa-plus"></i> Add Host
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { getBackendUrl } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('HostSelector');

/**
 * Infrastructure host type for SSH/VNC connections.
 * Issue #715: Dynamic host management via secrets.
 */
interface InfrastructureHost {
  id: string;
  name: string;
  host: string;
  ssh_port?: number;
  vnc_port?: number;
  username?: string;
  os?: string;
  capabilities?: string[];
  description?: string;
  tags?: string[];
}

// Props
const props = defineProps<{
  chatId?: string;
  requiredCapability?: 'ssh' | 'vnc';
  modelValue?: InfrastructureHost | null;
}>();

// Emits
const emit = defineEmits<{
  (e: 'update:modelValue', host: InfrastructureHost): void;
  (e: 'host-selected', host: InfrastructureHost): void;
  (e: 'open-secrets-manager'): void;
}>();

// State
const expanded = ref(false);
const loading = ref(false);
const hosts = ref<InfrastructureHost[]>([]);
const selectedHost = ref<InfrastructureHost | null>(null);
const connectionStatus = ref<'disconnected' | 'connecting' | 'connected'>('disconnected');
const capabilityFilter = ref<string | null>(null);

// Computed
const showCapabilityFilter = computed(() => !props.requiredCapability);

const filteredHosts = computed(() => {
  let filtered = hosts.value;

  // Filter by required capability
  if (props.requiredCapability) {
    filtered = filtered.filter(h =>
      h.capabilities?.includes(props.requiredCapability)
    );
  }

  // Filter by user-selected capability
  if (capabilityFilter.value) {
    filtered = filtered.filter(h =>
      h.capabilities?.includes(capabilityFilter.value)
    );
  }

  return filtered;
});

// Methods
const toggleExpanded = () => {
  expanded.value = !expanded.value;
  if (expanded.value && hosts.value.length === 0) {
    loadHosts();
  }
};

const loadHosts = async () => {
  loading.value = true;
  try {
    const backendUrl = getBackendUrl();
    const params = new URLSearchParams();

    if (props.requiredCapability) {
      params.append('capability', props.requiredCapability);
    }
    if (props.chatId) {
      params.append('chat_id', props.chatId);
    }

    const response = await fetch(
      `${backendUrl}/api/infrastructure/hosts?${params.toString()}`
    );

    if (!response.ok) {
      throw new Error(`Failed to load hosts: ${response.statusText}`);
    }

    const data = await response.json();
    hosts.value = data.hosts || [];

    logger.info(`Loaded ${hosts.value.length} infrastructure hosts`);
  } catch (error) {
    logger.error('Failed to load hosts:', error);
    hosts.value = [];
  } finally {
    loading.value = false;
  }
};

const refreshHosts = () => {
  loadHosts();
};

const selectHost = (host: InfrastructureHost) => {
  selectedHost.value = host;
  connectionStatus.value = 'disconnected';
  expanded.value = false;
  emit('update:modelValue', host);
  emit('host-selected', host);
  logger.info(`Selected host: ${host.name} (${host.host})`);
};

const setCapabilityFilter = (cap: string | null) => {
  capabilityFilter.value = cap;
};

const openSecretsManager = () => {
  emit('open-secrets-manager');
};

const getHostIcon = (host: InfrastructureHost) => {
  if (host.capabilities?.includes('vnc')) {
    return 'fas fa-desktop';
  }
  return 'fas fa-terminal';
};

const getHostColor = (host: InfrastructureHost) => {
  // Generate consistent color based on host name
  const colors = [
    '#3498db', '#2ecc71', '#9b59b6', '#e67e22',
    '#1abc9c', '#e74c3c', '#34495e', '#f39c12'
  ];
  const hash = host.name.split('').reduce(
    (acc: number, char: string) => acc + char.charCodeAt(0), 0
  );
  return colors[hash % colors.length];
};

const getStatusIcon = () => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'fas fa-check-circle';
    case 'connecting':
      return 'fas fa-spinner fa-spin';
    default:
      return 'fas fa-circle';
  }
};

// Update connection status from parent
const updateConnectionStatus = (status: 'disconnected' | 'connecting' | 'connected') => {
  connectionStatus.value = status;
};

// Watch for model value changes
watch(() => props.modelValue, (newValue) => {
  if (newValue && newValue.id !== selectedHost.value?.id) {
    selectedHost.value = newValue;
  }
});

// Initialize required capability filter
watch(() => props.requiredCapability, (cap) => {
  if (cap) {
    capabilityFilter.value = cap;
  }
}, { immediate: true });

// Load hosts on mount
onMounted(() => {
  loadHosts();
});

// Expose methods for parent components
defineExpose({
  updateConnectionStatus,
  refreshHosts,
  selectedHost,
});
</script>

<style scoped>
.host-selector {
  position: relative;
  min-width: 200px;
}

.host-selector-collapsed {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.host-selector-collapsed:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.selected-host {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.selected-host i {
  color: var(--color-primary);
}

.selected-host .host-name {
  font-weight: 500;
  color: var(--text-primary);
}

.selected-host .host-address {
  font-size: 12px;
  color: var(--text-tertiary);
}

.connection-status {
  margin-left: auto;
}

.connection-status.disconnected i {
  color: var(--text-muted);
}

.connection-status.connecting i {
  color: var(--color-warning);
}

.connection-status.connected i {
  color: var(--color-success);
}

.no-host-selected {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  color: var(--text-muted);
}

.expand-icon {
  color: var(--text-muted);
  font-size: 12px;
  transition: transform 0.2s;
}

.host-selector-collapsed:hover .expand-icon {
  color: var(--text-secondary);
}

.host-selector-expanded {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  min-width: 320px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  z-index: 100;
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
}

.selector-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: var(--text-muted);
}

.btn-close:hover {
  color: var(--text-primary);
}

.capability-filter {
  display: flex;
  gap: 4px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-default);
}

.filter-btn {
  flex: 1;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.filter-btn:hover {
  background: var(--bg-hover);
}

.filter-btn.active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.host-list {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
}

.host-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.host-item:hover {
  background: var(--bg-hover);
}

.host-item.selected {
  background: var(--color-primary-bg);
}

.host-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.host-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.host-info .host-name {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.host-details {
  font-size: 12px;
  color: var(--text-tertiary);
}

.host-os {
  color: var(--text-muted);
}

.host-capabilities {
  display: flex;
  gap: 4px;
}

.capability-badge {
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
  text-transform: uppercase;
}

.capability-badge.ssh {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.capability-badge.vnc {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.empty-state,
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--text-muted);
}

.empty-state i,
.loading-state i {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-state p {
  margin: 0;
  font-size: 13px;
}

.selector-actions {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
}

.btn-secondary,
.btn-primary {
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.15s;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}
</style>
