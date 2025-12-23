<template>
  <div class="security-findings-panel">
    <!-- Summary Header -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <div class="flex flex-wrap items-center justify-between">
        <div>
          <h2 class="text-xl font-semibold text-blueGray-700">Security Vulnerabilities</h2>
          <p class="text-sm text-blueGray-500 mt-1">
            {{ findings.length }} vulnerabilities detected
          </p>
        </div>
        <div class="flex items-center space-x-4 mt-4 sm:mt-0">
          <!-- Severity Filter -->
          <select
            v-model="severityFilter"
            class="px-3 py-2 border border-blueGray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
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

      <!-- Severity Breakdown -->
      <div class="grid grid-cols-5 gap-4 mt-6" v-if="summary">
        <div
          v-for="(count, severity) in severityBreakdown"
          :key="severity"
          class="text-center p-3 rounded-lg"
          :class="getSeverityBgClass(severity)"
        >
          <p class="text-2xl font-bold" :class="getSeverityTextClass(severity)">{{ count }}</p>
          <p class="text-sm capitalize text-blueGray-600">{{ severity }}</p>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="bg-white rounded-lg shadow-md p-12 text-center">
      <i class="fas fa-spinner fa-spin text-4xl text-indigo-500 mb-4"></i>
      <p class="text-blueGray-600">Analyzing security vulnerabilities...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredFindings.length === 0" class="bg-white rounded-lg shadow-md p-12 text-center">
      <i class="fas fa-shield-alt text-4xl text-green-500 mb-4"></i>
      <p class="text-lg font-medium text-blueGray-700">No vulnerabilities found</p>
      <p class="text-sm text-blueGray-500 mt-2">
        {{ severityFilter === 'all' ? 'Your code appears secure!' : `No ${severityFilter} severity issues found.` }}
      </p>
    </div>

    <!-- Findings List -->
    <div v-else class="space-y-4">
      <div
        v-for="(finding, index) in filteredFindings"
        :key="index"
        class="bg-white rounded-lg shadow-md p-6 border-l-4"
        :class="getSeverityBorderClass(finding.severity)"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center">
              <span
                class="px-2 py-1 text-xs font-medium rounded uppercase"
                :class="getSeverityBadgeClass(finding.severity)"
              >
                {{ finding.severity }}
              </span>
              <span class="ml-3 text-sm font-medium text-blueGray-700">
                {{ formatVulnerabilityType(finding.vulnerability_type) }}
              </span>
              <span
                v-if="finding.owasp_category"
                class="ml-3 px-2 py-1 text-xs bg-indigo-100 text-indigo-700 rounded"
              >
                {{ finding.owasp_category }}
              </span>
            </div>
            <p class="mt-2 text-sm text-blueGray-600">{{ finding.description }}</p>
            <div class="mt-3 flex items-center text-sm text-blueGray-500">
              <i class="fas fa-file-code mr-2"></i>
              <span class="font-mono">{{ formatFilePath(finding.file_path) }}</span>
              <span v-if="finding.line" class="ml-2">:{{ finding.line }}</span>
            </div>
            <div v-if="finding.code_snippet" class="mt-3 p-3 bg-blueGray-50 rounded-lg font-mono text-xs overflow-x-auto">
              <pre>{{ finding.code_snippet }}</pre>
            </div>
            <div v-if="finding.recommendation" class="mt-3 p-3 bg-green-50 rounded-lg border border-green-200">
              <p class="text-sm text-green-800">
                <i class="fas fa-lightbulb mr-2"></i>
                {{ finding.recommendation }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="filteredFindings.length > pageSize" class="mt-6 flex justify-center">
      <nav class="flex items-center space-x-2">
        <button
          @click="currentPage--"
          :disabled="currentPage === 1"
          class="px-3 py-2 rounded-lg border border-blueGray-300 disabled:opacity-50"
        >
          <i class="fas fa-chevron-left"></i>
        </button>
        <span class="px-4 py-2 text-sm text-blueGray-600">
          Page {{ currentPage }} of {{ totalPages }}
        </span>
        <button
          @click="currentPage++"
          :disabled="currentPage === totalPages"
          class="px-3 py-2 rounded-lg border border-blueGray-300 disabled:opacity-50"
        >
          <i class="fas fa-chevron-right"></i>
        </button>
      </nav>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Finding {
  severity: string
  vulnerability_type: string
  description: string
  file_path: string
  line?: number
  code_snippet?: string
  recommendation?: string
  owasp_category?: string
}

interface Summary {
  by_severity?: Record<string, number>
  total_findings?: number
}

interface Props {
  findings: Finding[]
  loading: boolean
  summary: Summary | null
}

const props = defineProps<Props>()
defineEmits<{
  'scan-file': [path: string]
  'refresh': []
}>()

const severityFilter = ref('all')
const currentPage = ref(1)
const pageSize = 10

const filteredFindings = computed(() => {
  if (severityFilter.value === 'all') return props.findings
  return props.findings.filter(f => f.severity === severityFilter.value)
})

const totalPages = computed(() => Math.ceil(filteredFindings.value.length / pageSize))

const severityBreakdown = computed(() => {
  if (props.summary?.by_severity) return props.summary.by_severity

  const breakdown: Record<string, number> = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0
  }

  props.findings.forEach(f => {
    if (breakdown[f.severity] !== undefined) {
      breakdown[f.severity]++
    }
  })

  return breakdown
})

function getSeverityBorderClass(severity: string): string {
  const classes: Record<string, string> = {
    critical: 'border-red-500',
    high: 'border-orange-500',
    medium: 'border-yellow-500',
    low: 'border-blue-500',
    info: 'border-gray-400'
  }
  return classes[severity] || 'border-gray-300'
}

function getSeverityBadgeClass(severity: string): string {
  const classes: Record<string, string> = {
    critical: 'bg-red-100 text-red-800',
    high: 'bg-orange-100 text-orange-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-blue-100 text-blue-800',
    info: 'bg-gray-100 text-gray-800'
  }
  return classes[severity] || 'bg-gray-100 text-gray-800'
}

function getSeverityBgClass(severity: string): string {
  const classes: Record<string, string> = {
    critical: 'bg-red-50',
    high: 'bg-orange-50',
    medium: 'bg-yellow-50',
    low: 'bg-blue-50',
    info: 'bg-gray-50'
  }
  return classes[severity] || 'bg-gray-50'
}

function getSeverityTextClass(severity: string): string {
  const classes: Record<string, string> = {
    critical: 'text-red-600',
    high: 'text-orange-600',
    medium: 'text-yellow-600',
    low: 'text-blue-600',
    info: 'text-gray-600'
  }
  return classes[severity] || 'text-gray-600'
}

function formatVulnerabilityType(type: string): string {
  if (!type) return 'Unknown'
  return type.split('_').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ')
}

function formatFilePath(path: string): string {
  if (!path) return 'Unknown'
  const parts = path.split('/')
  if (parts.length <= 3) return path
  return '.../' + parts.slice(-3).join('/')
}
</script>

<style scoped>
.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
