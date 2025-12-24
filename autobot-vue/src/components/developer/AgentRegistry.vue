<template>
  <div class="agent-registry">
    <!-- Header -->
    <div class="header-section mb-6">
      <h2 class="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-3">
        <i class="fas fa-robot text-purple-600"></i>
        AutoBot Agent Registry
      </h2>
      <p class="text-sm text-gray-600 dark:text-gray-400 mt-2">
        Manage and monitor AutoBot's AI agents - both backend and Claude specialized agents
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
              {{ summary.total_backend || 0 }} backend + {{ summary.total_claude || 0 }} Claude
            </p>
          </div>
          <i class="fas fa-users text-3xl text-purple-500"></i>
        </div>
      </div>

      <!-- Backend Agents Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-blue-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Backend Agents</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">
              {{ summary.healthy_backend || 0 }}/{{ summary.total_backend || 0 }}
            </p>
            <p class="mt-1 text-sm" :class="backendHealthClass">
              {{ backendHealthText }}
            </p>
          </div>
          <i class="fas fa-server text-3xl text-blue-500"></i>
        </div>
      </div>

      <!-- Claude Agents Card -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4 border-green-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">Claude Agents</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900 dark:text-gray-100">
              {{ summary.available_claude || 0 }}
            </p>
            <p class="mt-1 text-sm text-green-600 dark:text-green-400">
              All available
            </p>
          </div>
          <i class="fas fa-brain text-3xl text-green-500"></i>
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

    <!-- Tabs: Backend / Claude / Categories -->
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
                ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400'
            ]"
          >
            <i :class="tab.icon" class="mr-2"></i>
            {{ tab.label }}
            <span v-if="tab.count" class="ml-2 px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700">
              {{ tab.count }}
            </span>
          </button>
        </nav>
      </div>
    </div>

    <!-- Backend Agents Tab -->
    <div v-if="activeTab === 'backend'" class="space-y-4">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-purple-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading backend agents...</p>
      </div>

      <div v-else-if="backendAgents.length === 0" class="text-center py-12">
        <i class="fas fa-exclamation-triangle text-4xl text-yellow-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">No backend agents found</p>
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          v-for="agent in backendAgents"
          :key="agent.id"
          class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border-l-4"
          :class="agentBorderClass(agent.status)"
        >
          <!-- Agent Header -->
          <div class="flex items-start justify-between mb-4">
            <div class="flex-1">
              <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <i class="fas fa-server text-blue-500"></i>
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
                class="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded"
              >
                {{ task }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Claude Agents Tab -->
    <div v-if="activeTab === 'claude'" class="space-y-4">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-purple-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading Claude agents...</p>
      </div>

      <div v-else-if="claudeAgents.length === 0" class="text-center py-12">
        <i class="fas fa-exclamation-triangle text-4xl text-yellow-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">No Claude agents found</p>
      </div>

      <div v-else>
        <!-- Claude Agents Filter -->
        <div class="mb-4 flex flex-wrap gap-4">
          <input
            v-model="claudeFilter"
            type="text"
            placeholder="Search Claude agents..."
            class="flex-1 min-w-64 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <select
            v-model="categoryFilter"
            class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            <option value="">All Categories</option>
            <option value="implementation">Implementation</option>
            <option value="analysis">Analysis</option>
            <option value="planning">Planning</option>
            <option value="specialized">Specialized</option>
          </select>
        </div>

        <!-- Claude Agents List -->
        <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          <div
            v-for="agent in filteredClaudeAgents"
            :key="agent.id"
            class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-5 hover:shadow-lg transition-shadow border-l-4"
            :class="getCategoryBorderClass(agent.category)"
          >
            <!-- Agent Header -->
            <div class="flex items-start justify-between mb-3">
              <div class="flex-1">
                <h4 class="text-base font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <span
                    class="w-3 h-3 rounded-full"
                    :class="getColorClass(agent.color)"
                  ></span>
                  {{ agent.name }}
                </h4>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                  {{ truncateDescription(agent.description) }}
                </p>
              </div>
              <span
                class="px-2 py-1 text-xs font-medium rounded-full"
                :class="getCategoryBadgeClass(agent.category)"
              >
                {{ agent.category }}
              </span>
            </div>

            <!-- Agent Info -->
            <div class="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400 mb-3">
              <span class="flex items-center gap-1">
                <i class="fas fa-wrench"></i>
                {{ agent.tool_count }} tools
              </span>
              <span v-if="agent.model" class="flex items-center gap-1">
                <i class="fas fa-microchip"></i>
                {{ agent.model }}
              </span>
            </div>

            <!-- Sample Tools -->
            <div class="flex flex-wrap gap-1">
              <span
                v-for="tool in (agent.tools || []).slice(0, 3)"
                :key="tool"
                class="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
              >
                {{ formatTool(tool) }}
              </span>
              <span
                v-if="agent.tool_count > 3"
                class="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded"
              >
                +{{ agent.tool_count - 3 }} more
              </span>
            </div>

            <!-- View Details Button -->
            <button
              @click="showAgentDetails(agent)"
              class="mt-3 w-full px-3 py-1.5 text-xs bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200 rounded hover:bg-purple-200 dark:hover:bg-purple-800 transition-colors"
            >
              <i class="fas fa-info-circle mr-1"></i>
              View Details
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Categories Tab -->
    <div v-if="activeTab === 'categories'" class="space-y-6">
      <div v-if="loading" class="text-center py-12">
        <i class="fas fa-spinner fa-spin text-4xl text-purple-500"></i>
        <p class="mt-4 text-gray-600 dark:text-gray-400">Loading categories...</p>
      </div>

      <div v-else>
        <!-- Category Summary Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div
            v-for="(count, category) in claudeCategories"
            :key="category"
            class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-5 border-l-4 cursor-pointer hover:shadow-lg transition-shadow"
            :class="getCategoryBorderClass(category)"
            @click="filterByCategory(category)"
          >
            <div class="flex items-center justify-between">
              <div>
                <h4 class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase">{{ category }}</h4>
                <p class="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">{{ count }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">agents</p>
              </div>
              <i :class="getCategoryIcon(category)" class="text-2xl" :style="{ color: getCategoryColor(category) }"></i>
            </div>
          </div>
        </div>

        <!-- Category Descriptions -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">Agent Categories</h3>
          <div class="space-y-4">
            <div class="flex items-start gap-4">
              <div class="w-3 h-3 mt-1.5 rounded-full bg-blue-500"></div>
              <div>
                <h4 class="font-medium text-gray-900 dark:text-gray-100">Implementation</h4>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  Backend, frontend, database, DevOps, and testing engineers for building features
                </p>
              </div>
            </div>
            <div class="flex items-start gap-4">
              <div class="w-3 h-3 mt-1.5 rounded-full bg-orange-500"></div>
              <div>
                <h4 class="font-medium text-gray-900 dark:text-gray-100">Analysis</h4>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  Code reviewers, architects, security auditors, and performance engineers for analysis tasks
                </p>
              </div>
            </div>
            <div class="flex items-start gap-4">
              <div class="w-3 h-3 mt-1.5 rounded-full bg-green-500"></div>
              <div>
                <h4 class="font-medium text-gray-900 dark:text-gray-100">Planning</h4>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  Project managers, task planners, and PRD writers for planning and documentation
                </p>
              </div>
            </div>
            <div class="flex items-start gap-4">
              <div class="w-3 h-3 mt-1.5 rounded-full bg-purple-500"></div>
              <div>
                <h4 class="font-medium text-gray-900 dark:text-gray-100">Specialized</h4>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  Content writers, designers, refactoring specialists, and utility agents
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Agent Details Modal -->
    <div
      v-if="selectedAgent"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      @click.self="selectedAgent = null"
    >
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
        <!-- Modal Header -->
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span
              class="w-3 h-3 rounded-full"
              :class="getColorClass(selectedAgent.color)"
            ></span>
            {{ selectedAgent.name }}
          </h3>
          <button
            @click="selectedAgent = null"
            class="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <i class="fas fa-times text-xl"></i>
          </button>
        </div>

        <!-- Modal Body -->
        <div class="px-6 py-4 overflow-y-auto max-h-[60vh]">
          <!-- Description -->
          <div class="mb-4">
            <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Description</h4>
            <p class="text-sm text-gray-600 dark:text-gray-400">{{ selectedAgent.description }}</p>
          </div>

          <!-- Metadata -->
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Category</h4>
              <span
                class="px-2 py-1 text-xs font-medium rounded-full"
                :class="getCategoryBadgeClass(selectedAgent.category)"
              >
                {{ selectedAgent.category }}
              </span>
            </div>
            <div>
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Model</h4>
              <p class="text-sm text-gray-600 dark:text-gray-400">{{ selectedAgent.model || 'Default (Claude)' }}</p>
            </div>
            <div>
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Total Tools</h4>
              <p class="text-sm text-gray-600 dark:text-gray-400">{{ selectedAgent.tool_count }}</p>
            </div>
            <div>
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">File</h4>
              <p class="text-sm text-gray-600 dark:text-gray-400 font-mono">{{ selectedAgent.file }}</p>
            </div>
          </div>

          <!-- Tools -->
          <div>
            <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Available Tools</h4>
            <div class="flex flex-wrap gap-1 max-h-48 overflow-y-auto">
              <span
                v-for="tool in selectedAgent.tools"
                :key="tool"
                class="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
              >
                {{ formatTool(tool) }}
              </span>
            </div>
          </div>
        </div>

        <!-- Modal Footer -->
        <div class="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end">
          <button
            @click="selectedAgent = null"
            class="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Close
          </button>
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
    const activeTab = ref('backend');
    const loading = ref(false);
    const isRefreshing = ref(false);
    const backendAgents = ref([]);
    const claudeAgents = ref([]);
    const claudeCategories = ref({});
    const summary = ref({});
    const claudeFilter = ref('');
    const categoryFilter = ref('');
    const selectedAgent = ref(null);
    const lastUpdated = ref(null);

    // Toast notifications
    const { showToast } = useToast();
    const notify = (message, type = 'info') => {
      showToast(message, type, type === 'error' ? 5000 : 3000);
    };

    const tabs = computed(() => [
      { id: 'backend', label: 'Backend Agents', icon: 'fas fa-server', count: backendAgents.value.length },
      { id: 'claude', label: 'Claude Agents', icon: 'fas fa-brain', count: claudeAgents.value.length },
      { id: 'categories', label: 'Categories', icon: 'fas fa-tags', count: null },
    ]);

    const backendHealthClass = computed(() => {
      const ratio = summary.value.healthy_backend / summary.value.total_backend;
      if (ratio === 1) return 'text-green-600 dark:text-green-400';
      if (ratio >= 0.5) return 'text-yellow-600 dark:text-yellow-400';
      return 'text-red-600 dark:text-red-400';
    });

    const backendHealthText = computed(() => {
      const ratio = summary.value.healthy_backend / summary.value.total_backend;
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

    const filteredClaudeAgents = computed(() => {
      let filtered = claudeAgents.value;

      if (claudeFilter.value) {
        const filter = claudeFilter.value.toLowerCase();
        filtered = filtered.filter(
          agent =>
            agent.name.toLowerCase().includes(filter) ||
            agent.description.toLowerCase().includes(filter)
        );
      }

      if (categoryFilter.value) {
        filtered = filtered.filter(agent => agent.category === categoryFilter.value);
      }

      return filtered;
    });

    const agentBorderClass = (status) => {
      if (status === 'connected') return 'border-green-500';
      if (status === 'degraded') return 'border-yellow-500';
      return 'border-red-500';
    };

    const statusBadgeClass = (status) => {
      if (status === 'connected' || status === 'available') return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      if (status === 'degraded') return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    };

    const getCategoryBorderClass = (category) => {
      const colors = {
        implementation: 'border-blue-500',
        analysis: 'border-orange-500',
        planning: 'border-green-500',
        specialized: 'border-purple-500',
        general: 'border-gray-500',
      };
      return colors[category] || 'border-gray-500';
    };

    const getCategoryBadgeClass = (category) => {
      const colors = {
        implementation: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
        analysis: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
        planning: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        specialized: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
        general: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
      };
      return colors[category] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
    };

    const getCategoryIcon = (category) => {
      const icons = {
        implementation: 'fas fa-code',
        analysis: 'fas fa-search',
        planning: 'fas fa-project-diagram',
        specialized: 'fas fa-star',
        general: 'fas fa-robot',
      };
      return icons[category] || 'fas fa-robot';
    };

    const getCategoryColor = (category) => {
      const colors = {
        implementation: '#3B82F6',
        analysis: '#F97316',
        planning: '#22C55E',
        specialized: '#A855F7',
        general: '#6B7280',
      };
      return colors[category] || '#6B7280';
    };

    const getColorClass = (color) => {
      const colorMap = {
        orange: 'bg-orange-500',
        cyan: 'bg-cyan-500',
        blue: 'bg-blue-500',
        green: 'bg-green-500',
        purple: 'bg-purple-500',
        red: 'bg-red-500',
        yellow: 'bg-yellow-500',
        pink: 'bg-pink-500',
        gray: 'bg-gray-500',
      };
      return colorMap[color] || 'bg-gray-500';
    };

    const formatTool = (tool) => {
      // Shorten long tool names
      if (tool.startsWith('mcp__')) {
        const parts = tool.split('__');
        return parts.length > 1 ? parts.slice(1).join('_') : tool;
      }
      return tool;
    };

    const truncateDescription = (desc) => {
      if (!desc) return '';
      if (desc.length <= 100) return desc;
      return desc.substring(0, 100) + '...';
    };

    const filterByCategory = (category) => {
      categoryFilter.value = category;
      activeTab.value = 'claude';
    };

    const showAgentDetails = async (agent) => {
      // Fetch full details if needed
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/agents/claude/${agent.id}`);
        if (response.ok) {
          const data = await response.json();
          selectedAgent.value = data;
        } else {
          selectedAgent.value = agent;
        }
      } catch {
        selectedAgent.value = agent;
      }
    };

    const fetchAllAgents = async () => {
      try {
        const url = await AppConfig.getServiceUrl('backend');
        const response = await fetch(`${url}/api/agents/all`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        backendAgents.value = data.backend_agents || [];
        claudeAgents.value = data.claude_agents || [];
        summary.value = data.summary || {};

        // Build categories from Claude agents
        const categories = {};
        for (const agent of claudeAgents.value) {
          const cat = agent.category || 'general';
          categories[cat] = (categories[cat] || 0) + 1;
        }
        claudeCategories.value = categories;

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
      activeTab,
      loading,
      isRefreshing,
      backendAgents,
      claudeAgents,
      claudeCategories,
      summary,
      tabs,
      claudeFilter,
      categoryFilter,
      selectedAgent,
      backendHealthClass,
      backendHealthText,
      lastUpdatedTime,
      filteredClaudeAgents,
      agentBorderClass,
      statusBadgeClass,
      getCategoryBorderClass,
      getCategoryBadgeClass,
      getCategoryIcon,
      getCategoryColor,
      getColorClass,
      formatTool,
      truncateDescription,
      filterByCategory,
      showAgentDetails,
      refreshData,
    };
  },
};
</script>

<style scoped>
.agent-registry {
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

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
