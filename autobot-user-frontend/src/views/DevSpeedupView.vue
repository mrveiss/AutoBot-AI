<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * DevSpeedupView - Developer productivity tools and code generation
 * Issue #902 - Developer Speedup Tools
 */

import { ref, computed } from 'vue'
import { useDevSpeedup } from '@/composables/useDevSpeedup'
import type { CodeSnippet, CodeTemplate } from '@/composables/useDevSpeedup'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DevSpeedupView')

const {
  searchResults,
  snippets,
  templates,
  refactorSuggestions,
  generatedTests,
  actionHistory,
  isLoading,
  error,
  quickSearch,
  generateSnippet,
  fetchTemplates,
  suggestRefactor,
  generateBoilerplate,
  generateTests,
  optimizeCode,
  formatCode,
  lintFix,
} = useDevSpeedup({ autoFetch: true })

const activeTab = ref<'search' | 'snippets' | 'templates' | 'actions'>('search')
const searchQuery = ref('')
const searchType = ref<'file' | 'code' | 'symbol' | undefined>(undefined)

const snippetDescription = ref('')
const snippetLanguage = ref('python')

const selectedCategory = ref<string | undefined>(undefined)

const codeInput = ref('')
const actionLanguage = ref('python')
const actionType = ref<'refactor' | 'optimize' | 'format' | 'lint' | 'test'>('refactor')

const supportedLanguages = ['python', 'javascript', 'typescript', 'java', 'go', 'rust', 'cpp']

async function handleSearch() {
  if (!searchQuery.value.trim()) return
  await quickSearch(searchQuery.value, searchType.value)
}

async function handleGenerateSnippet() {
  if (!snippetDescription.value.trim()) return
  const snippet = await generateSnippet(snippetDescription.value, snippetLanguage.value)
  if (snippet) {
    logger.debug('Snippet generated:', snippet.id)
    snippetDescription.value = ''
  }
}

async function handleFetchTemplates() {
  await fetchTemplates(selectedCategory.value)
}

async function handleCodeAction() {
  if (!codeInput.value.trim()) return

  switch (actionType.value) {
    case 'refactor':
      await suggestRefactor(codeInput.value, actionLanguage.value)
      break
    case 'optimize':
      const optimized = await optimizeCode(codeInput.value, actionLanguage.value)
      if (optimized) {
        alert(`Optimized code:\n\n${optimized}`)
      }
      break
    case 'format':
      const formatted = await formatCode(codeInput.value, actionLanguage.value)
      if (formatted) {
        codeInput.value = formatted
        logger.debug('Code formatted')
      }
      break
    case 'lint':
      const fixed = await lintFix(codeInput.value, actionLanguage.value)
      if (fixed) {
        codeInput.value = fixed
        logger.debug('Linting fixed')
      }
      break
    case 'test':
      await generateTests(codeInput.value, actionLanguage.value)
      break
  }
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
  logger.debug('Copied to clipboard')
}

