<template>
  <div class="health-score-cards">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <!-- Overall Health Score -->
      <div class="score-card" :class="getCardBorderClass(healthScore.grade)">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Code Health</h3>
            <div class="mt-2 flex items-baseline">
              <p class="text-3xl font-extrabold" :class="getScoreTextClass(healthScore.grade)">
                {{ loading ? '-' : healthScore.score }}
              </p>
              <span class="ml-2 text-lg font-semibold" :class="getGradeClass(healthScore.grade)">
                {{ healthScore.grade }}
              </span>
            </div>
            <p class="mt-2 text-sm text-gray-600">
              {{ healthScore.total_issues || 0 }} issues found
            </p>
          </div>
          <div class="flex-shrink-0">
            <div class="score-circle" :class="getCircleClass(healthScore.grade)">
              <i class="fas fa-heartbeat text-2xl"></i>
            </div>
          </div>
        </div>
        <div v-if="loading" class="loading-overlay">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
      </div>

      <!-- Security Score -->
      <div class="score-card" :class="getCardBorderClass(securityScore.grade)">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Security</h3>
            <div class="mt-2 flex items-baseline">
              <p class="text-3xl font-extrabold" :class="getScoreTextClass(securityScore.grade)">
                {{ loading ? '-' : securityScore.security_score || securityScore.score }}
              </p>
              <span class="ml-2 text-lg font-semibold" :class="getGradeClass(securityScore.grade)">
                {{ securityScore.grade }}
              </span>
            </div>
            <p class="mt-2 text-sm" :class="getRiskClass(securityScore.risk_level)">
              {{ formatRiskLevel(securityScore.risk_level) }}
            </p>
          </div>
          <div class="flex-shrink-0">
            <div class="score-circle" :class="getCircleClass(securityScore.grade)">
              <i class="fas fa-shield-alt text-2xl"></i>
            </div>
          </div>
        </div>
        <div v-if="loading" class="loading-overlay">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
      </div>

      <!-- Performance Score -->
      <div class="score-card" :class="getCardBorderClass(performanceScore.grade)">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Performance</h3>
            <div class="mt-2 flex items-baseline">
              <p class="text-3xl font-extrabold" :class="getScoreTextClass(performanceScore.grade)">
                {{ loading ? '-' : performanceScore.performance_score || performanceScore.score }}
              </p>
              <span class="ml-2 text-lg font-semibold" :class="getGradeClass(performanceScore.grade)">
                {{ performanceScore.grade }}
              </span>
            </div>
            <p class="mt-2 text-sm text-gray-600">
              {{ performanceScore.total_issues || 0 }} optimizations
            </p>
          </div>
          <div class="flex-shrink-0">
            <div class="score-circle" :class="getCircleClass(performanceScore.grade)">
              <i class="fas fa-tachometer-alt text-2xl"></i>
            </div>
          </div>
        </div>
        <div v-if="loading" class="loading-overlay">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
      </div>

      <!-- Redis Score -->
      <div class="score-card" :class="getCardBorderClass(redisScore.grade)">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Redis</h3>
            <div class="mt-2 flex items-baseline">
              <p class="text-3xl font-extrabold" :class="getScoreTextClass(redisScore.grade)">
                {{ loading ? '-' : redisScore.health_score || redisScore.score }}
              </p>
              <span class="ml-2 text-lg font-semibold" :class="getGradeClass(redisScore.grade)">
                {{ redisScore.grade }}
              </span>
            </div>
            <p class="mt-2 text-sm text-gray-600">
              {{ redisScore.total_optimizations || 0 }} suggestions
            </p>
          </div>
          <div class="flex-shrink-0">
            <div class="score-circle" :class="getCircleClass(redisScore.grade)">
              <i class="fas fa-database text-2xl"></i>
            </div>
          </div>
        </div>
        <div v-if="loading" class="loading-overlay">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
      </div>
    </div>

    <!-- Refresh Button -->
    <div class="flex justify-end mt-4">
      <button
        @click="$emit('refresh')"
        :disabled="loading"
        class="text-sm text-indigo-600 hover:text-indigo-800 flex items-center"
      >
        <i class="fas fa-sync-alt mr-1" :class="{ 'animate-spin': loading }"></i>
        Refresh Scores
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface ScoreData {
  score?: number
  health_score?: number
  security_score?: number
  performance_score?: number
  grade: string
  total_issues?: number
  total_optimizations?: number
  risk_level?: string
}

interface Props {
  healthScore: ScoreData
  securityScore: ScoreData
  performanceScore: ScoreData
  redisScore: ScoreData
  loading: boolean
}

defineProps<Props>()
defineEmits<{
  refresh: []
}>()

function getCardBorderClass(grade: string): string {
  const classes: Record<string, string> = {
    'A': 'border-l-4 border-green-500',
    'B': 'border-l-4 border-blue-500',
    'C': 'border-l-4 border-yellow-500',
    'D': 'border-l-4 border-orange-500',
    'F': 'border-l-4 border-red-500'
  }
  return classes[grade] || 'border-l-4 border-gray-300'
}

function getScoreTextClass(grade: string): string {
  const classes: Record<string, string> = {
    'A': 'text-green-600',
    'B': 'text-blue-600',
    'C': 'text-yellow-600',
    'D': 'text-orange-600',
    'F': 'text-red-600'
  }
  return classes[grade] || 'text-gray-600'
}

function getGradeClass(grade: string): string {
  const classes: Record<string, string> = {
    'A': 'text-green-500',
    'B': 'text-blue-500',
    'C': 'text-yellow-500',
    'D': 'text-orange-500',
    'F': 'text-red-500'
  }
  return classes[grade] || 'text-gray-400'
}

function getCircleClass(grade: string): string {
  const classes: Record<string, string> = {
    'A': 'bg-green-100 text-green-600',
    'B': 'bg-blue-100 text-blue-600',
    'C': 'bg-yellow-100 text-yellow-600',
    'D': 'bg-orange-100 text-orange-600',
    'F': 'bg-red-100 text-red-600'
  }
  return classes[grade] || 'bg-gray-100 text-gray-400'
}

function getRiskClass(level: string | undefined): string {
  const classes: Record<string, string> = {
    'low': 'text-green-600',
    'medium': 'text-yellow-600',
    'high': 'text-orange-600',
    'critical': 'text-red-600'
  }
  return classes[level || ''] || 'text-gray-600'
}

function formatRiskLevel(level: string | undefined): string {
  if (!level || level === 'unknown') return 'No data'
  return `${level.charAt(0).toUpperCase() + level.slice(1)} risk`
}
</script>

<style scoped>
.score-card {
  @apply bg-white rounded-lg shadow-md p-6 relative overflow-hidden transition-all hover:shadow-lg;
}

.score-circle {
  @apply w-14 h-14 rounded-full flex items-center justify-center;
}

.loading-overlay {
  @apply absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
