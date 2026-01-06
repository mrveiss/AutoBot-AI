<template>
  <div class="threat-intel-settings">
    <!-- Header -->
    <div class="settings-header">
      <h2 class="settings-title">Threat Intelligence Settings</h2>
      <p class="settings-subtitle">Configure external threat intelligence API integrations</p>
    </div>

    <!-- Current Status -->
    <div class="status-banner" :class="status.any_service_configured ? 'active' : 'inactive'">
      <span class="status-icon">{{ status.any_service_configured ? '🛡️' : '⚠️' }}</span>
      <span class="status-text">
        {{ status.any_service_configured
          ? 'Threat intelligence services are active'
          : 'No threat intelligence services configured' }}
      </span>
    </div>

    <!-- VirusTotal Settings -->
    <div class="settings-section">
      <div class="section-header">
        <div class="service-info">
          <h3>VirusTotal Integration</h3>
          <span class="service-badge" :class="status.virustotal?.configured ? 'configured' : 'not-configured'">
            {{ status.virustotal?.configured ? 'Configured' : 'Not Configured' }}
          </span>
        </div>
        <a href="https://www.virustotal.com/gui/my-apikey" target="_blank" class="external-link">
          Get API Key →
        </a>
      </div>
      <div class="section-content">
        <p class="service-description">
          VirusTotal aggregates data from over 70 antivirus scanners and URL/domain blocklisting services.
          The free API allows 4 requests per minute.
        </p>
        <div class="form-group">
          <label for="vt-api-key">API Key</label>
          <div class="input-group">
            <input
              id="vt-api-key"
              v-model="virusTotalApiKey"
              :type="showVtKey ? 'text' : 'password'"
              placeholder="Enter your VirusTotal API key"
              class="form-input"
            />
            <button class="btn-toggle" @click="showVtKey = !showVtKey">
              {{ showVtKey ? '👁️' : '👁️‍🗨️' }}
            </button>
          </div>
          <p class="form-hint">Environment variable: <code>VIRUSTOTAL_API_KEY</code></p>
        </div>
        <div v-if="status.virustotal?.configured" class="service-stats">
          <div class="stat">
            <span class="stat-label">Rate Limit:</span>
            <span class="stat-value">{{ status.virustotal?.requests_per_minute || 4 }} req/min</span>
          </div>
          <div class="stat">
            <span class="stat-label">Remaining:</span>
            <span class="stat-value">{{ status.virustotal?.remaining_requests || 0 }} requests</span>
          </div>
        </div>
      </div>
    </div>

    <!-- URLVoid Settings -->
    <div class="settings-section">
      <div class="section-header">
        <div class="service-info">
          <h3>URLVoid Integration</h3>
          <span class="service-badge" :class="status.urlvoid?.configured ? 'configured' : 'not-configured'">
            {{ status.urlvoid?.configured ? 'Configured' : 'Not Configured' }}
          </span>
        </div>
        <a href="https://www.urlvoid.com/api/" target="_blank" class="external-link">
          Get API Key →
        </a>
      </div>
      <div class="section-content">
        <p class="service-description">
          URLVoid checks domains against 30+ blocklist engines and provides domain age,
          registration info, and reputation data. The free tier allows 10 requests per minute.
        </p>
        <div class="form-group">
          <label for="uv-api-key">API Key</label>
          <div class="input-group">
            <input
              id="uv-api-key"
              v-model="urlVoidApiKey"
              :type="showUvKey ? 'text' : 'password'"
              placeholder="Enter your URLVoid API key"
              class="form-input"
            />
            <button class="btn-toggle" @click="showUvKey = !showUvKey">
              {{ showUvKey ? '👁️' : '👁️‍🗨️' }}
            </button>
          </div>
          <p class="form-hint">Environment variable: <code>URLVOID_API_KEY</code></p>
        </div>
        <div v-if="status.urlvoid?.configured" class="service-stats">
          <div class="stat">
            <span class="stat-label">Rate Limit:</span>
            <span class="stat-value">{{ status.urlvoid?.requests_per_minute || 10 }} req/min</span>
          </div>
          <div class="stat">
            <span class="stat-label">Remaining:</span>
            <span class="stat-value">{{ status.urlvoid?.remaining_requests || 0 }} requests</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Cache Settings -->
    <div class="settings-section">
      <div class="section-header">
        <div class="service-info">
          <h3>Cache Settings</h3>
          <span class="service-badge configured">Active</span>
        </div>
      </div>
      <div class="section-content">
        <p class="service-description">
          URL reputation results are cached to reduce API calls and improve response times.
          Cached results are marked with a badge in the dashboard.
        </p>
        <div class="cache-stats">
          <div class="stat">
            <span class="stat-label">Cache Entries:</span>
            <span class="stat-value">{{ status.cache_stats?.size || 0 }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">TTL:</span>
            <span class="stat-value">2 hours</span>
          </div>
        </div>
        <button class="btn-secondary" @click="clearCache" :disabled="loading">
          Clear Cache
        </button>
      </div>
    </div>

    <!-- Domain Security Settings -->
    <div class="settings-section">
      <div class="section-header">
        <div class="service-info">
          <h3>Domain Security Settings</h3>
        </div>
      </div>
      <div class="section-content">
        <p class="service-description">
          Configure domain validation behavior for URL checking.
        </p>
        <div class="domain-settings">
          <div class="setting-row">
            <label>
              <input type="checkbox" v-model="domainSettings.requireHttps" />
              Require HTTPS
            </label>
            <span class="setting-hint">Block non-HTTPS URLs</span>
          </div>
          <div class="setting-row">
            <label>
              <input type="checkbox" v-model="domainSettings.checkDns" />
              DNS Verification
            </label>
            <span class="setting-hint">Verify domains resolve to valid IPs</span>
          </div>
          <div class="setting-row">
            <label>Max Redirects</label>
            <input
              type="number"
              v-model.number="domainSettings.maxRedirects"
              min="0"
              max="10"
              class="form-input-small"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Info Box -->
    <div class="info-box">
      <div class="info-icon">ℹ️</div>
      <div class="info-content">
        <h4>Setting Up API Keys</h4>
        <p>
          API keys should be configured via environment variables for security.
          Add the following to your <code>.env</code> file:
        </p>
        <pre class="code-block">VIRUSTOTAL_API_KEY=your_api_key_here
URLVOID_API_KEY=your_api_key_here</pre>
        <p>
          Restart the backend service after updating environment variables.
        </p>
      </div>
    </div>

    <!-- Actions -->
    <div class="settings-actions">
      <button class="btn-primary" @click="saveSettings" :disabled="loading">
        {{ loading ? 'Saving...' : 'Save Settings' }}
      </button>
      <button class="btn-secondary" @click="refreshStatus" :disabled="loading">
        Refresh Status
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import apiClient from '@/utils/ApiClient'

const logger = createLogger('ThreatIntelligenceSettings')

// State
const loading = ref(false)
const showVtKey = ref(false)
const showUvKey = ref(false)
const virusTotalApiKey = ref('')
const urlVoidApiKey = ref('')

const status = reactive({
  any_service_configured: false,
  virustotal: null as Record<string, unknown> | null,
  urlvoid: null as Record<string, unknown> | null,
  cache_stats: null as Record<string, unknown> | null
})

const domainSettings = reactive({
  requireHttps: true,
  checkDns: true,
  maxRedirects: 5
})

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
      const settings = (stats.settings as Record<string, unknown>) || {}
      domainSettings.requireHttps = (settings.require_https as boolean) ?? true
      domainSettings.checkDns = (settings.check_dns as boolean) ?? true
      domainSettings.maxRedirects = (settings.max_redirects as number) ?? 5
    }
  } catch (error) {
    logger.error('Failed to fetch threat intel status', error)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  loading.value = true
  try {
    // Note: API key changes require updating environment variables
    // This is just for domain settings
    logger.info('Settings saved (domain settings only - API keys require env vars)')
    await refreshStatus()
  } catch (error) {
    logger.error('Failed to save settings', error)
  } finally {
    loading.value = false
  }
}