const templateCategories = computed(() => {
  const cats = new Set<string>()
  templates.value.forEach(t => cats.add(t.category))
  return Array.from(cats)
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-primary">Developer Speedup</h2>
        <p class="text-sm text-secondary mt-1">Code search, generation, and productivity tools</p>
      </div>
      <div v-if="actionHistory.length > 0" class="text-right">
        <div class="text-sm text-secondary">Actions Today</div>
        <div class="text-2xl font-bold text-autobot-info">
          {{ actionHistory.length }}
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
          @click="activeTab = 'search'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'search'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Quick Search
        </button>
        <button
          @click="activeTab = 'snippets'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'snippets'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Snippets ({{ snippets.length }})
        </button>
        <button
          @click="activeTab = 'templates'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'templates'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Templates ({{ templates.length }})
        </button>
        <button
          @click="activeTab = 'actions'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'actions'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Quick Actions
        </button>
      </nav>
    </div>

    <!-- Search Tab -->
    <div v-show="activeTab === 'search'" class="space-y-4">
      <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Quick Code Search</h3>
        <div class="space-y-4">
          <div class="flex gap-3">
            <input v-model="searchQuery" type="text" placeholder="Search for files, code, or symbols..." class="flex-1 px-3 py-2 border border-default rounded">
            <select v-model="searchType" class="px-3 py-2 border border-default rounded">
              <option :value="undefined">All Types</option>
              <option value="file">Files</option>
              <option value="code">Code</option>
              <option value="symbol">Symbols</option>
            </select>
            <button @click="handleSearch" :disabled="isLoading || !searchQuery.trim()" class="px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50">
              Search
            </button>
          </div>
        </div>
      </div>

      <div v-if="searchResults.length > 0" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Results ({{ searchResults.length }})</h3>
        <div class="space-y-3">
          <div v-for="(result, idx) in searchResults" :key="idx" class="border border-default rounded p-4 hover:bg-autobot-bg-secondary">
            <div class="flex items-start gap-3">
              <span :class="[
                'px-2 py-1 text-xs font-medium rounded-sm',
                result.type === 'file' ? 'bg-autobot-info-bg text-blue-800' :
                result.type === 'code' ? 'bg-green-100 text-green-800' :
                'bg-purple-100 text-purple-800'
              ]">
                {{ result.type }}
              </span>
              <div class="flex-1">
                <p class="text-sm font-medium text-primary font-mono">{{ result.path }}</p>
                <p v-if="result.line" class="text-xs text-secondary">Line {{ result.line }}</p>
                <p class="text-sm text-secondary mt-2">{{ result.content }}</p>
                <p v-if="result.context" class="text-xs text-secondary mt-1">{{ result.context }}</p>
              </div>
              <div class="text-sm text-secondary">
                Score: {{ result.score.toFixed(2) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="searchQuery && !isLoading" class="text-center py-12 text-secondary">
        No results found
      </div>
    </div>

    <!-- Snippets Tab -->
    <div v-show="activeTab === 'snippets'" class="space-y-4">
      <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Generate Code Snippet</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-primary mb-2">Language</label>
            <select v-model="snippetLanguage" class="w-full px-3 py-2 border border-default rounded">
              <option v-for="lang in supportedLanguages" :key="lang" :value="lang">
                {{ lang.charAt(0).toUpperCase() + lang.slice(1) }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-primary mb-2">Description</label>
            <textarea v-model="snippetDescription" rows="3" placeholder="Describe what you want the code to do..." class="w-full px-3 py-2 border border-default rounded"></textarea>
          </div>
          <button @click="handleGenerateSnippet" :disabled="isLoading || !snippetDescription.trim()" class="w-full px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50">
            Generate Snippet
          </button>
        </div>
      </div>

      <div v-if="snippets.length > 0" class="space-y-4">
        <div v-for="snippet in snippets" :key="snippet.id" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="px-2 py-1 text-xs font-medium bg-autobot-info-bg text-blue-800 rounded-sm">
                  {{ snippet.language }}
                </span>
                <span v-for="tag in snippet.tags" :key="tag" class="px-2 py-1 text-xs font-medium bg-autobot-bg-secondary text-secondary rounded-sm">
                  {{ tag }}
                </span>
              </div>
            </div>
            <button @click="copyToClipboard(snippet.code)" class="text-sm text-autobot-info hover:text-primary-800">
              Copy
            </button>
          </div>
          <p class="text-sm text-secondary mb-3">{{ snippet.description }}</p>
          <pre class="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto"><code>{{ snippet.code }}</code></pre>
          <p class="text-xs text-secondary mt-2">Created: {{ new Date(snippet.created_at).toLocaleString() }}</p>
        </div>
      </div>

      <div v-else class="text-center py-12 text-secondary">
        No snippets yet. Generate your first one above!
      </div>
    </div>

    <!-- Templates Tab -->
    <div v-show="activeTab === 'templates'">
      <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6 mb-4">
        <div class="flex items-center gap-4">
          <select v-model="selectedCategory" class="flex-1 px-3 py-2 border border-default rounded">
            <option :value="undefined">All Categories</option>
            <option v-for="cat in templateCategories" :key="cat" :value="cat">
              {{ cat }}
            </option>
          </select>
          <button @click="handleFetchTemplates" :disabled="isLoading" class="px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50">
            Refresh
          </button>
        </div>
      </div>

      <div v-if="templates.length > 0" class="space-y-4">
        <div v-for="template in templates" :key="template.id" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
          <div class="flex items-start justify-between mb-3">
            <div>
              <h3 class="text-lg font-semibold text-primary">{{ template.name }}</h3>
              <div class="flex items-center gap-2 mt-1">
                <span class="px-2 py-1 text-xs font-medium bg-autobot-info-bg text-blue-800 rounded-sm">
                  {{ template.language }}
                </span>
                <span class="px-2 py-1 text-xs font-medium bg-purple-100 text-purple-800 rounded-sm">
                  {{ template.category }}
                </span>
              </div>
            </div>
            <button @click="copyToClipboard(template.template)" class="text-sm text-autobot-info hover:text-primary-800">
              Copy
            </button>
          </div>
          <p class="text-sm text-secondary mb-3">{{ template.description }}</p>
          <div v-if="template.variables.length > 0" class="mb-3">
            <p class="text-xs text-secondary">Variables: {{ template.variables.join(', ') }}</p>
          </div>
          <pre class="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto"><code>{{ template.template }}</code></pre>
        </div>
      </div>

      <div v-else class="text-center py-12 text-secondary">
        No templates available
      </div>
    </div>

    <!-- Actions Tab -->
    <div v-show="activeTab === 'actions'" class="space-y-4">
      <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Quick Code Actions</h3>
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-primary mb-2">Language</label>
              <select v-model="actionLanguage" class="w-full px-3 py-2 border border-default rounded">
                <option v-for="lang in supportedLanguages" :key="lang" :value="lang">
                  {{ lang.charAt(0).toUpperCase() + lang.slice(1) }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-primary mb-2">Action</label>
              <select v-model="actionType" class="w-full px-3 py-2 border border-default rounded">
                <option value="refactor">Suggest Refactorings</option>
                <option value="optimize">Optimize Code</option>
                <option value="format">Format Code</option>
                <option value="lint">Fix Linting Issues</option>
                <option value="test">Generate Tests</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-primary mb-2">Code</label>
            <textarea v-model="codeInput" rows="12" placeholder="Paste your code here..." class="w-full px-3 py-2 border border-default rounded font-mono text-sm"></textarea>
          </div>

          <button @click="handleCodeAction" :disabled="isLoading || !codeInput.trim()" class="w-full px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50">
            {{ isLoading ? 'Processing...' : 'Run Action' }}
          </button>
        </div>
      </div>

      <!-- Refactor Suggestions -->
      <div v-if="actionType === 'refactor' && refactorSuggestions.length > 0" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Refactor Suggestions ({{ refactorSuggestions.length }})</h3>
        <div class="space-y-4">
          <div v-for="(suggestion, idx) in refactorSuggestions" :key="idx" class="border border-default rounded p-4">
            <div class="flex items-start justify-between mb-2">
              <div class="flex items-center gap-2">
                <span class="px-2 py-1 text-xs font-medium bg-autobot-info-bg text-blue-800 rounded-sm">
                  {{ suggestion.type }}
                </span>
                <span :class="[
                  'px-2 py-1 text-xs font-medium rounded-sm',
                  suggestion.impact === 'high' ? 'bg-autobot-error-bg text-autobot-error' :
                  suggestion.impact === 'medium' ? 'bg-autobot-warning-bg text-autobot-warning' :
                  'bg-autobot-bg-secondary text-secondary'
                ]">
                  {{ suggestion.impact }} impact
                </span>
              </div>
            </div>
            <p class="text-sm text-primary mb-3">{{ suggestion.description }}</p>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-secondary mb-1">Before:</p>
                <pre class="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto"><code>{{ suggestion.before }}</code></pre>
              </div>
              <div>
                <p class="text-xs text-secondary mb-1">After:</p>
                <pre class="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-x-auto"><code>{{ suggestion.after }}</code></pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Generated Tests -->
      <div v-if="actionType === 'test' && generatedTests.length > 0" class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
        <h3 class="text-lg font-semibold text-primary mb-4">Generated Tests ({{ generatedTests.length }})</h3>
        <div class="space-y-4">
          <div v-for="(test, idx) in generatedTests" :key="idx" class="border border-default rounded p-4">
            <div class="flex items-start justify-between mb-2">
              <div>
                <h4 class="text-sm font-semibold text-primary">{{ test.name }}</h4>
                <span class="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-sm">
                  {{ test.framework }}
                </span>
              </div>
              <button @click="copyToClipboard(test.code)" class="text-sm text-autobot-info hover:text-primary-800">
                Copy
              </button>
            </div>
            <p class="text-sm text-secondary mb-3">{{ test.description }}</p>
            <pre class="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto"><code>{{ test.code }}</code></pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
