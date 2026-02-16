<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * CodeIntelligenceView - Code analysis and quality monitoring
 * Issue #899 - Code Intelligence Tools
 */

import { ref, computed, onMounted } from 'vue'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import type { CodeAnalysisRequest } from '@/composables/useCodeIntelligence'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodeIntelligenceView')

const {
  currentAnalysis,
  analysisHistory,
  qualityScore,
  healthScore,
  suggestions,
  trends,
  isLoading,
  error,
  analyzeCode,
  getQualityScore,
  getSuggestions,
  getHealthScore,
  getTrends,
  getAnalysisHistory,
  deleteAnalysis,
} = useCodeIntelligence({ autoFetch: true })

const activeTab = ref<'analysis' | 'quality' | 'suggestions' | 'history'>('analysis')
const codeInput = ref('')
const languageInput = ref('python')
const filenameInput = ref('')

const supportedLanguages = ['python', 'javascript', 'typescript', 'java', 'go', 'rust', 'cpp']

async function handleAnalyze() {
  if (!codeInput.value.trim()) return

  const request: CodeAnalysisRequest = {
    code: codeInput.value,
    language: languageInput.value,
    filename: filenameInput.value || undefined,
    include_suggestions: true,
  }

  const result = await analyzeCode(request)
  if (result) {
    logger.debug('Analysis complete, switching to quality tab')
    activeTab.value = 'quality'
  }
}

async function handleGetSuggestions() {
  if (!codeInput.value.trim()) return
  await getSuggestions(codeInput.value, languageInput.value)
  activeTab.value = 'suggestions'
}

async function handleDeleteAnalysis(id: string) {
  if (confirm('Delete this analysis?')) {
    await deleteAnalysis(id)
  }
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-success-600'
  if (score >= 60) return 'text-warning-600'
  return 'text-danger-600'
}

function getSeverityColor(severity: string): string {
  switch (severity) {
    case 'critical': return 'bg-danger-100 text-danger-800'
    case 'high': return 'bg-warning-100 text-warning-800'
    case 'medium': return 'bg-yellow-100 text-yellow-800'
    case 'low': return 'bg-blue-100 text-blue-800'
    default: return 'bg-gray-100 text-gray-600'
  }
}

