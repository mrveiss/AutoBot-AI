<template>
  <div class="threat-intel-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2 class="dashboard-title">Threat Intelligence</h2>
        <p class="dashboard-subtitle">URL reputation checking and domain security analysis</p>
      </div>
      <div class="header-actions">
        <button class="btn-refresh" @click="refreshStatus" :disabled="loading">
          <span class="icon">↻</span>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Service Status Cards -->
    <div class="status-cards">
      <div class="status-card" :class="{ active: status.virustotal?.configured }">
        <div class="card-icon">
          <span v-if="status.virustotal?.configured">✓</span>
          <span v-else>✗</span>
        </div>
        <div class="card-content">
          <span class="card-title">VirusTotal</span>
          <span class="card-status">
            {{ status.virustotal?.configured ? 'Configured' : 'Not Configured' }}
          </span>
          <span v-if="status.virustotal?.configured" class="card-detail">
            {{ status.virustotal?.remaining_requests || 0 }}/{{ status.virustotal?.requests_per_minute || 4 }} requests remaining
          </span>
        </div>
      </div>

      <div class="status-card" :class="{ active: status.urlvoid?.configured }">
        <div class="card-icon">
          <span v-if="status.urlvoid?.configured">✓</span>
          <span v-else>✗</span>
        </div>
        <div class="card-content">
          <span class="card-title">URLVoid</span>
          <span class="card-status">
            {{ status.urlvoid?.configured ? 'Configured' : 'Not Configured' }}
          </span>
          <span v-if="status.urlvoid?.configured" class="card-detail">
            {{ status.urlvoid?.remaining_requests || 0 }}/{{ status.urlvoid?.requests_per_minute || 10 }} requests remaining
          </span>
        </div>
      </div>

      <div class="status-card cache">
        <div class="card-icon">💾</div>
        <div class="card-content">
          <span class="card-title">Cache</span>
          <span class="card-status">{{ status.cache_stats?.size || 0 }} entries</span>
          <span class="card-detail">2-hour TTL</span>
        </div>
      </div>

      <div class="status-card overall" :class="{ warning: !status.any_service_configured }">
        <div class="card-icon">
          <span v-if="status.any_service_configured">🛡️</span>
          <span v-else>⚠️</span>
        </div>
        <div class="card-content">
          <span class="card-title">Overall Status</span>
          <span class="card-status">
            {{ status.any_service_configured ? 'Active' : 'No Services' }}
          </span>
          <span class="card-detail">
            {{ status.any_service_configured ? 'Ready for URL checks' : 'Configure API keys' }}
          </span>
        </div>
      </div>
    </div>

    <!-- URL Check Section -->
    <div class="url-check-section">
      <div class="section-header">
        <h3>URL Reputation Check</h3>
        <p>Check any URL against threat intelligence services</p>
      </div>
      <div class="url-check-form">
        <input
          v-model="urlToCheck"
          type="url"
          placeholder="https://example.com"
          class="url-input"
          @keyup.enter="checkUrl"
        />
        <button
          class="btn-check"
          @click="checkUrl"
          :disabled="checkLoading || !urlToCheck || !status.any_service_configured"
        >
          <span v-if="checkLoading" class="spinner"></span>
          <span v-else>🔍</span>
          {{ checkLoading ? 'Checking...' : 'Check URL' }}
        </button>
      </div>

      <!-- Check Result -->
      <div v-if="checkResult" class="check-result" :class="'threat-' + checkResult.threat_level">
        <div class="result-header">
          <span class="result-icon">{{ getThreatIcon(checkResult.threat_level) }}</span>
          <span class="result-url">{{ checkResult.url }}</span>
          <span class="result-badge" :class="checkResult.threat_level">
            {{ checkResult.threat_level.toUpperCase() }}
          </span>
        </div>
        <div class="result-details">
          <div class="score-bar">
            <div class="score-label">Safety Score</div>
            <div class="score-track">
              <div
                class="score-fill"
                :style="{ width: (checkResult.overall_score * 100) + '%', backgroundColor: getScoreColor(checkResult.overall_score) }"
              ></div>
            </div>
            <div class="score-value">{{ (checkResult.overall_score * 100).toFixed(0) }}%</div>
          </div>
          <div class="source-scores">
            <div v-if="checkResult.virustotal_score !== null" class="source-score">
              <span class="source-name">VirusTotal:</span>
              <span class="source-value">{{ (checkResult.virustotal_score * 100).toFixed(0) }}%</span>
            </div>
            <div v-if="checkResult.urlvoid_score !== null" class="source-score">
              <span class="source-name">URLVoid:</span>
              <span class="source-value">{{ (checkResult.urlvoid_score * 100).toFixed(0) }}%</span>
            </div>
            <div class="source-score">
              <span class="source-name">Sources Checked:</span>
              <span class="source-value">{{ checkResult.sources_checked }}</span>
            </div>
            <div v-if="checkResult.cached" class="source-score cached">
              <span class="source-name">Cached Result</span>
              <span class="source-value">✓</span>
            </div>
          </div>
        </div>
      </div>

      <!-- No Services Warning -->
      <div v-if="!status.any_service_configured" class="no-services-warning">
        <span class="warning-icon">⚠️</span>
        <span class="warning-text">
          No threat intelligence services configured.
          Set <code>VIRUSTOTAL_API_KEY</code> or <code>URLVOID_API_KEY</code> environment variables.
        </span>
        <router-link to="/settings/security" class="btn-settings">
          Configure Settings →
        </router-link>
      </div>
    </div>

    <!-- Domain Security Stats -->
    <div class="domain-stats-section">
      <div class="section-header">
        <h3>Domain Security Configuration</h3>
        <p>Current domain validation settings and lists</p>
      </div>
      <div class="domain-stats-grid">
        <div class="stat-card">
          <div class="stat-icon">✅</div>
          <div class="stat-value">{{ domainStats.whitelist_count || 0 }}</div>
          <div class="stat-label">Whitelisted Domains</div>
        </div>
        <div class="stat-card danger">
          <div class="stat-icon">🚫</div>
          <div class="stat-value">{{ domainStats.blacklist_count || 0 }}</div>
          <div class="stat-label">Blacklisted Domains</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-icon">⚠️</div>
          <div class="stat-value">{{ domainStats.suspicious_tlds_count || 0 }}</div>
          <div class="stat-label">Suspicious TLDs</div>
        </div>
        <div class="stat-card info">
          <div class="stat-icon">🔒</div>
          <div class="stat-value">{{ domainStats.settings?.require_https ? 'Yes' : 'No' }}</div>
          <div class="stat-label">Require HTTPS</div>
        </div>
      </div>
    </div>

    <!-- Recent Checks History -->
    <div v-if="checkHistory.length > 0" class="history-section">
      <div class="section-header">
        <h3>Recent Checks</h3>
        <button class="btn-clear" @click="clearHistory">Clear History</button>
      </div>
      <div class="history-list">
        <div
          v-for="(item, index) in checkHistory"
          :key="index"
          class="history-item"
          :class="'threat-' + item.threat_level"
        >
          <span class="history-icon">{{ getThreatIcon(item.threat_level) }}</span>
          <span class="history-url">{{ item.url }}</span>
          <span class="history-score">{{ (item.overall_score * 100).toFixed(0) }}%</span>
          <span class="history-level" :class="item.threat_level">{{ item.threat_level }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import apiClient from '@/utils/ApiClient'

const logger = createLogger('ThreatIntelligenceDashboard')

/**
 * Helper to get CSS custom property value from the document root.
 * Used for dynamic color access in JavaScript when needed.
 */
function getCssVar(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

// State
const loading = ref(false)
const checkLoading = ref(false)
const urlToCheck = ref('')

const status = reactive({
  any_service_configured: false,
  virustotal: null as Record<string, unknown> | null,
  urlvoid: null as Record<string, unknown> | null,
  cache_stats: null as Record<string, unknown> | null
})

const domainStats = reactive({
  whitelist_count: 0,
  blacklist_count: 0,
  suspicious_tlds_count: 0,
  settings: null as Record<string, unknown> | null,
  threat_intelligence: null as Record<string, unknown> | null
})

interface CheckResult {
  success: boolean
  url: string
  overall_score: number
  threat_level: string
  virustotal_score: number | null
  urlvoid_score: number | null
  sources_checked: number
  cached: boolean
  message?: string
}

const checkResult = ref<CheckResult | null>(null)
const checkHistory = ref<CheckResult[]>([])

// Methods
async function refreshStatus() {
  loading.value = true
  try {
    const [statusResponse, statsResponse] = await Promise.all([
      apiClient.get('/api/security/threat-intel/status'),
      apiClient.get('/api/security/domain-security/stats')
    ])

    const statusData = (statusResponse as { data?: Record<string, unknown> }).data
    if (statusData) {
      status.any_service_configured = statusData.any_service_configured as boolean
      status.virustotal = statusData.virustotal as Record<string, unknown> | null
      status.urlvoid = statusData.urlvoid as Record<string, unknown> | null
      status.cache_stats = statusData.cache_stats as Record<string, unknown> | null
    }

    const statsData = (statsResponse as { data?: Record<string, unknown> }).data
    if (statsData?.success) {
      const stats = (statsData.stats as Record<string, unknown>) || {}
      domainStats.whitelist_count = (stats.whitelist_count as number) || 0
      domainStats.blacklist_count = (stats.blacklist_count as number) || 0
      domainStats.suspicious_tlds_count = (stats.suspicious_tlds_count as number) || 0
      domainStats.settings = (stats.settings as Record<string, unknown>) || null
      domainStats.threat_intelligence = (stats.threat_intelligence as Record<string, unknown>) || null
    }
  } catch (error) {
    logger.error('Failed to fetch threat intel status', error)
  } finally {
    loading.value = false
  }
}

async function checkUrl() {
  if (!urlToCheck.value || !status.any_service_configured) return

  checkLoading.value = true
  checkResult.value = null

  try {
    const response = await apiClient.post('/api/security/threat-intel/check-url', {
      url: urlToCheck.value
    })

    const responseData = (response as { data?: CheckResult }).data
    if (responseData) {
      checkResult.value = responseData
      // Add to history (keep last 10)
      checkHistory.value.unshift(responseData)
      if (checkHistory.value.length > 10) {
        checkHistory.value.pop()
      }
    }
  } catch (error) {
    logger.error('Failed to check URL', error)
    checkResult.value = {
      success: false,
      url: urlToCheck.value,
      overall_score: 0.5,
      threat_level: 'unknown',
      virustotal_score: null,
      urlvoid_score: null,
      sources_checked: 0,
      cached: false,
      message: 'Failed to check URL'
    }
  } finally {
    checkLoading.value = false
  }
}

function getThreatIcon(level: string): string {
  const icons: Record<string, string> = {
    safe: '✅',
    low: '🟢',
    medium: '🟡',
    high: '🟠',
    critical: '🔴',
    unknown: '❓'
  }
  return icons[level] || '❓'
}

/**
 * Get the appropriate color for the score fill bar.
 * Uses CSS variables from design tokens for theme consistency.
 */
function getScoreColor(score: number): string {
  if (score >= 0.9) return getCssVar('--color-success')
  if (score >= 0.7) return getCssVar('--color-success-light')
  if (score >= 0.5) return getCssVar('--color-warning')
  if (score >= 0.3) return getCssVar('--chart-orange')
  return getCssVar('--color-error')
}

function clearHistory() {
  checkHistory.value = []
}

// Lifecycle
onMounted(() => {
  refreshStatus()
})
</script>

<style scoped>
.threat-intel-dashboard {
  padding: var(--spacing-4);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.dashboard-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.dashboard-subtitle {
  color: var(--text-secondary);
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

.btn-refresh {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-primary);
  transition: var(--transition-all);
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Status Cards */
.status-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.status-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  transition: var(--transition-all);
}

.status-card.active {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.status-card.warning {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
}

.card-icon {
  font-size: var(--text-2xl);
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-card);
  border-radius: var(--radius-md);
}

.card-content {
  display: flex;
  flex-direction: column;
}

.card-title {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.card-status {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.card-detail {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

/* URL Check Section */
.url-check-section,
.domain-stats-section,
.history-section {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-6);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
}

.section-header h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.section-header p {
  color: var(--text-secondary);
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
}

.url-check-form {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
}

.url-input {
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.url-input:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: var(--shadow-focus);
}

.btn-check {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-6);
  background: var(--color-info);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: var(--font-medium);
  transition: var(--transition-all);
}

.btn-check:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.btn-check:disabled {
  background: var(--text-muted);
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--text-on-primary);
  border-top-color: transparent;
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Check Result */
.check-result {
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.check-result.threat-safe { background: var(--color-success-bg); border-color: var(--color-success-border); }
.check-result.threat-low { background: var(--color-success-bg); border-color: var(--color-success-border); }
.check-result.threat-medium { background: var(--color-warning-bg); border-color: var(--color-warning-border); }
.check-result.threat-high { background: var(--color-warning-bg); border-color: var(--color-warning-border); }
.check-result.threat-critical { background: var(--color-error-bg); border-color: var(--color-error-border); }

.result-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.result-icon {
  font-size: var(--text-2xl);
}

.result-url {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  word-break: break-all;
  color: var(--text-primary);
}

.result-badge {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.result-badge.safe, .result-badge.low { background: var(--color-success-bg); color: var(--color-success-dark); }
.result-badge.medium { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.result-badge.high { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.result-badge.critical { background: var(--color-error-bg); color: var(--color-error-dark); }
.result-badge.unknown { background: var(--bg-tertiary); color: var(--text-secondary); }

.score-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-3);
}

.score-label {
  width: 100px;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.score-track {
  flex: 1;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: var(--radius-default);
  transition: width var(--duration-300) var(--ease-out);
}

.score-value {
  width: 50px;
  text-align: right;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.source-scores {
  display: flex;
  gap: var(--spacing-6);
  flex-wrap: wrap;
}

.source-score {
  display: flex;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.source-name {
  color: var(--text-secondary);
}

.source-value {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.source-score.cached {
  color: var(--color-primary);
}

/* No Services Warning */
.no-services-warning {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-lg);
}

.warning-icon {
  font-size: var(--text-2xl);
}

.warning-text {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-warning-dark);
}

.warning-text code {
  background: var(--color-warning-bg-hover);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.btn-settings {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-warning);
  color: var(--text-on-warning);
  text-decoration: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
  transition: var(--transition-all);
}

.btn-settings:hover {
  background: var(--color-warning-hover);
}

/* Domain Stats */
.domain-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.stat-card {
  text-align: center;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.stat-card.danger { background: var(--color-error-bg); border-color: var(--color-error-border); }
.stat-card.warning { background: var(--color-warning-bg); border-color: var(--color-warning-border); }
.stat-card.info { background: var(--color-info-bg); border-color: var(--color-info); }

.stat-icon {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-2);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

/* History Section */
.btn-clear {
  padding: var(--spacing-1-5) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition-all);
}

.btn-clear:hover {
  background: var(--bg-hover);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--border-default);
}

.history-item.threat-safe, .history-item.threat-low { border-left-color: var(--color-success); }
.history-item.threat-medium { border-left-color: var(--color-warning); }
.history-item.threat-high { border-left-color: var(--chart-orange); }
.history-item.threat-critical { border-left-color: var(--color-error); }

.history-icon {
  font-size: var(--text-base);
}

.history-url {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-score {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.history-level {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.history-level.safe, .history-level.low { background: var(--color-success-bg); color: var(--color-success-dark); }
.history-level.medium { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.history-level.high { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.history-level.critical { background: var(--color-error-bg); color: var(--color-error-dark); }
.history-level.unknown { background: var(--bg-tertiary); color: var(--text-secondary); }
</style>
