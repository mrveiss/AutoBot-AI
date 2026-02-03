<template>
  <div class="entity-extractor">
    <!-- Header -->
    <div class="extractor-header">
      <h4><i class="fas fa-brain"></i> Entity Extraction</h4>
      <p class="header-description">Extract entities and relationships from text</p>
    </div>

    <!-- Input Section -->
    <div class="input-section">
      <div class="form-group">
        <label for="conversation-id">
          <i class="fas fa-tag"></i> Conversation ID
          <span class="label-hint">(for tracking)</span>
        </label>
        <input
          id="conversation-id"
          v-model="conversationId"
          type="text"
          placeholder="Enter a unique identifier (e.g., conv-001)"
          :disabled="isExtracting"
        />
      </div>

      <div class="form-group">
        <label for="text-input">
          <i class="fas fa-file-alt"></i> Text Content
          <span class="label-hint">(supports multi-message format)</span>
        </label>
        <textarea
          id="text-input"
          v-model="textInput"
          rows="8"
          placeholder="Enter text to extract entities from...

You can enter plain text or use message format:
[user] What is Redis?
[assistant] Redis is an in-memory data structure store..."
          :disabled="isExtracting"
        ></textarea>
        <div class="input-actions">
          <span class="char-count">{{ textInput.length }} characters</span>
          <button
            type="button"
            @click="clearInput"
            class="text-btn"
            :disabled="isExtracting || !textInput"
          >
            <i class="fas fa-eraser"></i> Clear
          </button>
          <button
            type="button"
            @click="loadSampleText"
            class="text-btn"
            :disabled="isExtracting"
          >
            <i class="fas fa-flask"></i> Load Sample
          </button>
        </div>
      </div>

      <div class="extract-actions">
        <button
          @click="extractEntities"
          class="action-btn primary"
          :disabled="isExtracting || !textInput.trim() || !conversationId.trim()"
        >
          <i v-if="isExtracting" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-magic"></i>
          {{ isExtracting ? 'Extracting...' : 'Extract Entities' }}
        </button>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="extractionResult" class="results-section">
      <div class="results-header">
        <h5><i class="fas fa-check-circle"></i> Extraction Results</h5>
        <span class="processing-time">
          <i class="fas fa-clock"></i>
          {{ extractionResult.processing_time.toFixed(2) }}s
        </span>
      </div>

      <div class="results-stats">
        <div class="stat-card">
          <div class="stat-value">{{ extractionResult.facts_analyzed }}</div>
          <div class="stat-label">Facts Analyzed</div>
        </div>
        <div class="stat-card success">
          <div class="stat-value">{{ extractionResult.entities_created }}</div>
          <div class="stat-label">Entities Created</div>
        </div>
        <div class="stat-card info">
          <div class="stat-value">{{ extractionResult.relations_created }}</div>
          <div class="stat-label">Relations Created</div>
        </div>
      </div>

      <div v-if="extractionResult.errors?.length" class="errors-section">
        <h6><i class="fas fa-exclamation-triangle"></i> Warnings</h6>
        <ul class="error-list">
          <li v-for="(error, idx) in extractionResult.errors" :key="idx">
            {{ error }}
          </li>
        </ul>
      </div>

      <div class="result-actions">
        <button @click="viewInGraph" class="action-btn">
          <i class="fas fa-project-diagram"></i> View in Graph
        </button>
        <button @click="clearResults" class="action-btn">
          <i class="fas fa-times"></i> Clear Results
        </button>
      </div>
    </div>

    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" class="close-btn">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Extraction History -->
    <div v-if="extractionHistory.length > 0" class="history-section">
      <h5><i class="fas fa-history"></i> Recent Extractions</h5>
      <div class="history-list">
        <div
          v-for="item in extractionHistory"
          :key="item.request_id"
          class="history-item"
          @click="selectHistoryItem(item)"
        >
          <div class="history-main">
            <span class="history-id">{{ item.conversation_id }}</span>
            <span class="history-stats">
              {{ item.entities_created }} entities, {{ item.relations_created }} relations
            </span>
          </div>
          <div class="history-meta">
            <span class="history-time">{{ formatTime(item.timestamp) }}</span>
            <span :class="['history-status', item.success ? 'success' : 'error']">
              {{ item.success ? 'Success' : 'Failed' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * EntityExtractor - Extract entities and relationships from text
 *
 * @description Provides an interface for extracting entities from text content
 * using the backend entity extraction API. Supports both plain text and
 * conversation message format.
 *
 * @see Issue #586 - Entity Extraction & Graph RAG Manager GUI
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('EntityExtractor')
const router = useRouter()

// ============================================================================
// Types
// ============================================================================

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

interface ExtractionResult {
  success: boolean
  conversation_id: string
  facts_analyzed: number
  entities_created: number
  relations_created: number
  processing_time: number
  errors: string[]
  request_id: string
  timestamp?: number
}

// ============================================================================
// State
// ============================================================================

const conversationId = ref('')
const textInput = ref('')
const isExtracting = ref(false)
const errorMessage = ref('')
const extractionResult = ref<ExtractionResult | null>(null)
const extractionHistory = ref<ExtractionResult[]>([])

// ============================================================================
// Emits
// ============================================================================

const emit = defineEmits<{
  (e: 'extraction-complete', result: ExtractionResult): void
  (e: 'view-graph', conversationId: string): void
}>()

// ============================================================================
// Methods
// ============================================================================

/**
 * Parses text input into message array
 * Supports plain text and [role] content format
 */
function parseMessages(text: string): Message[] {
  const lines = text.split('\n')
  const messages: Message[] = []
  let currentRole: 'user' | 'assistant' | 'system' = 'user'
  let currentContent: string[] = []

  const rolePattern = /^\[(user|assistant|system)\]\s*/i

  for (const line of lines) {
    const roleMatch = line.match(rolePattern)
    if (roleMatch) {
      if (currentContent.length > 0) {
        messages.push({
          role: currentRole,
          content: currentContent.join('\n').trim()
        })
        currentContent = []
      }
      currentRole = roleMatch[1].toLowerCase() as 'user' | 'assistant' | 'system'
      const content = line.replace(rolePattern, '').trim()
      if (content) {
        currentContent.push(content)
      }
    } else {
      currentContent.push(line)
    }
  }

  if (currentContent.length > 0) {
    const content = currentContent.join('\n').trim()
    if (content) {
      messages.push({ role: currentRole, content })
    }
  }

  if (messages.length === 0 && text.trim()) {
    messages.push({ role: 'user', content: text.trim() })
  }

  return messages
}

/**
 * Extracts entities from the input text
 */
async function extractEntities(): Promise<void> {
  if (!textInput.value.trim() || !conversationId.value.trim()) {
    errorMessage.value = 'Please enter both conversation ID and text content'
    return
  }

  isExtracting.value = true
  errorMessage.value = ''
  extractionResult.value = null

  try {
    const messages = parseMessages(textInput.value)
    logger.info(`Extracting entities from ${messages.length} messages`)

    const response = await apiClient.post('/api/entities/extract', {
      conversation_id: conversationId.value.trim(),
      messages
    })

    const parsedResponse = await parseApiResponse(response)
    const result = parsedResponse?.data || parsedResponse

    extractionResult.value = { ...result, timestamp: Date.now() }

    extractionHistory.value.unshift(extractionResult.value)
    if (extractionHistory.value.length > 10) {
      extractionHistory.value.pop()
    }

    emit('extraction-complete', extractionResult.value)
    logger.info(`Extraction complete: ${result.entities_created} entities`)
  } catch (error) {
    logger.error('Entity extraction failed:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Entity extraction failed'
  } finally {
    isExtracting.value = false
  }
}

function clearInput(): void {
  textInput.value = ''
}

function clearResults(): void {
  extractionResult.value = null
}

function loadSampleText(): void {
  conversationId.value = `conv-${Date.now()}`
  textInput.value = `[user] I'm having issues with Redis connection timeouts in the AutoBot application.

[assistant] Redis connection timeouts can occur due to several reasons. Let me help you troubleshoot:

1. Check if Redis server is running on 172.16.168.23:6379
2. Verify network connectivity between your application and Redis
3. Check if there are too many concurrent connections

The timeout setting in the SSOT config should be at least 30 seconds for reliable operation.

[user] Thanks! I increased the timeout to 30s and it's working now.

[assistant] That's a common fix for Redis timeout issues. The default timeout is often too low for operations that involve larger datasets or slower network conditions.`
}

function viewInGraph(): void {
  emit('view-graph', conversationId.value)
  router.push('/knowledge/graph')
}

function selectHistoryItem(item: ExtractionResult): void {
  extractionResult.value = item
}

function formatTime(timestamp?: number): string {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<style scoped>
/* Issue #586: Entity Extraction styles - Uses design tokens */
.entity-extractor {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.extractor-header h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.extractor-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

.input-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--border-subtle);
}

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.form-group label i {
  color: var(--text-tertiary);
}

.label-hint {
  font-weight: var(--font-normal);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
  font-family: inherit;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-group input:disabled,
.form-group textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-group textarea {
  resize: vertical;
  min-height: 150px;
  font-family: var(--font-mono);
  line-height: 1.5;
}

.input-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
}

.char-count {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.text-btn {
  background: none;
  border: none;
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  transition: color var(--duration-200);
}

.text-btn:hover:not(:disabled) {
  color: var(--color-primary);
}

.text-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.extract-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--spacing-md);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-hover));
  color: white;
  border-color: transparent;
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-primary);
}

