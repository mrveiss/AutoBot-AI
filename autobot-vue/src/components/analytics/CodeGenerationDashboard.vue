<template>
  <div class="code-generation-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <h2>LLM-Powered Code Generation</h2>
      <p class="subtitle">Generate and refactor code using AI</p>
    </div>

    <!-- Stats Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon generation">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.generation.total }}</span>
          <span class="stat-label">Generated</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon refactor">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.refactoring.total }}</span>
          <span class="stat-label">Refactored</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon tokens">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ formatTokens(totalTokens) }}</span>
          <span class="stat-label">Tokens Used</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon success">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ successRate }}%</span>
          <span class="stat-label">Success Rate</span>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="main-content">
      <!-- Left Panel: Input -->
      <div class="input-panel">
        <!-- Mode Toggle -->
        <div class="mode-toggle">
          <button
            :class="['mode-btn', { active: mode === 'generate' }]"
            @click="mode = 'generate'"
          >
            Generate Code
          </button>
          <button
            :class="['mode-btn', { active: mode === 'refactor' }]"
            @click="mode = 'refactor'"
          >
            Refactor Code
          </button>
        </div>

        <!-- Generate Mode -->
        <div v-if="mode === 'generate'" class="generate-form">
          <div class="form-group">
            <label>Description</label>
            <textarea
              v-model="generateRequest.description"
              placeholder="Describe what code you want to generate..."
              rows="4"
            ></textarea>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Language</label>
              <select v-model="generateRequest.language">
                <option value="python">Python</option>
                <option value="typescript">TypeScript</option>
                <option value="javascript">JavaScript</option>
                <option value="vue">Vue</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label>Additional Context (optional)</label>
            <textarea
              v-model="generateRequest.context"
              placeholder="Any additional requirements or context..."
              rows="2"
            ></textarea>
          </div>

          <div class="form-group">
            <label>Existing Code to Integrate (optional)</label>
            <textarea
              v-model="generateRequest.existing_code"
              placeholder="Paste existing code to integrate with..."
              rows="4"
              class="code-input"
            ></textarea>
          </div>

          <button
            class="submit-btn"
            :disabled="!generateRequest.description || processing"
            @click="generateCode"
          >
            <span v-if="processing" class="spinner"></span>
            {{ processing ? 'Generating...' : 'Generate Code' }}
          </button>
        </div>

        <!-- Refactor Mode -->
        <div v-else class="refactor-form">
          <div class="form-group">
            <label>Code to Refactor</label>
            <textarea
              v-model="refactorRequest.code"
              placeholder="Paste code to refactor..."
              rows="8"
              class="code-input"
            ></textarea>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Language</label>
              <select v-model="refactorRequest.language">
                <option value="python">Python</option>
                <option value="typescript">TypeScript</option>
                <option value="javascript">JavaScript</option>
                <option value="vue">Vue</option>
              </select>
            </div>

            <div class="form-group">
              <label>Refactoring Type</label>
              <select v-model="refactorRequest.refactoring_type">
                <option v-for="rt in refactoringTypes" :key="rt.id" :value="rt.id">
                  {{ rt.name }}
                </option>
              </select>
            </div>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input type="checkbox" v-model="refactorRequest.preserve_comments" />
              Preserve comments
            </label>
          </div>

          <button
            class="submit-btn"
            :disabled="!refactorRequest.code || processing"
            @click="refactorCode"
          >
            <span v-if="processing" class="spinner"></span>
            {{ processing ? 'Refactoring...' : 'Refactor Code' }}
          </button>
        </div>
      </div>

      <!-- Right Panel: Output -->
      <div class="output-panel">
        <div v-if="!result" class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="empty-icon">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
          </svg>
          <p>Generated code will appear here</p>
        </div>

        <div v-else class="result-container">
          <!-- Result Header -->
          <div class="result-header">
            <div class="result-status" :class="{ success: result.success, error: !result.success }">
              <svg v-if="result.success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M15 9l-6 6M9 9l6 6"/>
              </svg>
              {{ result.success ? 'Success' : 'Failed' }}
            </div>
            <div class="result-meta">
              <span>{{ result.tokens_used }} tokens</span>
              <span>{{ result.processing_time?.toFixed(2) }}s</span>
            </div>
          </div>

          <!-- Validation Warnings -->
          <div v-if="result.validation?.warnings?.length" class="validation-warnings">
            <div class="warning-header">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
              </svg>
              Warnings
            </div>
            <ul>
              <li v-for="(warning, idx) in result.validation.warnings" :key="idx">
                {{ warning }}
              </li>
            </ul>
          </div>

          <!-- Validation Errors -->
          <div v-if="result.validation?.errors?.length" class="validation-errors">
            <div class="error-header">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M15 9l-6 6M9 9l6 6"/>
              </svg>
              Errors
            </div>
            <ul>
              <li v-for="(error, idx) in result.validation.errors" :key="idx">
                {{ error }}
              </li>
            </ul>
          </div>

          <!-- Changes (for refactoring) -->
          <div v-if="result.changes?.length" class="changes-list">
            <div class="changes-header">Changes Made</div>
            <ul>
              <li v-for="(change, idx) in result.changes" :key="idx">
                {{ change }}
              </li>
            </ul>
          </div>

          <!-- Code Output -->
          <div class="code-output">
            <div class="code-header">
              <span>{{ mode === 'generate' ? 'Generated Code' : 'Refactored Code' }}</span>
              <button class="copy-btn" @click="copyCode">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                </svg>
                {{ copied ? 'Copied!' : 'Copy' }}
              </button>
            </div>
            <pre class="code-block"><code>{{ outputCode }}</code></pre>
          </div>

          <!-- Diff View (for refactoring) -->
          <div v-if="mode === 'refactor' && result.diff" class="diff-section">
            <div class="diff-header">
              <span>Diff</span>
              <button class="toggle-btn" @click="showDiff = !showDiff">
                {{ showDiff ? 'Hide' : 'Show' }}
              </button>
            </div>
            <pre v-if="showDiff" class="diff-block"><code v-html="formatDiff(result.diff)"></code></pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Validation Panel -->
    <div class="validation-panel">
      <h3>Code Validator</h3>
      <div class="validator-content">
        <div class="form-group">
          <textarea
            v-model="validateCode"
            placeholder="Paste code to validate..."
            rows="4"
            class="code-input"
          ></textarea>
        </div>
        <div class="form-row">
          <select v-model="validateLanguage">
            <option value="python">Python</option>
            <option value="typescript">TypeScript</option>
            <option value="javascript">JavaScript</option>
            <option value="vue">Vue</option>
          </select>
          <button class="validate-btn" :disabled="!validateCode" @click="validateCodeSubmit">
            Validate
          </button>
        </div>
        <div v-if="validationResult" class="validation-result">
          <div :class="['validation-status', { valid: validationResult.is_valid, invalid: !validationResult.is_valid }]">
            {{ validationResult.is_valid ? 'Valid' : 'Invalid' }}
          </div>
          <div v-if="validationResult.ast_info" class="ast-info">
            <span v-if="validationResult.ast_info.functions !== undefined">
              Functions: {{ Array.isArray(validationResult.ast_info.functions) ? validationResult.ast_info.functions.length : validationResult.ast_info.functions }}
            </span>
            <span v-if="validationResult.ast_info.classes !== undefined">
              Classes: {{ Array.isArray(validationResult.ast_info.classes) ? validationResult.ast_info.classes.length : validationResult.ast_info.classes }}
            </span>
            <span v-if="validationResult.ast_info.total_lines">
              Lines: {{ validationResult.ast_info.total_lines }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

// Types
interface GenerateRequest {
  description: string
  language: string
  context: string
  existing_code: string
}

interface RefactorRequest {
  code: string
  language: string
  refactoring_type: string
  preserve_comments: boolean
}

interface ValidationInfo {
  is_valid: boolean
  errors: string[]
  warnings: string[]
  ast_info: Record<string, unknown>
}

interface GenerationResult {
  success: boolean
  generated_code?: string
  refactored_code?: string
  diff?: string
  changes?: string[]
  validation?: ValidationInfo
  tokens_used: number
  processing_time: number
  error?: string
}

interface Stats {
  generation: { total: number; success: number; tokens: number }
  refactoring: { total: number; success: number; tokens: number }
}

interface RefactoringType {
  id: string
  name: string
  description: string
}

// State
const mode = ref<'generate' | 'refactor'>('generate')
const processing = ref(false)
const result = ref<GenerationResult | null>(null)
const copied = ref(false)
const showDiff = ref(false)

const generateRequest = ref<GenerateRequest>({
  description: '',
  language: 'python',
  context: '',
  existing_code: ''
})

const refactorRequest = ref<RefactorRequest>({
  code: '',
  language: 'python',
  refactoring_type: 'general',
  preserve_comments: true
})

const stats = ref<Stats>({
  generation: { total: 0, success: 0, tokens: 0 },
  refactoring: { total: 0, success: 0, tokens: 0 }
})

const refactoringTypes = ref<RefactoringType[]>([
  { id: 'general', name: 'General', description: 'General improvements' },
  { id: 'add_type_hints', name: 'Add Type Hints', description: 'Add type annotations' },
  { id: 'add_docstrings', name: 'Add Docstrings', description: 'Add documentation' },
  { id: 'simplify_conditional', name: 'Simplify Conditionals', description: 'Simplify if/else' },
  { id: 'improve_naming', name: 'Improve Naming', description: 'Better variable names' },
  { id: 'clean_imports', name: 'Clean Imports', description: 'Organize imports' },
  { id: 'extract_function', name: 'Extract Function', description: 'Extract reusable code' }
])

const validateCode = ref('')
const validateLanguage = ref('python')
const validationResult = ref<ValidationInfo | null>(null)

// Computed
const outputCode = computed(() => {
  if (!result.value) return ''
  return result.value.generated_code || result.value.refactored_code || ''
})

const totalTokens = computed(() => {
  return stats.value.generation.tokens + stats.value.refactoring.tokens
})

const successRate = computed(() => {
  const total = stats.value.generation.total + stats.value.refactoring.total
  const success = stats.value.generation.success + stats.value.refactoring.success
  if (total === 0) return 100
  return Math.round((success / total) * 100)
})

// Methods
const formatTokens = (tokens: number): string => {
  if (tokens >= 1000000) return (tokens / 1000000).toFixed(1) + 'M'
  if (tokens >= 1000) return (tokens / 1000).toFixed(1) + 'K'
  return String(tokens)
}

const formatDiff = (diff: string): string => {
  return diff
    .split('\n')
    .map(line => {
      if (line.startsWith('+') && !line.startsWith('+++')) {
        return `<span class="diff-add">${escapeHtml(line)}</span>`
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        return `<span class="diff-remove">${escapeHtml(line)}</span>`
      } else if (line.startsWith('@@')) {
        return `<span class="diff-info">${escapeHtml(line)}</span>`
      }
      return escapeHtml(line)
    })
    .join('\n')
}

const escapeHtml = (text: string): string => {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }
  return text.replace(/[&<>"']/g, m => map[m])
}

const copyCode = async () => {
  try {
    await navigator.clipboard.writeText(outputCode.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

const generateCode = async () => {
  processing.value = true
  result.value = null

  try {
    const response = await fetch('/api/code-generation/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(generateRequest.value)
    })

    if (!response.ok) throw new Error('Generation failed')

    result.value = await response.json()
    await fetchStats()
  } catch (err) {
    console.error('Generation error:', err)
    result.value = {
      success: false,
      error: String(err),
      tokens_used: 0,
      processing_time: 0
    }
  } finally {
    processing.value = false
  }
}

const refactorCode = async () => {
  processing.value = true
  result.value = null

  try {
    const response = await fetch('/api/code-generation/refactor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(refactorRequest.value)
    })

    if (!response.ok) throw new Error('Refactoring failed')

    result.value = await response.json()
    await fetchStats()
  } catch (err) {
    console.error('Refactoring error:', err)
    result.value = {
      success: false,
      error: String(err),
      tokens_used: 0,
      processing_time: 0
    }
  } finally {
    processing.value = false
  }
}

const validateCodeSubmit = async () => {
  try {
    const response = await fetch('/api/code-generation/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: validateCode.value,
        language: validateLanguage.value
      })
    })

    if (!response.ok) throw new Error('Validation failed')

    validationResult.value = await response.json()
  } catch (err) {
    console.error('Validation error:', err)
  }
}

