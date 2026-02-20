<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * BrowserAutomationView - Browser control and automation dashboard
 * Issue #900 - Browser Automation Dashboard
 */

import { ref, computed } from 'vue'
import { useBrowserAutomation } from '@/composables/useBrowserAutomation'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BrowserAutomationView')

const {
  workerStatus,
  sessions,
  currentSession,
  screenshots,
  isLoading,
  error,
  launchSession,
  closeSession,
  navigate,
  click,
  type: typeText,
  takeScreenshot,
  executeScript,
  runAutomationScript,
  deleteSession,
} = useBrowserAutomation({ autoFetch: true, pollInterval: 5000 })

const activeTab = ref<'control' | 'sessions' | 'scripts'>('control')
const urlInput = ref('')
const selectorInput = ref('')
const textInput = ref('')
const scriptInput = ref('')
const automationScriptInput = ref('')

const statusColor = computed(() => {
  if (!workerStatus.value) return 'status-unknown'
  switch (workerStatus.value.status) {
    case 'online': return 'status-online'
    case 'degraded': return 'status-degraded'
    case 'offline': return 'status-offline'
    default: return 'status-unknown'
  }
})

async function handleLaunchSession() {
  const url = urlInput.value.trim() || 'about:blank'
  const session = await launchSession(url)
  if (session) {
    logger.debug('Session launched:', session.id)
    urlInput.value = ''
  }
}

async function handleNavigate() {
  if (!currentSession.value || !urlInput.value.trim()) return
  const success = await navigate(currentSession.value.id, urlInput.value)
  if (success) {
    logger.debug('Navigation successful')
  }
}

async function handleClick() {
  if (!currentSession.value || !selectorInput.value.trim()) return
  const success = await click(currentSession.value.id, selectorInput.value)
  if (success) {
    logger.debug('Click successful')
    selectorInput.value = ''
  }
}

async function handleType() {
  if (!currentSession.value || !selectorInput.value.trim() || !textInput.value) return
  const success = await typeText(currentSession.value.id, selectorInput.value, textInput.value)
  if (success) {
    logger.debug('Type successful')
    textInput.value = ''
  }
}

async function handleScreenshot() {
  if (!currentSession.value) return
  const screenshot = await takeScreenshot(currentSession.value.id)
  if (screenshot) {
    logger.debug('Screenshot captured')
  }
}

async function handleExecuteScript() {
  if (!currentSession.value || !scriptInput.value.trim()) return
  const result = await executeScript(currentSession.value.id, scriptInput.value)
  logger.debug('Script result:', result)
  alert(`Script result: ${JSON.stringify(result, null, 2)}`)
}

async function handleRunAutomation() {
  if (!automationScriptInput.value.trim()) return
  const result = await runAutomationScript(automationScriptInput.value)
  logger.debug('Automation result:', result)
  alert(`Automation completed: ${JSON.stringify(result, null, 2)}`)
}

function selectSession(session: typeof sessions.value[0]) {
  currentSession.value = session
  activeTab.value = 'control'
}
</script>

