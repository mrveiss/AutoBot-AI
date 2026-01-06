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
                :style="{ width: (checkResult.overall_score * 100) + '%' }"
                :class="getScoreClass(checkResult.overall_score)"
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

function getScoreClass(score: number): string {
  if (score >= 0.9) return 'safe'
  if (score >= 0.7) return 'low'
  if (score >= 0.5) return 'medium'
  if (score >= 0.3) return 'high'
  return 'critical'
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
  padding: 1rem;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e2e8f0;
}

.dashboard-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: #1a202c;
  margin: 0;
}

.dashboard-subtitle {
  color: #718096;
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-refresh {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #edf2f7;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: #e2e8f0;
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Status Cards */
.status-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.status-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #f7fafc;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  transition: all 0.2s;
}

.status-card.active {
  background: #f0fff4;
  border-color: #9ae6b4;
}

.status-card.warning {
  background: #fffaf0;
  border-color: #fbd38d;
}

.card-icon {
  font-size: 1.5rem;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  border-radius: 0.375rem;
}

.card-content {
  display: flex;
  flex-direction: column;
}

.card-title {
  font-weight: 600;
  color: #2d3748;
}

.card-status {
  font-size: 0.875rem;
  color: #718096;
}

.card-detail {
  font-size: 0.75rem;
  color: #a0aec0;
}

/* URL Check Section */
.url-check-section,
.domain-stats-section,
.history-section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #2d3748;
  margin: 0;
}

.section-header p {
  color: #718096;
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
}

.url-check-form {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.url-input {
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.url-input:focus {
  outline: none;
  border-color: #4299e1;
  box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1);
}

.btn-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  background: #4299e1;
  color: white;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-check:hover:not(:disabled) {
  background: #3182ce;
}

.btn-check:disabled {
  background: #a0aec0;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid white;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Check Result */
.check-result {
  padding: 1rem;
  border-radius: 0.5rem;
  border: 1px solid #e2e8f0;
  background: #f7fafc;
}

.check-result.threat-safe { background: #f0fff4; border-color: #9ae6b4; }
.check-result.threat-low { background: #f0fff4; border-color: #9ae6b4; }
.check-result.threat-medium { background: #fffff0; border-color: #faf089; }
.check-result.threat-high { background: #fffaf0; border-color: #fbd38d; }
.check-result.threat-critical { background: #fff5f5; border-color: #feb2b2; }

.result-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.result-icon {
  font-size: 1.5rem;
}

.result-url {
  flex: 1;
  font-family: monospace;
  font-size: 0.875rem;
  word-break: break-all;
}

.result-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.result-badge.safe, .result-badge.low { background: #c6f6d5; color: #22543d; }
.result-badge.medium { background: #fefcbf; color: #744210; }
.result-badge.high { background: #feebc8; color: #7b341e; }
.result-badge.critical { background: #fed7d7; color: #742a2a; }
.result-badge.unknown { background: #e2e8f0; color: #4a5568; }

.score-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.score-label {
  width: 100px;
  font-size: 0.875rem;
  color: #4a5568;
}

.score-track {
  flex: 1;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.score-fill.safe { background: #48bb78; }
.score-fill.low { background: #68d391; }
.score-fill.medium { background: #ecc94b; }
.score-fill.high { background: #ed8936; }
.score-fill.critical { background: #f56565; }

.score-value {
  width: 50px;
  text-align: right;
  font-weight: 600;
  color: #2d3748;
}

.source-scores {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.source-score {
  display: flex;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.source-name {
  color: #718096;
}

.source-value {
  color: #2d3748;
  font-weight: 500;
}

.source-score.cached {
  color: #805ad5;
}

/* No Services Warning */
.no-services-warning {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #fffaf0;
  border: 1px solid #fbd38d;
  border-radius: 0.5rem;
}

.warning-icon {
  font-size: 1.5rem;
}

.warning-text {
  flex: 1;
  font-size: 0.875rem;
  color: #744210;
}

.warning-text code {
  background: #feebc8;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-size: 0.8125rem;
}

.btn-settings {
  padding: 0.5rem 1rem;
  background: #ed8936;
  color: white;
  text-decoration: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
}

.btn-settings:hover {
  background: #dd6b20;
}

/* Domain Stats */
.domain-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.stat-card {
  text-align: center;
  padding: 1rem;
  background: #f7fafc;
  border-radius: 0.5rem;
  border: 1px solid #e2e8f0;
}

.stat-card.danger { background: #fff5f5; border-color: #feb2b2; }
.stat-card.warning { background: #fffaf0; border-color: #fbd38d; }
.stat-card.info { background: #ebf8ff; border-color: #90cdf4; }

.stat-icon {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #2d3748;
}

.stat-label {
  font-size: 0.75rem;
  color: #718096;
  margin-top: 0.25rem;
}

/* History Section */
.btn-clear {
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: #718096;
  cursor: pointer;
}

.btn-clear:hover {
  background: #f7fafc;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #f7fafc;
  border-radius: 0.375rem;
  border-left: 3px solid #e2e8f0;
}

.history-item.threat-safe, .history-item.threat-low { border-left-color: #48bb78; }
.history-item.threat-medium { border-left-color: #ecc94b; }
.history-item.threat-high { border-left-color: #ed8936; }
.history-item.threat-critical { border-left-color: #f56565; }

.history-icon {
  font-size: 1rem;
}

.history-url {
  flex: 1;
  font-family: monospace;
  font-size: 0.8125rem;
  color: #4a5568;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-score {
  font-weight: 600;
  color: #2d3748;
}

.history-level {
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
}

.history-level.safe, .history-level.low { background: #c6f6d5; color: #22543d; }
.history-level.medium { background: #fefcbf; color: #744210; }
.history-level.high { background: #feebc8; color: #7b341e; }
.history-level.critical { background: #fed7d7; color: #742a2a; }
.history-level.unknown { background: #e2e8f0; color: #4a5568; }
</style>