const fetchStats = async () => {
  try {
    const response = await fetch('/api/code-generation/stats')
    if (response.ok) {
      const data = await response.json()
      stats.value = data
    }
  } catch (err) {
    console.error('Failed to fetch stats:', err)
  }
}

const fetchRefactoringTypes = async () => {
  try {
    const response = await fetch('/api/code-generation/refactoring-types')
    if (response.ok) {
      const data = await response.json()
      refactoringTypes.value = data.types
    }
  } catch (err) {
    console.error('Failed to fetch refactoring types:', err)
  }
}

// Lifecycle
onMounted(() => {
  fetchStats()
  fetchRefactoringTypes()
})
</script>

<style scoped>
.code-generation-dashboard {
  padding: 1.5rem;
  background: #0f0f1a;
  min-height: 100vh;
  color: #f9fafb;
}

.dashboard-header {
  margin-bottom: 1.5rem;
}

.dashboard-header h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: #f9fafb;
  margin: 0;
}

.subtitle {
  color: #9ca3af;
  font-size: 0.875rem;
  margin: 0.25rem 0 0 0;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 0.5rem;
  padding: 1rem;
}

.stat-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon svg {
  width: 1.25rem;
  height: 1.25rem;
}

.stat-icon.generation {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.stat-icon.refactor {
  background: rgba(168, 85, 247, 0.2);
  color: #a855f7;
}

.stat-icon.tokens {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.stat-icon.success {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #f9fafb;
}

.stat-label {
  font-size: 0.75rem;
  color: #9ca3af;
}

/* Main Content */
.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.input-panel,
.output-panel {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 0.5rem;
  padding: 1.5rem;
}

/* Mode Toggle */
.mode-toggle {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.mode-btn {
  flex: 1;
  padding: 0.75rem 1rem;
  background: #2a2a3e;
  border: 1px solid #3a3a4e;
  border-radius: 0.375rem;
  color: #9ca3af;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-btn:hover {
  background: #3a3a4e;
}

.mode-btn.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}

/* Forms */
.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  color: #d1d5db;
  margin-bottom: 0.5rem;
}

.form-group textarea,
.form-group select {
  width: 100%;
  padding: 0.75rem;
  background: #0f0f1a;
  border: 1px solid #3a3a4e;
  border-radius: 0.375rem;
  color: #f9fafb;
  font-size: 0.875rem;
  resize: vertical;
}

.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: #3b82f6;
}

