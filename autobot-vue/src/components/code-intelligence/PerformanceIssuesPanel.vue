<template>
  <div class="performance-issues-panel">
    <!-- Summary Header -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <div class="flex flex-wrap items-center justify-between">
        <div>
          <h2 class="text-xl font-semibold text-blueGray-700">Performance Issues</h2>
          <p class="text-sm text-blueGray-500 mt-1">
            {{ findings.length }} performance optimizations identified
          </p>
        </div>
        <div class="flex items-center space-x-4 mt-4 sm:mt-0">
          <select
            v-model="categoryFilter"
            class="px-3 py-2 border border-blueGray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All Categories</option>
            <option value="complexity">Complexity</option>
            <option value="async">Async/Await</option>
            <option value="loop">Loop Operations</option>
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
      <p class="text-blueGray-600">Analyzing performance patterns...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredFindings.length === 0" class="bg-white rounded-lg shadow-md p-12 text-center">
      <i class="fas fa-tachometer-alt text-4xl text-green-500 mb-4"></i>
      <p class="text-lg font-medium text-blueGray-700">No performance issues found</p>
      <p class="text-sm text-blueGray-500 mt-2">Your code is well optimized!</p>
    </div>

    <!-- Findings List -->
    <div v-else class="space-y-4">
      <div
        v-for="(finding, index) in filteredFindings"
        :key="index"
        class="bg-white rounded-lg shadow-md p-6 border-l-4"
        :class="getSeverityBorderClass(finding.severity)"
      >
        <div class="flex items-center flex-wrap gap-2 mb-2">
          <span
            class="px-2 py-1 text-xs font-medium rounded uppercase"
            :class="getSeverityBadgeClass(finding.severity)"
          >
            {{ finding.severity }}
          </span>
          <span class="text-sm font-medium text-blueGray-700">
            {{ formatIssueType(finding.issue_type) }}
          </span>
        </div>
        <p class="text-sm text-blueGray-600">{{ finding.description }}</p>
        <div class="mt-3 flex items-center text-sm text-blueGray-500">
          <i class="fas fa-file-code mr-2"></i>
          <span class="font-mono">{{ formatFilePath(finding.file_path) }}</span>
          <span v-if="finding.line" class="ml-2">:{{ finding.line }}</span>
        </div>
        <div v-if="finding.recommendation" class="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
          <p class="text-sm text-blue-800">
            <i class="fas fa-lightbulb mr-2"></i>{{ finding.recommendation }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Finding {
  severity: string
  issue_type: string
  description: string
  file_path: string
  line?: number
  recommendation?: string
}

interface Props {
  findings: Finding[]
  loading: boolean
  summary: any
}

const props = defineProps<Props>()
defineEmits<{ 'scan-file': [path: string]; 'refresh': [] }>()

const categoryFilter = ref('all')

const filteredFindings = computed(() => {
  if (categoryFilter.value === 'all') return props.findings
  return props.findings.filter(f => f.issue_type?.toLowerCase().includes(categoryFilter.value))
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

function formatIssueType(type: string): string {
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
