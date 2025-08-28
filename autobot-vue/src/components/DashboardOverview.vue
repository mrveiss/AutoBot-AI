<template>
  <div class="dashboard-overview">
    <!-- Quick Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <!-- System Status Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-green-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">System Status</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ systemStatus.status }}</p>
            <p class="mt-2 text-sm text-gray-600">{{ systemStatus.message }}</p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-server text-3xl" :class="systemStatus.iconClass"></i>
          </div>
        </div>
      </div>

      <!-- Active Sessions Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-blue-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Active Sessions</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ activeSessions }}</p>
            <p class="mt-2 text-sm text-green-600">
              <i class="fas fa-arrow-up"></i>
              {{ sessionsChange }}% from last hour
            </p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-users text-3xl text-blue-500"></i>
          </div>
        </div>
      </div>

      <!-- Knowledge Base Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Knowledge Items</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ knowledgeStats.totalItems }}</p>
            <p class="mt-2 text-sm text-gray-600">{{ knowledgeStats.categories }} categories</p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-brain text-3xl text-purple-500"></i>
          </div>
        </div>
      </div>

      <!-- Performance Score Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-yellow-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Performance</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ performanceScore }}%</p>
            <p class="mt-2 text-sm" :class="performanceChange >= 0 ? 'text-green-600' : 'text-red-600'">
              <i :class="performanceChange >= 0 ? 'fas fa-arrow-up' : 'fas fa-arrow-down'"></i>
              {{ Math.abs(performanceChange) }}% from yesterday
            </p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-tachometer-alt text-3xl text-yellow-500"></i>
          </div>
        </div>
      </div>
    </div>

    <!-- Main Dashboard Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
      <!-- System Health -->
      <div class="lg:col-span-2">
        <div class="bg-white rounded-lg shadow-md p-6">
          <div class="flex items-center justify-between mb-6">
            <h3 class="text-lg font-semibold text-gray-900">System Health</h3>
            <div class="flex space-x-2">
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <span class="w-2 h-2 bg-green-400 rounded-full mr-1"></span>
                Healthy
              </span>
            </div>
          </div>

          <!-- Service Status Grid -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div v-for="service in services" :key="service.name" class="text-center">
              <div class="flex flex-col items-center">
                <div class="w-12 h-12 rounded-full flex items-center justify-center mb-2" :class="service.statusClass">
                  <i :class="service.icon" class="text-xl text-white"></i>
                </div>
                <h4 class="font-medium text-gray-900 text-sm">{{ service.name }}</h4>
                <p class="text-xs text-gray-500">{{ service.status }}</p>
                <p class="text-xs text-gray-400">{{ service.responseTime }}ms</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="space-y-6">
        <!-- Recent Activity -->
        <div class="bg-white rounded-lg shadow-md p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Recent Activity</h3>
          <div class="space-y-3">
            <div v-for="activity in recentActivity" :key="activity.id" class="flex items-center space-x-3">
              <div class="flex-shrink-0">
                <i :class="activity.icon" class="text-gray-400"></i>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 truncate">{{ activity.action }}</p>
                <p class="text-sm text-gray-500">{{ activity.time }}</p>
              </div>
            </div>
          </div>
          <div class="mt-4">
            <router-link to="/monitoring" class="text-sm text-blue-600 hover:text-blue-900 font-medium">
              View all activity →
            </router-link>
          </div>
        </div>

        <!-- Quick Links -->
        <div class="bg-white rounded-lg shadow-md p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h3>
          <div class="space-y-2">
            <router-link to="/chat" class="flex items-center space-x-2 p-2 rounded-md hover:bg-gray-50 transition-colors">
              <i class="fas fa-comments text-blue-500"></i>
              <span class="text-sm font-medium">Start New Chat</span>
            </router-link>
            <router-link to="/knowledge/upload" class="flex items-center space-x-2 p-2 rounded-md hover:bg-gray-50 transition-colors">
              <i class="fas fa-upload text-green-500"></i>
              <span class="text-sm font-medium">Upload Document</span>
            </router-link>
            <router-link to="/tools/terminal" class="flex items-center space-x-2 p-2 rounded-md hover:bg-gray-50 transition-colors">
              <i class="fas fa-terminal text-gray-700"></i>
              <span class="text-sm font-medium">Open Terminal</span>
            </router-link>
            <router-link to="/monitoring/system" class="flex items-center space-x-2 p-2 rounded-md hover:bg-gray-50 transition-colors">
              <i class="fas fa-chart-line text-purple-500"></i>
              <span class="text-sm font-medium">System Monitor</span>
            </router-link>
          </div>
        </div>
      </div>
    </div>

    <!-- Performance Charts Row -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <!-- API Performance Chart -->
      <div class="bg-white rounded-lg shadow-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">API Performance</h3>
        <div class="h-64 flex items-center justify-center bg-gray-50 rounded-lg">
          <div class="text-center">
            <i class="fas fa-chart-line text-4xl text-gray-300 mb-2"></i>
            <p class="text-gray-500">API Response Time Chart</p>
            <p class="text-sm text-gray-400">Real-time monitoring active</p>
            <div class="mt-4">
              <span class="text-sm text-green-600">Avg: {{ avgResponseTime }}ms</span>
              <span class="mx-2 text-gray-300">|</span>
              <span class="text-sm text-blue-600">Requests: {{ totalRequests }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- System Resources -->
      <div class="bg-white rounded-lg shadow-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">System Resources</h3>
        <div class="space-y-4">
          <!-- CPU Usage -->
          <div>
            <div class="flex justify-between text-sm font-medium text-gray-700 mb-1">
              <span>CPU Usage</span>
              <span>{{ systemResources.cpu }}%</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2">
              <div class="bg-blue-500 h-2 rounded-full transition-all duration-300" :style="`width: ${systemResources.cpu}%`"></div>
            </div>
          </div>

          <!-- Memory Usage -->
          <div>
            <div class="flex justify-between text-sm font-medium text-gray-700 mb-1">
              <span>Memory Usage</span>
              <span>{{ systemResources.memory }}%</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2">
              <div class="bg-green-500 h-2 rounded-full transition-all duration-300" :style="`width: ${systemResources.memory}%`"></div>
            </div>
          </div>

          <!-- Disk Usage -->
          <div>
            <div class="flex justify-between text-sm font-medium text-gray-700 mb-1">
              <span>Disk Usage</span>
              <span>{{ systemResources.disk }}%</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2">
              <div class="bg-yellow-500 h-2 rounded-full transition-all duration-300" :style="`width: ${systemResources.disk}%`"></div>
            </div>
          </div>

          <!-- Network Usage -->
          <div>
            <div class="flex justify-between text-sm font-medium text-gray-700 mb-1">
              <span>Network I/O</span>
              <span>{{ systemResources.network }}%</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2">
              <div class="bg-purple-500 h-2 rounded-full transition-all duration-300" :style="`width: ${systemResources.network}%`"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

const appStore = useAppStore()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()

// Dashboard data
const systemStatus = ref({
  status: 'Healthy',
  message: 'All systems operational',
  iconClass: 'text-green-500'
})

const activeSessions = ref(12)
const sessionsChange = ref(8)
const performanceScore = ref(94)
const performanceChange = ref(2)

const knowledgeStats = ref({
  totalItems: 2847,
  categories: 12
})

const services = ref([
  { name: 'Backend', status: 'Online', icon: 'fas fa-server', statusClass: 'bg-green-500', responseTime: 23 },
  { name: 'Database', status: 'Online', icon: 'fas fa-database', statusClass: 'bg-green-500', responseTime: 12 },
  { name: 'LLM', status: 'Ready', icon: 'fas fa-brain', statusClass: 'bg-blue-500', responseTime: 156 },
  { name: 'Redis', status: 'Warning', icon: 'fas fa-memory', statusClass: 'bg-yellow-500', responseTime: 45 }
])

const recentActivity = ref([
  { id: 1, action: 'New chat session started', time: '2 minutes ago', icon: 'fas fa-comment' },
  { id: 2, action: 'Document uploaded to knowledge base', time: '5 minutes ago', icon: 'fas fa-file-upload' },
  { id: 3, action: 'System health check completed', time: '10 minutes ago', icon: 'fas fa-check-circle' },
  { id: 4, action: 'Performance optimization applied', time: '15 minutes ago', icon: 'fas fa-cogs' }
])

const avgResponseTime = ref(28)
const totalRequests = ref(1247)

const systemResources = ref({
  cpu: 34,
  memory: 67,
  disk: 23,
  network: 12
})

// Update system metrics
const updateMetrics = () => {
  // Simulate real-time updates
  systemResources.value.cpu = Math.max(10, Math.min(90, systemResources.value.cpu + (Math.random() - 0.5) * 10))
  systemResources.value.memory = Math.max(20, Math.min(85, systemResources.value.memory + (Math.random() - 0.5) * 5))
  systemResources.value.network = Math.max(5, Math.min(50, systemResources.value.network + (Math.random() - 0.5) * 15))

  avgResponseTime.value = Math.max(15, Math.min(100, avgResponseTime.value + (Math.random() - 0.5) * 10))
  totalRequests.value += Math.floor(Math.random() * 5)

  activeSessions.value += Math.floor((Math.random() - 0.5) * 2)
  if (activeSessions.value < 1) activeSessions.value = 1
}

let updateInterval: number

onMounted(() => {
  // Update metrics every 5 seconds
  updateInterval = setInterval(updateMetrics, 5000)
})

onUnmounted(() => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
})
</script>

<style scoped>
.dashboard-overview {
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.bg-white {
  transition: box-shadow 0.2s ease-in-out;
}

.bg-white:hover {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
}
</style>
