<template>
  <div class="redis-optimization-panel">
    <!-- Summary Header -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <div class="flex flex-wrap items-center justify-between">
        <div>
          <h2 class="text-xl font-semibold text-blueGray-700">Redis Optimizations</h2>
          <p class="text-sm text-blueGray-500 mt-1">
            {{ optimizations.length }} optimization opportunities found
          </p>
        </div>
        <div class="flex items-center space-x-4 mt-4 sm:mt-0">
          <select
            v-model="categoryFilter"
            class="px-3 py-2 border border-blueGray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All Types</option>
            <option value="pipeline">Pipeline</option>
            <option value="lua_script">Lua Script</option>
            <option value="data_structure">Data Structure</option>
            <option value="connection">Connection</option>
            <option value="cache">Cache</option>
          </select>
          <button
            @click="$emit('refresh')"
            :disabled="loading"
            class="px-4 py-2 text-indigo-600 hover:text-indigo-800 flex items-center"
          >
            <i class="fas fa-sync-alt mr-2" :class="{ 'animate-spin': loading }"></i>
            Refresh
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="bg-white rounded-lg shadow-md p-12 text-center">
      <i class="fas fa-spinner fa-spin text-4xl text-indigo-500 mb-4"></i>
      <p class="text-blueGray-600">Analyzing Redis usage patterns...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredOptimizations.length === 0" class="bg-white rounded-lg shadow-md p-12 text-center">
      <i class="fas fa-database text-4xl text-green-500 mb-4"></i>
      <p class="text-lg font-medium text-blueGray-700">No Redis optimizations needed</p>
      <p class="text-sm text-blueGray-500 mt-2">Redis usage patterns look optimal!</p>
    </div>

    <!-- Optimizations List -->
    <div v-else class="space-y-4">
      <div
        v-for="(opt, index) in filteredOptimizations"
        :key="index"
        class="bg-white rounded-lg shadow-md p-6 border-l-4"
        :class="getSeverityBorderClass(opt.severity)"
      >
        <div class="flex items-center flex-wrap gap-2 mb-2">
          <span
            class="px-2 py-1 text-xs font-medium rounded uppercase"
            :class="getSeverityBadgeClass(opt.severity)"
          >
            {{ opt.severity }}
          </span>
          <span class="text-sm font-medium text-blueGray-700">
            {{ formatOptType(opt.optimization_type) }}
          </span>
          <span
            v-if="opt.category"
            class="px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded"
          >
            {{ opt.category }}
          </span>
        </div>
        <p class="text-sm text-blueGray-600">{{ opt.description }}</p>
        <div class="mt-3 flex items-center text-sm text-blueGray-500">
          <i class="fas fa-file-code mr-2"></i>
          <span class="font-mono">{{ formatFilePath(opt.file_path) }}</span>
          <span v-if="opt.line" class="ml-2">:{{ opt.line }}</span>
        </div>
        <div v-if="opt.code_snippet" class="mt-3 p-3 bg-blueGray-50 rounded-lg font-mono text-xs overflow-x-auto">
          <pre>{{ opt.code_snippet }}</pre>
        </div>
        <div v-if="opt.recommendation" class="mt-3 p-3 bg-green-50 rounded-lg border border-green-200">
          <p class="text-sm text-green-800">
            <i class="fas fa-lightbulb mr-2"></i>{{ opt.recommendation }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Optimization {
  severity: string
  optimization_type: string
  category?: string
  description: string
  file_path: string
  line?: number
  code_snippet?: string
  recommendation?: string
}

interface Props {
  optimizations: Optimization[]
  loading: boolean
  summary: any
}

const props = defineProps<Props>()
defineEmits<{ 'scan-file': [path: string]; 'refresh': [] }>()

const categoryFilter = ref('all')

const filteredOptimizations = computed(() => {
  if (categoryFilter.value === 'all') return props.optimizations
  return props.optimizations.filter(o => o.category === categoryFilter.value)
})

function getSeverityBorderClass(severity: string): string {
  const classes: Record<string, string> = {
    critical: 'border-red-500', high: 'border-orange-500',
    medium: 'border-yellow-500', low: 'border-blue-500', info: 'border-gray-400'
  }
  return classes[severity] || 'border-gray-300'
}

function getSeverityBadgeClass(severity: string): string {
  const classes: Record<string, string> = {
    critical: 'bg-red-100 text-red-800', high: 'bg-orange-100 text-orange-800',
    medium: 'bg-yellow-100 text-yellow-800', low: 'bg-blue-100 text-blue-800',
    info: 'bg-gray-100 text-gray-800'
  }
  return classes[severity] || 'bg-gray-100 text-gray-800'
}

function formatOptType(type: string): string {
  return type?.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') || 'Unknown'
}

function formatFilePath(path: string): string {
  const parts = path?.split('/') || []
  return parts.length <= 3 ? path : '.../' + parts.slice(-3).join('/')
}
</script>

<style scoped>
.animate-spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