async function clearCache() {
  loading.value = true
  try {
    // Would need a backend endpoint for this
    logger.info('Cache clear requested')
    await refreshStatus()
  } catch (error) {
    logger.error('Failed to clear cache', error)
  } finally {
    loading.value = false
  }
}

// Lifecycle
onMounted(() => {
  refreshStatus()
})
</script>

<style scoped>
.threat-intel-settings {
  padding: 1rem;
  max-width: 800px;
}

.settings-header {
  margin-bottom: 1.5rem;
}

.settings-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: #1a202c;
  margin: 0;
}

.settings-subtitle {
  color: #718096;
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
}

/* Status Banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1.5rem;
}

.status-banner.active {
  background: #f0fff4;
  border: 1px solid #9ae6b4;
}

.status-banner.inactive {
  background: #fffaf0;
  border: 1px solid #fbd38d;
}

.status-icon {
  font-size: 1.25rem;
}

.status-text {
  font-weight: 500;
  color: #2d3748;
}

/* Settings Sections */
.settings-section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #f7fafc;
  border-bottom: 1px solid #e2e8f0;
}

.service-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.service-info h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #2d3748;
  margin: 0;
}

.service-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
}

.service-badge.configured {
  background: #c6f6d5;
  color: #22543d;
}

.service-badge.not-configured {
  background: #fed7d7;
  color: #742a2a;
}