onMounted(async () => {
  await Promise.all([getHealthScore(), getTrends(), getAnalysisHistory()])
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Code Intelligence</h2>
        <p class="text-sm text-gray-500 mt-1">Analyze code quality, get suggestions, and monitor health</p>
      </div>
      <div v-if="healthScore" class="text-right">
        <div class="text-sm text-gray-500">Codebase Health</div>
        <div :class="['text-2xl font-bold', getScoreColor(healthScore.health_score)]">
          {{ healthScore.health_score.toFixed(0) }}%
        </div>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="bg-danger-50 border border-danger-200 rounded-lg p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-danger-600 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-danger-800">Error</h3>
          <p class="text-sm text-danger-700 mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="activeTab = 'analysis'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'analysis'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Analysis
        </button>
        <button
          @click="activeTab = 'quality'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'quality'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Quality Score
        </button>
        <button
          @click="activeTab = 'suggestions'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'suggestions'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Suggestions ({{ suggestions.length }})
        </button>
        <button
          @click="activeTab = 'history'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'history'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          History ({{ analysisHistory.length }})
        </button>
      </nav>
    </div>

    <!-- Analysis Tab -->
    <div v-show="activeTab === 'analysis'" class="space-y-4">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Code Analysis</h3>

        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Language</label>
              <select v-model="languageInput" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option v-for="lang in supportedLanguages" :key="lang" :value="lang">
                  {{ lang.charAt(0).toUpperCase() + lang.slice(1) }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">Filename (optional)</label>
              <input v-model="filenameInput" type="text" placeholder="example.py" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Code</label>
            <textarea v-model="codeInput" rows="15" placeholder="Paste your code here..." class="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"></textarea>
          </div>

          <div class="flex gap-3">
            <button @click="handleAnalyze" :disabled="isLoading || !codeInput.trim()" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
              {{ isLoading ? 'Analyzing...' : 'Analyze Code' }}
            </button>
            <button @click="handleGetSuggestions" :disabled="isLoading || !codeInput.trim()" class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
              Get Suggestions
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Quality Tab -->
    <div v-show="activeTab === 'quality'">
      <div v-if="!currentAnalysis && !qualityScore" class="text-center py-12 text-gray-500">
        Analyze code to see quality metrics
      </div>

      <div v-else class="space-y-6">
        <div v-if="currentAnalysis" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold text-gray-900">Quality Score</h3>
            <div :class="['text-3xl font-bold', getScoreColor(currentAnalysis.quality_score)]">
              {{ currentAnalysis.quality_score.toFixed(0) }}/100
            </div>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div v-for="(value, key) in currentAnalysis.metrics" :key="key" class="bg-gray-50 rounded-lg p-4">
              <div class="text-sm text-gray-500 mb-1">{{ key.replace(/_/g, ' ') }}</div>
              <div class="text-xl font-semibold text-gray-900">{{ value }}</div>
            </div>
          </div>
        </div>

        <div v-if="currentAnalysis && currentAnalysis.issues.length > 0" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Issues ({{ currentAnalysis.issues.length }})</h3>
          <div class="space-y-3">
            <div v-for="(issue, idx) in currentAnalysis.issues" :key="idx" class="border border-gray-200 rounded-lg p-4">
              <div class="flex items-start gap-3">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getSeverityColor(issue.severity)]">
                  {{ issue.severity }}
                </span>
                <div class="flex-1">
                  <p class="text-sm font-medium text-gray-900">{{ issue.message }}</p>
                  <p v-if="issue.line_number" class="text-xs text-gray-500 mt-1">Line {{ issue.line_number }}</p>
                  <p v-if="issue.suggestion" class="text-sm text-gray-600 mt-2">{{ issue.suggestion }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Suggestions Tab -->
    <div v-show="activeTab === 'suggestions'">
      <div v-if="suggestions.length === 0" class="text-center py-12 text-gray-500">
        No suggestions available. Analyze code first.
      </div>

      <div v-else class="space-y-4">
        <div v-for="suggestion in suggestions" :key="suggestion.id" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div class="flex items-start justify-between mb-3">
            <div>
              <h3 class="text-lg font-semibold text-gray-900">{{ suggestion.title }}</h3>
              <div class="flex items-center gap-2 mt-1">
                <span class="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                  {{ suggestion.type }}
                </span>
                <span :class="[
                  'px-2 py-1 text-xs font-medium rounded-full',
                  suggestion.priority === 'high' ? 'bg-danger-100 text-danger-800' :
                  suggestion.priority === 'medium' ? 'bg-warning-100 text-warning-800' :
                  'bg-gray-100 text-gray-600'
                ]">
                  {{ suggestion.priority }} priority
                </span>
              </div>
            </div>
          </div>
          <p class="text-sm text-gray-600 mb-3">{{ suggestion.description }}</p>
          <div v-if="suggestion.impact" class="text-sm text-gray-700 bg-gray-50 rounded p-3">
            <strong>Impact:</strong> {{ suggestion.impact }}
          </div>
        </div>
      </div>
    </div>

    <!-- History Tab -->
    <div v-show="activeTab === 'history'">
      <div v-if="analysisHistory.length === 0" class="text-center py-12 text-gray-500">
        No analysis history yet
      </div>

      <div v-else class="bg-white rounded-lg shadow-sm border border-gray-200">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Filename</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Language</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Quality Score</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Issues</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="analysis in analysisHistory" :key="analysis.id" class="hover:bg-gray-50">
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {{ analysis.filename || 'Untitled' }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ analysis.language }}</td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="['text-sm font-semibold', getScoreColor(analysis.quality_score)]">
                    {{ analysis.quality_score.toFixed(0) }}
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                  {{ analysis.issues.length }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {{ new Date(analysis.timestamp).toLocaleString() }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">
                  <button @click="handleDeleteAnalysis(analysis.id)" class="text-danger-600 hover:text-danger-800">
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