<template>
  <div class="browser-auto-view">
    <!-- Page Header -->
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Browser Automation</h2>
        <p class="page-subtitle">Control browser workers and automate web tasks</p>
      </div>
      <div v-if="workerStatus" class="worker-summary">
        <div class="worker-label">Worker Status</div>
        <div :class="['worker-status', statusColor]">
          {{ workerStatus.status.toUpperCase() }}
        </div>
        <div class="worker-sessions">
          {{ workerStatus.active_sessions }}/{{ workerStatus.max_sessions }} sessions
        </div>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="alert alert-error">
      <i class="fas fa-exclamation-circle"></i>
      <div class="alert-content">
        <strong>Error</strong>
        <p>{{ error }}</p>
      </div>
    </div>

    <!-- Tabs -->
    <nav class="tab-nav">
      <button
        @click="activeTab = 'control'"
        :class="['tab-btn', { active: activeTab === 'control' }]"
      >
        <i class="fas fa-gamepad"></i> Control Panel
      </button>
      <button
        @click="activeTab = 'sessions'"
        :class="['tab-btn', { active: activeTab === 'sessions' }]"
      >
        <i class="fas fa-window-restore"></i> Sessions ({{ sessions.length }})
      </button>
      <button
        @click="activeTab = 'scripts'"
        :class="['tab-btn', { active: activeTab === 'scripts' }]"
      >
        <i class="fas fa-code"></i> Automation Scripts
      </button>
    </nav>

    <!-- Tab Content -->
    <div class="tab-content">
      <!-- Control Panel Tab -->
      <div v-show="activeTab === 'control'" class="tab-panel">
        <!-- Current Session Info -->
        <div v-if="currentSession" class="card">
          <div class="card-header">
            <div class="card-header-content">
              <span class="card-title">Active Session</span>
              <span class="session-url">{{ currentSession.url }}</span>
            </div>
            <button @click="closeSession(currentSession.id)" class="btn-action-danger">
              Close Session
            </button>
          </div>
        </div>

        <!-- Launch New Session -->
        <div v-if="!currentSession" class="card">
          <div class="card-header">
            <span class="card-title">Launch New Session</span>
          </div>
          <div class="card-body">
            <div class="input-action-row">
              <input v-model="urlInput" type="url" placeholder="https://example.com" class="field-input">
              <button @click="handleLaunchSession" :disabled="isLoading" class="btn-action-primary">
                Launch Browser
              </button>
            </div>
          </div>
        </div>

        <!-- Navigation Controls -->
        <div v-if="currentSession" class="card">
          <div class="card-header">
            <span class="card-title">Navigation</span>
          </div>
          <div class="card-body">
            <div class="input-action-row">
              <input v-model="urlInput" type="url" placeholder="https://example.com" class="field-input">
              <button @click="handleNavigate" :disabled="isLoading" class="btn-action-primary">
                Navigate
              </button>
            </div>
          </div>
        </div>

        <!-- Element Interaction -->
        <div v-if="currentSession" class="card">
          <div class="card-header">
            <span class="card-title">Element Interaction</span>
          </div>
          <div class="card-body interaction-fields">
            <div class="input-action-row">
              <input v-model="selectorInput" type="text" placeholder="CSS selector (e.g., #button-id)" class="field-input">
              <button @click="handleClick" :disabled="isLoading" class="btn-action-primary">
                Click
              </button>
            </div>
            <div class="input-action-row">
              <input v-model="textInput" type="text" placeholder="Text to type" class="field-input">
              <button @click="handleType" :disabled="isLoading" class="btn-action-primary">
                Type Text
              </button>
            </div>
          </div>
        </div>

        <!-- Screenshot & Script Execution -->
        <div v-if="currentSession" class="card">
          <div class="card-header">
            <span class="card-title">Actions</span>
          </div>
          <div class="card-body actions-panel">
            <button @click="handleScreenshot" :disabled="isLoading" class="btn-action-secondary btn-full">
              <i class="fas fa-camera"></i> Take Screenshot
            </button>
            <div class="script-block">
              <textarea
                v-model="scriptInput"
                rows="4"
                placeholder="JavaScript code to execute..."
                class="field-input code-textarea"
              ></textarea>
              <button @click="handleExecuteScript" :disabled="isLoading" class="btn-action-primary btn-full">
                Execute Script
              </button>
            </div>
          </div>
        </div>

        <!-- Screenshots Display -->
        <div v-if="screenshots.length > 0" class="card">
          <div class="card-header">
            <span class="card-title">Recent Screenshots</span>
          </div>
          <div class="card-body">
            <div class="screenshots-grid">
              <div v-for="(screenshot, idx) in screenshots.slice(0, 6)" :key="idx" class="screenshot-item">
                <img :src="screenshot.image_data" alt="Screenshot">
                <div class="screenshot-meta">
                  {{ new Date(screenshot.timestamp).toLocaleTimeString() }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sessions Tab -->
      <div v-show="activeTab === 'sessions'" class="tab-panel">
        <div v-if="sessions.length === 0" class="empty-state">
          <i class="fas fa-window-restore"></i>
          <p>No active sessions</p>
        </div>

        <div v-else class="card">
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Session ID</th>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="session in sessions" :key="session.id">
                  <td class="cell-mono">{{ session.id.slice(0, 8) }}...</td>
                  <td class="cell-url">{{ session.url }}</td>
                  <td>
                    <span :class="[
                      'badge',
                      session.status === 'active' ? 'badge-success' :
                      session.status === 'idle' ? 'badge-neutral' :
                      'badge-error'
                    ]">
                      {{ session.status }}
                    </span>
                  </td>
                  <td>{{ new Date(session.created_at).toLocaleString() }}</td>
                  <td class="cell-actions">
                    <button @click="selectSession(session)" class="btn-link">Control</button>
                    <button @click="deleteSession(session.id)" class="btn-link btn-link-danger">Delete</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Scripts Tab -->
      <div v-show="activeTab === 'scripts'" class="tab-panel">
        <div class="card">
          <div class="card-header">
            <span class="card-title">Run Automation Script</span>
          </div>
          <div class="card-body">
            <textarea
              v-model="automationScriptInput"
              rows="12"
              placeholder="Enter automation script (JavaScript)..."
              class="field-input code-textarea"
            ></textarea>
            <div class="action-row">
              <button
                @click="handleRunAutomation"
                :disabled="isLoading || !automationScriptInput.trim()"
                class="btn-action-primary"
              >
                Run Automation
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.browser-auto-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