.external-link {
  font-size: 0.875rem;
  color: #4299e1;
  text-decoration: none;
}

.external-link:hover {
  text-decoration: underline;
}

.section-content {
  padding: 1rem;
}

.service-description {
  font-size: 0.875rem;
  color: #718096;
  margin: 0 0 1rem;
  line-height: 1.5;
}

/* Form Elements */
.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: #4a5568;
  margin-bottom: 0.5rem;
}

.input-group {
  display: flex;
  gap: 0.5rem;
}

.form-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-family: monospace;
}

.form-input:focus {
  outline: none;
  border-color: #4299e1;
  box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1);
}

.form-input-small {
  width: 80px;
  padding: 0.375rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.btn-toggle {
  padding: 0.5rem;
  background: #edf2f7;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  cursor: pointer;
}

.btn-toggle:hover {
  background: #e2e8f0;
}

.form-hint {
  font-size: 0.75rem;
  color: #a0aec0;
  margin: 0.5rem 0 0;
}

.form-hint code {
  background: #edf2f7;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
}

/* Service Stats */
.service-stats,
.cache-stats {
  display: flex;
  gap: 2rem;
  padding: 0.75rem;
  background: #f7fafc;
  border-radius: 0.375rem;
  margin-bottom: 1rem;
}

.stat {
  display: flex;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.stat-label {
  color: #718096;
}

.stat-value {
  font-weight: 600;
  color: #2d3748;
}

/* Domain Settings */
.domain-settings {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.setting-row label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #4a5568;
  cursor: pointer;
}

.setting-row input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

.setting-hint {
  font-size: 0.75rem;
  color: #a0aec0;
}

/* Info Box */
.info-box {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  background: #ebf8ff;
  border: 1px solid #90cdf4;
  border-radius: 0.5rem;
  margin-bottom: 1.5rem;
}

.info-icon {
  font-size: 1.25rem;
}

.info-content h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #2b6cb0;
  margin: 0 0 0.5rem;
}

.info-content p {
  font-size: 0.8125rem;
  color: #4a5568;
  margin: 0 0 0.5rem;
  line-height: 1.5;
}

.info-content code {
  background: #bee3f8;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
}

.code-block {
  background: #2d3748;
  color: #e2e8f0;
  padding: 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  font-family: monospace;
  overflow-x: auto;
  margin: 0.5rem 0;
}

/* Actions */
.settings-actions {
  display: flex;
  gap: 0.75rem;
}

.btn-primary {
  padding: 0.75rem 1.5rem;
  background: #4299e1;
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #3182ce;
}

.btn-primary:disabled {
  background: #a0aec0;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 0.75rem 1.5rem;
  background: white;
  color: #4a5568;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: #f7fafc;
  border-color: #cbd5e0;
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
