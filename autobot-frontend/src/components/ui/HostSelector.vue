<template>
  <div class="host-selector">
    <!-- Collapsed state - shows current selection -->
    <button
      v-if="!expanded"
      type="button"
      class="host-selector-collapsed"
      :aria-expanded="expanded"
      @click="toggleExpanded"
    >
      <div class="selected-host" v-if="selectedHost">
        <Icon :name="getHostIcon(selectedHost)" size="sm" />
        <span class="host-name">{{ selectedHost.name }}</span>
        <span class="host-address">{{ selectedHost.host }}</span>
        <span class="connection-status" :class="connectionStatus">
          <Icon :name="getStatusIcon().name" :spin="getStatusIcon().spin" size="sm" />
        </span>
      </div>
      <div class="no-host-selected" v-else>
        <Icon name="server" size="sm" />
        <span>{{ t('ui.hostSelector.selectHost') }}</span>
      </div>
      <Icon name="chevron-down" size="sm" class="expand-icon" />
    </button>

    <!-- Expanded state - shows host list -->
    <div v-else class="host-selector-expanded">
      <div class="selector-header">
        <h4>{{ t('ui.hostSelector.infrastructureHosts') }}</h4>
        <button class="btn-close" @click="toggleExpanded" :aria-label="t('ui.modal.closeDialog')">
          <Icon name="times" size="sm" />
        </button>
      </div>

      <!-- Filter by capability -->
      <div class="capability-filter" v-if="showCapabilityFilter">
        <button
          class="filter-btn"
          :class="{ active: capabilityFilter === 'ssh' }"
          @click="setCapabilityFilter('ssh')"
        >
          <Icon name="terminal" size="sm" /> SSH
        </button>
        <button
          class="filter-btn"
          :class="{ active: capabilityFilter === 'vnc' }"
          @click="setCapabilityFilter('vnc')"
        >
          <Icon name="desktop" size="sm" /> VNC
        </button>
        <button
          class="filter-btn"
          :class="{ active: !capabilityFilter }"
          @click="setCapabilityFilter(null)"
        >
          {{ t('ui.hostSelector.all') }}
        </button>
      </div>

      <!-- Host list -->
      <div class="host-list" v-if="!loading">
        <button
          v-for="host in filteredHosts"
          :key="host.id"
          type="button"
          class="host-item"
          :class="{ selected: selectedHost?.id === host.id }"
          @click="selectHost(host)"
        >
          <div class="host-icon" :style="{ background: getHostColor(host) }">
            <Icon :name="getHostIcon(host)" size="sm" />
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
        </button>

        <!-- Empty state -->
        <div v-if="filteredHosts.length === 0" class="empty-state">
          <Icon name="server" size="lg" />
          <p v-if="hosts.length === 0">
            {{ t('ui.hostSelector.noHostsConfigured') }}
          </p>
          <p v-else>
            {{ t('ui.hostSelector.noHostsMatchFilter') }}
          </p>
        </div>
      </div>

      <!-- Loading state -->
      <div v-else class="loading-state" role="status" aria-live="polite">
        <LoadingSpinner size="md" />
        <span>{{ t('ui.hostSelector.loadingHosts') }}</span>
      </div>

      <!-- Actions -->
      <div class="selector-actions">
        <button class="btn-secondary" @click="refreshHosts">
          <Icon name="sync-alt" size="sm" /> {{ t('ui.hostSelector.refresh') }}
        </button>
        <button class="btn-primary" @click="openSecretsManager">
          <Icon name="plus" size="sm" /> {{ t('ui.hostSelector.addHost') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { useHostSelector } from '@/composables/useHostSelector'
import type { SelectorHost as InfrastructureHost } from '@/composables/useHostSelector'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'

const logger = createLogger('HostSelector');
const { t } = useI18n();

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

// Composable
const { hosts, loading, loadHosts } = useHostSelector({
  requiredCapability: props.requiredCapability,
  chatId: props.chatId,
});

// State
const expanded = ref(false);
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
      h.capabilities?.includes(props.requiredCapability!)
    );
  }

  // Filter by user-selected capability
  if (capabilityFilter.value) {
    filtered = filtered.filter(h =>
      h.capabilities?.includes(capabilityFilter.value!)
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

const getHostIcon = (host: InfrastructureHost): IconName => {
  if (host.capabilities?.includes('vnc')) {
    return 'desktop';
  }
  return 'terminal';
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

const getStatusIcon = (): { name: IconName; spin: boolean } => {
  switch (connectionStatus.value) {
    case 'connected':
      return { name: 'check-circle', spin: false };
    case 'connecting':
      return { name: 'sync-alt', spin: true };
    default:
      return { name: 'circle', spin: false };
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
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-150);
  appearance: none;
  font-family: inherit;
  font-size: inherit;
  text-align: left;
  width: 100%;
}

.host-selector-collapsed:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.selected-host {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
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
  font-size: var(--text-xs);
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
  gap: var(--spacing-2);
  flex: 1;
  color: var(--text-muted);
}

.expand-icon {
  color: var(--text-muted);
  font-size: var(--text-xs);
  transition: transform var(--duration-200);
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
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-popover);
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.selector-header h4 {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  padding: var(--spacing-1);
  cursor: pointer;
  color: var(--text-muted);
  min-width: 44px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-close:hover {
  color: var(--text-primary);
}

.capability-filter {
  display: flex;
  gap: var(--spacing-1);
  padding: var(--spacing-2) var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.filter-btn {
  flex: 1;
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-150);
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
  min-height: 200px; max-height: 50vh;
  overflow-y: auto;
  padding: var(--spacing-2);
}

.host-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150);
  appearance: none;
  background: none;
  border: none;
  width: 100%;
  text-align: left;
  font-family: inherit;
  font-size: inherit;
  color: inherit;
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
  border-radius: var(--radius-lg);
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
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.host-os {
  color: var(--text-muted);
}

.host-capabilities {
  display: flex;
  gap: var(--spacing-1);
}

.capability-badge {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  font-size: var(--text-xs);
  font-weight: 600;
  border-radius: var(--radius-default);
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
  padding: var(--spacing-8) var(--spacing-4);
  text-align: center;
  color: var(--text-muted);
}

.empty-state i,
.loading-state i {
  font-size: 32px;
  margin-bottom: var(--spacing-3);
  opacity: 0.5;
}

.empty-state p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
}

.selector-actions {
  display: flex;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.btn-secondary,
.btn-primary {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
  transition: all var(--duration-150);
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
