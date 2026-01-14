<template>
  <div class="infrastructure-settings">
    <!-- Sub-tabs for Infrastructure -->
    <div class="infrastructure-tabs">
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'nodes' }"
        @click="activeSubTab = 'nodes'"
      >
        <i class="fas fa-server mr-2"></i>
        Host Management
      </button>
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'npu-workers' }"
        @click="activeSubTab = 'npu-workers'"
      >
        <i class="fas fa-microchip mr-2"></i>
        NPU Workers
      </button>
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'data-storage' }"
        @click="activeSubTab = 'data-storage'"
      >
        <i class="fas fa-database mr-2"></i>
        Data Storage
      </button>
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'hardware' }"
        @click="activeSubTab = 'hardware'"
      >
        <i class="fas fa-server mr-2"></i>
        Hardware
      </button>
      <button
        class="infrastructure-tab"
        :class="{ active: activeSubTab === 'services' }"
        @click="activeSubTab = 'services'"
      >
        <i class="fas fa-cogs mr-2"></i>
        Services
      </button>
    </div>

    <!-- Host Management Tab (Issue #695) - System Updates merged here -->
    <div v-show="activeSubTab === 'nodes'">
      <NodesSettings :isSettingsLoaded="isSettingsLoaded" @change="$emit('change')" />
    </div>

    <!-- NPU Workers Tab -->
    <div v-show="activeSubTab === 'npu-workers'">
      <NPUWorkersSettings :isSettingsLoaded="isSettingsLoaded" @change="$emit('change')" />
    </div>

    <!-- Data Storage Tab -->
    <div v-show="activeSubTab === 'data-storage'">
      <DataStorageSettings />
    </div>

    <!-- Hardware Tab -->
    <div v-show="activeSubTab === 'hardware'">
      <HardwareSettings :isSettingsLoaded="isSettingsLoaded" @change="$emit('change')" />
    </div>

    <!-- Services Tab -->
    <div v-show="activeSubTab === 'services'">
      <ServicesSettings :isSettingsLoaded="isSettingsLoaded" @change="$emit('change')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '../../stores/useUserStore'
import NPUWorkersSettings from './NPUWorkersSettings.vue'
import DataStorageSettings from './DataStorageSettings.vue'
import HardwareSettings from './HardwareSettings.vue'
import ServicesSettings from './ServicesSettings.vue'
import NodesSettings from './NodesSettings.vue'

const userStore = useUserStore()

// Sub-tab state - default to nodes (Host Management)
const activeSubTab = ref<'nodes' | 'npu-workers' | 'data-storage' | 'hardware' | 'services'>('nodes')

// Props
interface Props {
  isSettingsLoaded?: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'setting-changed': [key: string, value: any]
  'change': []
}>()

onMounted(async () => {
  // Check auth from backend first (handles single_user mode auto-auth)
  if (!userStore.isAuthenticated) {
    await userStore.checkAuthFromBackend()
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
/* Issue #695: System Updates merged into Host Management (NodesSettings) */
.infrastructure-settings {
  padding: 24px;
}

/* Infrastructure Sub-tabs */
.infrastructure-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 2px solid var(--border-light);
  padding-bottom: 0;
  flex-wrap: wrap;
}

.infrastructure-tab {
  padding: 12px 20px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  display: flex;
  align-items: center;
}

.infrastructure-tab:hover {
  color: var(--text-primary);
  background: var(--bg-secondary);
}

.infrastructure-tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  background: transparent;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .infrastructure-settings {
    padding: 16px;
  }

  .infrastructure-tabs {
    gap: 4px;
  }

  .infrastructure-tab {
    padding: 10px 14px;
    font-size: 13px;
  }
}
</style>
