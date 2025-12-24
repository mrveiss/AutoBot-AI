<template>
  <div class="agent-registry">
    <!-- Header -->
    <div class="header-section mb-6">
      <h2 class="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-3">
        <i class="fas fa-robot text-purple-600"></i>
        AutoBot Agent Registry
      </h2>
      <p class="text-sm text-gray-600 dark:text-gray-400 mt-2">
        Manage and monitor AutoBot's AI agents
      </p>
    </div>

    <!-- Overview Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <!-- Total Agents Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-purple-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Total Agents</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">{{ summary.total || 0 }}</p>
            <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Registered agents
            </p>
          </div>
          <i class="fas fa-users text-3xl text-purple-500"></i>
        </div>
      </div>

      <!-- Connected Agents Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-green-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Connected</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">
              {{ summary.healthy || 0 }}
            </p>
            <p class="mt-1 text-sm" :class="healthClass">
              {{ healthText }}
            </p>
          </div>
          <i class="fas fa-check-circle text-3xl text-green-500"></i>
        </div>
      </div>

      <!-- Disconnected Agents Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-red-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Disconnected</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">
              {{ summary.disconnected || 0 }}
            </p>
            <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Need attention
            </p>
          </div>
          <i class="fas fa-exclamation-circle text-3xl text-red-500"></i>
        </div>
      </div>

      <!-- Last Updated Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-orange-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Last Updated</h3>
            <p class="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">{{ lastUpdatedTime }}</p>
            <button
              @click="refreshData"
              class="mt-2 text-sm text-orange-600 hover:text-orange-700 dark:text-orange-400 flex items-center gap-1"
              :disabled="isRefreshing"
            >
              <i class="fas fa-sync-alt" :class="{ 'animate-spin': isRefreshing }"></i>
              Refresh Now
            </button>
          </div>
          <i class="fas fa-clock text-3xl text-orange-500"></i>
        </div>
      </div>
    </div>

    <!-- Agents List -->
    <div class="space-y-4">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-purple-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading agents...</p>
      </div>

      <div v-else-if="agents.length === 0" class="text-center py-12">
        <i class="fas fa-exclamation-triangle text-4xl text-yellow-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">No agents found</p>
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          v-for="agent in agents"
          :key="agent.id"
          class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4"
          :class="agentBorderClass(agent.status)"
        >
          <!-- Agent Header -->
          <div class="flex items-start justify-between mb-4">
            <div class="flex-1">
              <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <i class="fas fa-robot text-purple-500"></i>
                {{ agent.name }}
                <span
                  class="px-2 py-1 text-xs font-medium rounded-full"
                  :class="statusBadgeClass(agent.status)"
                >
                  {{ agent.status }}
                </span>
              </h3>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ agent.description }}</p>
            </div>
            <div class="flex items-center gap-2">
              <span
                v-if="agent.enabled"
                class="px-2 py-1 text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded"
              >
                Enabled
              </span>
              <span
                v-else
                class="px-2 py-1 text-xs bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 rounded"
              >
                Disabled
              </span>
            </div>
          </div>

          <!-- Agent Stats -->
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <p class="text-xs text-gray-500 dark:text-gray-400 uppercase">Model</p>
              <p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ agent.model || 'Default' }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-500 dark:text-gray-400 uppercase">Priority</p>
              <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ agent.priority }}</p>
            </div>
          </div>

          <!-- Tasks List -->
          <div class="mb-4">
            <p class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">TASKS:</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="task in agent.tasks"
                :key="task"
                class="px-2 py-1 text-xs bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded"
              >
                {{ task }}
              </span>
            </div>
          </div>

          <!-- MCP Tools List -->
          <div v-if="agent.mcp_tools && agent.mcp_tools.length > 0" class="mb-4">
            <p class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">MCP TOOLS:</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="mcp in agent.mcp_tools"
                :key="mcp"
                class="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded flex items-center gap-1"
              >
                <i class="fas fa-plug text-[10px]"></i>
                {{ formatMcpName(mcp) }}
              </span>
            </div>
          </div>

          <!-- Invocation Info -->
          <div v-if="agent.invoked_by" class="mb-4">
            <p class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">INVOKED BY:</p>
            <p class="text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700 p-2 rounded">
              <i class="fas fa-arrow-right text-green-500 mr-1"></i>
              {{ agent.invoked_by }}
            </p>
          </div>

          <!-- Source File -->
          <div v-if="agent.source_file">
            <p class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">SOURCE:</p>
            <p class="text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700 p-2 rounded font-mono">
              <i class="fas fa-file-code text-orange-500 mr-1"></i>
              {{ agent.source_file }}
            </p>
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
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('AgentRegistry');

export default {
  name: 'AgentRegistry',
  setup() {
    const loading = ref(false);
    const isRefreshing = ref(false);
    const agents = ref([]);
    const summary = ref({});
    const lastUpdated = ref(null);

    // Toast notifications
    const { showToast } = useToast();
    const notify = (message, type = 'info') => {
      showToast(message, type, type === 'error' ? 5000 : 3000);
    };

    const healthClass = computed(() => {
      if (!summary.value.total) return 'text-gray-600 dark:text-gray-400';
      const ratio = summary.value.healthy / summary.value.total;
      if (ratio === 1) return 'text-green-600 dark:text-green-400';
      if (ratio >= 0.5) return 'text-yellow-600 dark:text-yellow-400';
      return 'text-red-600 dark:text-red-400';
    });

    const healthText = computed(() => {
      if (!summary.value.total) return 'No agents';
      const ratio = summary.value.healthy / summary.value.total;
      if (ratio === 1) return 'All connected';
      if (ratio >= 0.5) return 'Some disconnected';
      return 'Most disconnected';
    });

    const lastUpdatedTime = computed(() => {
      if (!lastUpdated.value) return 'Never';
      const now = new Date();
      const diff = Math.floor((now - lastUpdated.value) / 1000);
      if (diff < 60) return `${diff}s ago`;
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      return `${Math.floor(diff / 3600)}h ago`;
    });

    const agentBorderClass = (status) => {
      if (status === 'connected') return 'border-green-500';
      if (status === 'degraded') return 'border-yellow-500';
      return 'border-red-500';
    };

    const statusBadgeClass = (status) => {
      if (status === 'connected') return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      if (status === 'degraded') return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    };

    const formatMcpName = (mcp) => {
      // Convert mcp_name to readable format: "knowledge_mcp" -> "Knowledge"
      return mcp.replace('_mcp', '').split('_').map(word =>
        word.charAt(0).toUpperCase() + word.slice(1)
      ).join(' ');
    };

    const fetchAllAgents = async () => {
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/agent_config/agents/all`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        agents.value = data.agents || [];
        summary.value = data.summary || {};
      } catch (error) {
        logger.error('Failed to fetch agents:', error);
        notify('Failed to load agents', 'error');
      }
    };

    const refreshData = async () => {
      isRefreshing.value = true;
      loading.value = true;
      try {
        await fetchAllAgents();
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
      loading,
      isRefreshing,
      agents,
      summary,
      healthClass,
      healthText,
      lastUpdatedTime,
      agentBorderClass,
      statusBadgeClass,
      formatMcpName,
      refreshData,
    };
  },
};
</script>

<style scoped>
.agent-registry {
  padding: 1.5rem;
}
</style>
