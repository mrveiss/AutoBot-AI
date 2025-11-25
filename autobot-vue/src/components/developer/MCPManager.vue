<template>
  <div class="mcp-manager">
    <!-- Header -->
    <div class="header-section mb-6">
      <h2 class="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-3">
        <i class="fas fa-plug text-blue-600"></i>
        MCP Tool Registry
      </h2>
      <p class="text-sm text-gray-600 dark:text-gray-400 mt-2">
        Manage and monitor AutoBot's Model Context Protocol (MCP) tools and bridges
      </p>
    </div>

    <!-- Overview Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <!-- Total Tools Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-blue-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Total MCP Tools</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">{{ stats.total_tools || 0 }}</p>
            <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">Across {{ stats.total_bridges || 0 }} bridges</p>
          </div>
          <i class="fas fa-toolbox text-3xl text-blue-500"></i>
        </div>
      </div>

      <!-- Healthy Bridges Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-green-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Healthy Bridges</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">
              {{ stats.healthy_bridges || 0 }}/{{ stats.total_bridges || 0 }}
            </p>
            <p class="mt-1 text-sm" :class="bridgeHealthClass">
              {{ bridgeHealthText }}
            </p>
          </div>
          <i class="fas fa-heartbeat text-3xl text-green-500"></i>
        </div>
      </div>

      <!-- Last Updated Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-purple-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Last Updated</h3>
            <p class="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">{{ lastUpdatedTime }}</p>
            <button
              @click="refreshData"
              class="mt-2 text-sm text-purple-600 hover:text-purple-700 dark:text-purple-400 flex items-center gap-1"
              :disabled="isRefreshing"
            >
              <i class="fas fa-sync-alt" :class="{ 'animate-spin': isRefreshing }"></i>
              Refresh Now
            </button>
          </div>
          <i class="fas fa-clock text-3xl text-purple-500"></i>
        </div>
      </div>
    </div>

    <!-- Tabs: Bridges / Tools / Health -->
    <div class="mb-6">
      <div class="border-b border-gray-200 dark:border-gray-700">
        <nav class="-mb-px flex space-x-8">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm',
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400'
            ]"
          >
            <i :class="tab.icon" class="mr-2"></i>
            {{ tab.label }}
          </button>
        </nav>
      </div>
    </div>

    <!-- Bridges Tab -->
    <div v-if="activeTab === 'bridges'" class="space-y-4">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-blue-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading MCP bridges...</p>
      </div>

      <div v-else-if="bridges.length === 0" class="text-center py-12">
        <i class="fas fa-exclamation-triangle text-4xl text-yellow-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">No MCP bridges found</p>
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          v-for="bridge in bridges"
          :key="bridge.name"
          class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4"
          :class="bridgeBorderClass(bridge.status)"
        >
          <!-- Bridge Header -->
          <div class="flex items-start justify-between mb-4">
            <div class="flex-1">
              <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                {{ bridge.name }}
                <span
                  class="px-2 py-1 text-xs font-medium rounded-full"
                  :class="statusBadgeClass(bridge.status)"
                >
                  {{ bridge.status }}
                </span>
              </h3>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ bridge.description }}</p>
            </div>
          </div>

          <!-- Bridge Stats -->
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <p class="text-xs text-gray-500 dark:text-gray-400 uppercase">Tools</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ bridge.tool_count }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-500 dark:text-gray-400 uppercase">Features</p>
              <p class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ bridge.features.length }}</p>
            </div>
          </div>

          <!-- Features List -->
          <div class="mb-4">
            <p class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">FEATURES:</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="feature in bridge.features"
                :key="feature"
                class="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded"
              >
                {{ feature }}
              </span>
            </div>
          </div>

          <!-- Endpoint -->
          <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <p class="text-xs text-gray-500 dark:text-gray-400">ENDPOINT:</p>
            <code class="text-xs text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded">
              {{ bridge.endpoint }}
            </code>
          </div>

          <!-- Error Message (if any) -->
          <div v-if="bridge.error" class="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded">
            <p class="text-xs text-red-700 dark:text-red-300">
              <i class="fas fa-exclamation-circle mr-1"></i>
              {{ bridge.error }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Tools Tab -->
    <div v-if="activeTab === 'tools'" class="space-y-4">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-blue-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading MCP tools...</p>
      </div>

      <div v-else-if="tools.length === 0" class="text-center py-12">
        <i class="fas fa-exclamation-triangle text-4xl text-yellow-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">No MCP tools found</p>
      </div>

      <div v-else>
        <!-- Tools Filter -->
        <div class="mb-4">
          <input
            v-model="toolFilter"
            type="text"
            placeholder="Search tools..."
            class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>

        <!-- Tools List -->
        <div class="space-y-3">
          <div
            v-for="tool in filteredTools"
            :key="tool.name"
            class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-5 hover:shadow-lg transition-shadow"
          >
            <!-- Tool Header -->
            <div class="flex items-start justify-between mb-3">
              <div class="flex-1">
                <h4 class="text-base font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <i class="fas fa-wrench text-blue-500 text-sm"></i>
                  {{ tool.name }}
                </h4>
                <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ tool.description }}</p>
              </div>
              <button
                @click="toggleToolSchema(tool.name)"
                class="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded"
              >
                <i class="fas" :class="expandedTools.has(tool.name) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
                Schema
              </button>
            </div>

            <!-- Bridge Info -->
            <div class="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400 mb-3">
              <span class="flex items-center gap-1">
                <i class="fas fa-layer-group"></i>
                Bridge: <strong class="text-gray-900 dark:text-gray-100">{{ tool.bridge }}</strong>
              </span>
              <span class="flex items-center gap-1">
                <i class="fas fa-link"></i>
                <code class="text-xs bg-gray-100 dark:bg-gray-900 px-2 py-0.5 rounded">{{ tool.endpoint }}</code>
              </span>
            </div>

            <!-- Expanded Schema -->
            <div v-if="expandedTools.has(tool.name)" class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <p class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">INPUT SCHEMA:</p>
              <pre class="bg-gray-900 text-green-400 p-4 rounded text-xs overflow-x-auto">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Health Tab -->
    <div v-if="activeTab === 'health'" class="space-y-4">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-blue-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading health status...</p>
      </div>

      <div v-else>
        <!-- Overall Health Status -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100">Overall MCP System Health</h3>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ healthData.timestamp }}</p>
            </div>
            <div class="flex items-center gap-3">
              <span
                class="px-4 py-2 text-lg font-bold rounded-full"
                :class="statusBadgeClass(healthData.status)"
              >
                {{ healthData.status }}
              </span>
            </div>
          </div>
        </div>

        <!-- Individual Bridge Health Checks -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div
            v-for="check in healthData.checks"
            :key="check.bridge"
            class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-5"
          >
            <div class="flex items-start justify-between mb-3">
              <h4 class="text-base font-bold text-gray-900 dark:text-gray-100">{{ check.bridge }}</h4>
              <span
                class="px-2 py-1 text-xs font-medium rounded-full"
                :class="statusBadgeClass(check.status)"
              >
                {{ check.status }}
              </span>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 dark:text-gray-400">Response Time</p>
                <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ check.response_time_ms }}ms</p>
              </div>
              <div v-if="check.tool_count">
                <p class="text-xs text-gray-500 dark:text-gray-400">Tools Available</p>
                <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ check.tool_count }}</p>
              </div>
            </div>

            <div v-if="check.error" class="mt-3 p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded">
              <p class="text-xs text-red-700 dark:text-red-300">{{ check.error }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue';
import AppConfig from '@/config/AppConfig';
import { useToast } from '@/composables/useToast';

export default {
  name: 'MCPManager',
  setup() {
    const activeTab = ref('bridges');
    const loading = ref(false);
    const isRefreshing = ref(false);
    const bridges = ref([]);
    const tools = ref([]);
    const healthData = ref({ status: 'unknown', checks: [], timestamp: '' });
    const stats = ref({});
    const toolFilter = ref('');
    const expandedTools = ref(new Set());
    const lastUpdated = ref(null);

    // Toast notifications
    const { showToast } = useToast();
    const notify = (message, type = 'info') => {
      showToast(message, type, type === 'error' ? 5000 : 3000);
    };

    const tabs = [
      { id: 'bridges', label: 'MCP Bridges', icon: 'fas fa-layer-group' },
      { id: 'tools', label: 'Available Tools', icon: 'fas fa-toolbox' },
      { id: 'health', label: 'Health Status', icon: 'fas fa-heartbeat' },
    ];

    const bridgeHealthClass = computed(() => {
      const ratio = stats.value.healthy_bridges / stats.value.total_bridges;
      if (ratio === 1) return 'text-green-600 dark:text-green-400';
      if (ratio >= 0.5) return 'text-yellow-600 dark:text-yellow-400';
      return 'text-red-600 dark:text-red-400';
    });

    const bridgeHealthText = computed(() => {
      const ratio = stats.value.healthy_bridges / stats.value.total_bridges;
      if (ratio === 1) return 'All systems operational';
      if (ratio >= 0.5) return 'Some systems degraded';
      return 'Multiple systems down';
    });

    const lastUpdatedTime = computed(() => {
      if (!lastUpdated.value) return 'Never';
      const now = new Date();
      const diff = Math.floor((now - lastUpdated.value) / 1000);
      if (diff < 60) return `${diff}s ago`;
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      return `${Math.floor(diff / 3600)}h ago`;
    });

    const filteredTools = computed(() => {
      if (!toolFilter.value) return tools.value;
      const filter = toolFilter.value.toLowerCase();
      return tools.value.filter(
        tool =>
          tool.name.toLowerCase().includes(filter) ||
          tool.description.toLowerCase().includes(filter) ||
          tool.bridge.toLowerCase().includes(filter)
      );
    });

    const bridgeBorderClass = (status) => {
      if (status === 'healthy') return 'border-green-500';
      if (status === 'degraded') return 'border-yellow-500';
      return 'border-red-500';
    };

    const statusBadgeClass = (status) => {
      if (status === 'healthy') return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      if (status === 'degraded') return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    };

    const toggleToolSchema = (toolName) => {
      if (expandedTools.value.has(toolName)) {
        expandedTools.value.delete(toolName);
      } else {
        expandedTools.value.add(toolName);
      }
      // Trigger reactivity
      expandedTools.value = new Set(expandedTools.value);
    };

    const fetchBridges = async () => {
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/mcp/bridges`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        bridges.value = data.bridges || [];
      } catch (error) {
        console.error('[MCPManager] Failed to fetch MCP bridges:', error);
        notify('Failed to load MCP bridges', 'error');
      }
    };

    const fetchTools = async () => {
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/mcp/tools`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        tools.value = data.tools || [];
      } catch (error) {
        console.error('[MCPManager] Failed to fetch MCP tools:', error);
        notify('Failed to load MCP tools', 'error');
      }
    };

    const fetchHealth = async () => {
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/mcp/health`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        healthData.value = data;
      } catch (error) {
        console.error('[MCPManager] Failed to fetch MCP health:', error);
        notify('Failed to load MCP health status', 'warning');
      }
    };

    const fetchStats = async () => {
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/mcp/stats`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        stats.value = data.overview || {};
      } catch (error) {
        console.error('[MCPManager] Failed to fetch MCP stats:', error);
        notify('Failed to load MCP statistics', 'warning');
      }
    };

    const refreshData = async () => {
      isRefreshing.value = true;
      loading.value = true;
      try {
        await Promise.all([
          fetchBridges(),
          fetchTools(),
          fetchHealth(),
          fetchStats(),
        ]);
        lastUpdated.value = new Date();
      } finally {
        loading.value = false;
        isRefreshing.value = false;
      }
    };

    onMounted(() => {
      refreshData();
      // Auto-refresh every 30 seconds
      setInterval(() => {
        refreshData();
      }, 30000);
    });

    return {
      activeTab,
      loading,
      isRefreshing,
      bridges,
      tools,
      healthData,
      stats,
      tabs,
      toolFilter,
      expandedTools,
      bridgeHealthClass,
      bridgeHealthText,
      lastUpdatedTime,
      filteredTools,
      bridgeBorderClass,
      statusBadgeClass,
      toggleToolSchema,
      refreshData,
    };
  },
};
</script>

<style scoped>
.mcp-manager {
  padding: 1.5rem;
  min-height: 100vh;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