.code-input {
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 0.8125rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.checkbox-group input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  accent-color: #3b82f6;
}

.submit-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  background: #3b82f6;
  border: none;
  border-radius: 0.375rem;
  color: #fff;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: background 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #2563eb;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Output Panel */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: #6b7280;
}

.empty-icon {
  width: 3rem;
  height: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

/* Result */
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #2a2a3e;
}

.result-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
}

.result-status svg {
  width: 1.25rem;
  height: 1.25rem;
}

.result-status.success {
  color: #22c55e;
}

.result-status.error {
  color: #ef4444;
}

.result-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #9ca3af;
}

/* Validation Messages */
.validation-warnings,
.validation-errors {
  margin-bottom: 1rem;
  padding: 0.75rem;
  border-radius: 0.375rem;
}

.validation-warnings {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.validation-errors {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.warning-header,
.error-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.warning-header {
  color: #f59e0b;
}

.error-header {
  color: #ef4444;
}

.warning-header svg,
.error-header svg {
  width: 1rem;
  height: 1rem;
}

.validation-warnings ul,
.validation-errors ul {
  margin: 0;
  padding-left: 1.5rem;
  font-size: 0.8125rem;
}

.validation-warnings li {
  color: #fbbf24;
}

.validation-errors li {
  color: #f87171;
}

/* Changes List */
.changes-list {
  margin-bottom: 1rem;
  padding: 0.75rem;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 0.375rem;
}

.changes-header {
  font-size: 0.875rem;
  font-weight: 500;
  color: #60a5fa;
  margin-bottom: 0.5rem;
}

.changes-list ul {
  margin: 0;
  padding-left: 1.5rem;
  font-size: 0.8125rem;
  color: #93c5fd;
}

/* Code Output */
.code-output {
  margin-bottom: 1rem;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  background: #2a2a3e;
  border-radius: 0.375rem 0.375rem 0 0;
  font-size: 0.75rem;
  color: #9ca3af;
}

.copy-btn {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: 1px solid #3a3a4e;
  border-radius: 0.25rem;
  color: #9ca3af;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover {
  background: #3a3a4e;
  color: #f9fafb;
}

.copy-btn svg {
  width: 0.875rem;
  height: 0.875rem;
}

.code-block {
  margin: 0;
  padding: 1rem;
  background: #0a0a14;
  border: 1px solid #2a2a3e;
  border-top: none;
  border-radius: 0 0 0.375rem 0.375rem;
  overflow-x: auto;
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #e5e7eb;
  max-height: 400px;
}

/* Diff Section */
.diff-section {
  margin-top: 1rem;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  color: #9ca3af;
}

.toggle-btn {
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: 1px solid #3a3a4e;
  border-radius: 0.25rem;
  color: #9ca3af;
  font-size: 0.75rem;
  cursor: pointer;
}

.toggle-btn:hover {
  background: #3a3a4e;
  color: #f9fafb;
}

.diff-block {
  margin: 0;
  padding: 1rem;
  background: #0a0a14;
  border: 1px solid #2a2a3e;
  border-radius: 0.375rem;
  overflow-x: auto;
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #9ca3af;
  max-height: 300px;
}

.diff-block :deep(.diff-add) {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.diff-block :deep(.diff-remove) {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.diff-block :deep(.diff-info) {
  color: #60a5fa;
}

/* Validation Panel */
.validation-panel {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 0.5rem;
  padding: 1.5rem;
}

.validation-panel h3 {
  font-size: 1rem;
  font-weight: 500;
  color: #f9fafb;
  margin: 0 0 1rem 0;
}

.validator-content .form-row {
  display: flex;
  gap: 0.5rem;
}

.validator-content select {
  flex: 1;
  padding: 0.5rem;
  background: #0f0f1a;
  border: 1px solid #3a3a4e;
  border-radius: 0.375rem;
  color: #f9fafb;
  font-size: 0.875rem;
}

.validate-btn {
  padding: 0.5rem 1rem;
  background: #6366f1;
  border: none;
  border-radius: 0.375rem;
  color: #fff;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.2s;
}

.validate-btn:hover:not(:disabled) {
  background: #4f46e5;
}

.validate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.validation-result {
  margin-top: 1rem;
  padding: 0.75rem;
  background: #0f0f1a;
  border: 1px solid #2a2a3e;
  border-radius: 0.375rem;
}

.validation-status {
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.validation-status.valid {
  color: #22c55e;
}

.validation-status.invalid {
  color: #ef4444;
}

.ast-info {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #9ca3af;
}

/* Responsive */
@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .main-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
