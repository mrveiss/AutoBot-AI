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
  if (score >= 80) return 'text-autobot-success'
  if (score >= 60) return 'text-autobot-warning'
  return 'text-autobot-error'
}

function getSeverityColor(severity: string): string {
  switch (severity) {
    case 'critical': return 'bg-autobot-error-bg text-autobot-error'
    case 'high': return 'bg-autobot-warning-bg text-autobot-warning'
    case 'medium': return 'bg-yellow-100 text-yellow-800'
    case 'low': return 'bg-autobot-info-bg text-blue-800'
    default: return 'bg-autobot-bg-secondary text-secondary'
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
        <h2 class="text-2xl font-bold text-primary">Code Intelligence</h2>
        <p class="text-sm text-secondary mt-1">Analyze code quality, get suggestions, and monitor health</p>
      </div>
      <div v-if="healthScore" class="text-right">
        <div class="text-sm text-secondary">Codebase Health</div>
        <div :class="['text-2xl font-bold', getScoreColor(healthScore.health_score)]">
          {{ healthScore.health_score.toFixed(0) }}%
        </div>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="bg-autobot-error-bg border border-autobot-error rounded p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-autobot-error mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-autobot-error">Error</h3>
          <p class="text-sm text-autobot-error mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-default">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="activeTab = 'analysis'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'analysis'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Analysis
        </button>
        <button
          @click="activeTab = 'quality'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'quality'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Quality Score
        </button>
        <button
          @click="activeTab = 'suggestions'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'suggestions'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Suggestions ({{ suggestions.length }})
        </button>
        <button
          @click="activeTab = 'history'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'history'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          History ({{ analysisHistory.length }})
        </button>
      </nav>
    </div>

    <!-- Analysis Tab -->
    <div v-show="activeTab === 'analysis'" class="space-y-4">
      <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Code Analysis</h3>

        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-primary mb-2">Language</label>
              <select v-model="languageInput" class="w-full px-3 py-2 border border-default rounded">
                <option v-for="lang in supportedLanguages" :key="lang" :value="lang">
                  {{ lang.charAt(0).toUpperCase() + lang.slice(1) }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-primary mb-2">Filename (optional)</label>
              <input v-model="filenameInput" type="text" placeholder="example.py" class="w-full px-3 py-2 border border-default rounded">
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-primary mb-2">Code</label>
            <textarea v-model="codeInput" rows="15" placeholder="Paste your code here..." class="w-full px-3 py-2 border border-default rounded font-mono text-sm"></textarea>
          </div>

          <div class="flex gap-3">
            <button @click="handleAnalyze" :disabled="isLoading || !codeInput.trim()" class="px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50">
              {{ isLoading ? 'Analyzing...' : 'Analyze Code' }}
            </button>
            <button @click="handleGetSuggestions" :disabled="isLoading || !codeInput.trim()" class="px-4 py-2 text-sm font-medium text-primary bg-autobot-bg-card border border-default rounded hover:bg-autobot-bg-secondary">
              Get Suggestions
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Quality Tab -->
    <div v-show="activeTab === 'quality'">
      <div v-if="!currentAnalysis && !qualityScore" class="text-center py-12 text-secondary">
        Analyze code to see quality metrics
      </div>

      <div v-else class="space-y-6">
        <div v-if="currentAnalysis" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold text-primary">Quality Score</h3>
            <div :class="['text-3xl font-bold', getScoreColor(currentAnalysis.quality_score)]">
              {{ currentAnalysis.quality_score.toFixed(0) }}/100
            </div>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div v-for="(value, key) in currentAnalysis.metrics" :key="key" class="bg-autobot-bg-secondary rounded p-4">
              <div class="text-sm text-secondary mb-1">{{ key.replace(/_/g, ' ') }}</div>
              <div class="text-xl font-semibold text-primary">{{ value }}</div>
            </div>
          </div>
        </div>

        <div v-if="currentAnalysis && currentAnalysis.issues.length > 0" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
          <h3 class="text-lg font-semibold text-primary mb-4">Issues ({{ currentAnalysis.issues.length }})</h3>
          <div class="space-y-3">
            <div v-for="(issue, idx) in currentAnalysis.issues" :key="idx" class="border border-default rounded p-4">
              <div class="flex items-start gap-3">
                <span :class="['px-2 py-1 text-xs font-medium rounded-sm', getSeverityColor(issue.severity)]">
                  {{ issue.severity }}
                </span>
                <div class="flex-1">
                  <p class="text-sm font-medium text-primary">{{ issue.message }}</p>
                  <p v-if="issue.line_number" class="text-xs text-secondary mt-1">Line {{ issue.line_number }}</p>
                  <p v-if="issue.suggestion" class="text-sm text-secondary mt-2">{{ issue.suggestion }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Suggestions Tab -->
    <div v-show="activeTab === 'suggestions'">
      <div v-if="suggestions.length === 0" class="text-center py-12 text-secondary">
        No suggestions available. Analyze code first.
      </div>

      <div v-else class="space-y-4">
        <div v-for="suggestion in suggestions" :key="suggestion.id" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
          <div class="flex items-start justify-between mb-3">
            <div>
              <h3 class="text-lg font-semibold text-primary">{{ suggestion.title }}</h3>
              <div class="flex items-center gap-2 mt-1">
                <span class="px-2 py-1 text-xs font-medium bg-autobot-info-bg text-blue-800 rounded-sm">
                  {{ suggestion.type }}
                </span>
                <span :class="[
                  'px-2 py-1 text-xs font-medium rounded-sm',
                  suggestion.priority === 'high' ? 'bg-autobot-error-bg text-autobot-error' :
                  suggestion.priority === 'medium' ? 'bg-autobot-warning-bg text-autobot-warning' :
                  'bg-autobot-bg-secondary text-secondary'
                ]">
                  {{ suggestion.priority }} priority
                </span>
              </div>
            </div>
          </div>
          <p class="text-sm text-secondary mb-3">{{ suggestion.description }}</p>
          <div v-if="suggestion.impact" class="text-sm text-primary bg-autobot-bg-secondary rounded p-3">
            <strong>Impact:</strong> {{ suggestion.impact }}
          </div>
        </div>
      </div>
    </div>

    <!-- History Tab -->
    <div v-show="activeTab === 'history'">
      <div v-if="analysisHistory.length === 0" class="text-center py-12 text-secondary">
        No analysis history yet
      </div>

      <div v-else class="bg-autobot-bg-card rounded shadow-sm border border-default">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-autobot-bg-secondary">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase">Filename</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase">Language</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase">Quality Score</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase">Issues</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase">Date</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-secondary uppercase">Actions</th>
              </tr>
            </thead>
            <tbody class="bg-autobot-bg-card divide-y divide-gray-200">
              <tr v-for="analysis in analysisHistory" :key="analysis.id" class="hover:bg-autobot-bg-secondary">
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-primary">
                  {{ analysis.filename || 'Untitled' }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-secondary">{{ analysis.language }}</td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="['text-sm font-semibold', getScoreColor(analysis.quality_score)]">
                    {{ analysis.quality_score.toFixed(0) }}
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-secondary">
                  {{ analysis.issues.length }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-secondary">
                  {{ new Date(analysis.timestamp).toLocaleString() }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">
                  <button @click="handleDeleteAnalysis(analysis.id)" class="text-autobot-error hover:text-autobot-error">
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