.results-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-success-border);
  border-left: 4px solid var(--color-success);
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.results-header h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.processing-time {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.results-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.stat-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  text-align: center;
  border: 1px solid var(--border-subtle);
}

.stat-card.success {
  border-color: var(--color-success-border);
  background: var(--color-success-bg);
}

.stat-card.info {
  border-color: var(--color-primary-border);
  background: var(--color-primary-bg);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-card.success .stat-value {
  color: var(--color-success);
}

.stat-card.info .stat-value {
  color: var(--color-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

.errors-section {
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-warning-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-warning-border);
}

.errors-section h6 {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-warning);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-sm) 0;
}

.error-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.error-list li {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--spacing-xs) 0;
}

.result-actions {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
}

.error-notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-left: 4px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error-text);
}

.error-notification i.fa-exclamation-circle {
  color: var(--color-error);
}

.error-notification span {
  flex: 1;
  font-size: var(--text-sm);
}

.close-btn {
  background: none;
  border: none;
  padding: var(--spacing-xs);
  cursor: pointer;
  color: var(--text-secondary);
  opacity: 0.7;
  transition: opacity var(--duration-200);
}

.close-btn:hover {
  opacity: 1;
}

.history-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--border-subtle);
}

.history-section h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-md) 0;
}

.history-section h5 i {
  color: var(--text-tertiary);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-200);
  border: 1px solid var(--border-subtle);
}

.history-item:hover {
  background: var(--bg-hover);
}

.history-main {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.history-id {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.history-stats {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.history-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.history-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.history-status {
  font-size: var(--text-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
}

.history-status.success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.history-status.error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

@media (max-width: 768px) {
  .results-stats {
    grid-template-columns: 1fr;
  }

  .result-actions {
    flex-direction: column;
  }

  .history-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .history-meta {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