/* Worker status in header */
.worker-summary {
  text-align: right;
  flex-shrink: 0;
}

.worker-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.worker-status {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  font-family: var(--font-mono);
}

.worker-sessions {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.status-online { color: var(--color-success); }
.status-degraded { color: var(--color-warning); }
.status-offline { color: var(--color-error); }
.status-unknown { color: var(--text-secondary); }

/* Alert */
.alert {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  margin: 0 var(--spacing-5);
  border-radius: var(--radius-md);
}

.alert-error {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
}

.alert-content p {
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
}

/* Tab content */
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

/* Card header content */
.card-header-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.session-url {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Input + action button rows */
.input-action-row {
  display: flex;
  gap: var(--spacing-3);
}

.input-action-row .field-input {
  flex: 1;
}

.interaction-fields {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.actions-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.btn-full {
  width: 100%;
}

.script-block {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.code-textarea {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  resize: vertical;
}

.action-row {
  display: flex;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
}

/* Danger button */
.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-on-error);
  background: var(--color-error);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out);
}

.btn-action-danger:hover {
  background: var(--color-error-hover);
}

/* Screenshots grid */
.screenshots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--spacing-4);
}

.screenshot-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.screenshot-item img {
  width: 100%;
  height: auto;
  display: block;
}

.screenshot-meta {
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* Table */
.table-wrapper { overflow-x: auto; }

.cell-mono {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.cell-url {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-actions {
  display: flex;
  gap: var(--spacing-3);
}

.btn-link {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: 0;
  transition: color var(--duration-150) var(--ease-in-out);
}

.btn-link:hover { color: var(--color-primary-hover); }

.btn-link-danger { color: var(--color-error); }
.btn-link-danger:hover { color: var(--color-error-hover); }

/* Empty state */
.empty-state {
  text-align: center;
  padding: var(--spacing-12) var(--spacing-4);
  color: var(--text-secondary);
}

.empty-state i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-3);
  display: block;
  color: var(--text-muted);
}

.empty-state p {
  margin: 0;
  font-size: var(--text-sm);
}

@media (max-width: 768px) {
  .input-action-row {
    flex-direction: column;
  }

  .screenshots-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
