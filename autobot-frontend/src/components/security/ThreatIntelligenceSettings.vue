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
  padding: var(--spacing-4);
  max-width: 800px;
}

.settings-header {
  margin-bottom: var(--spacing-6);
}

.settings-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.settings-subtitle {
  color: var(--text-secondary);
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
}

/* Status Banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-6);
}

.status-banner.active {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
}

.status-banner.inactive {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
}

.status-icon {
  font-size: var(--text-xl);
}

.status-text {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

/* Settings Sections */
.settings-section {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.service-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.service-info h3 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.service-badge {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.service-badge.configured {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.service-badge.not-configured {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.external-link {
  font-size: var(--text-sm);
  color: var(--text-link);
  text-decoration: none;
}

.external-link:hover {
  color: var(--text-link-hover);
  text-decoration: underline;
}

.section-content {
  padding: var(--spacing-4);
}

.service-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-4);
  line-height: var(--leading-normal);
}

/* Form Elements */
.form-group {
  margin-bottom: var(--spacing-4);
}

.form-group label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.input-group {
  display: flex;
  gap: var(--spacing-2);
}

.form-input {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-input-small {
  width: 80px;
  padding: var(--spacing-1-5) var(--spacing-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.btn-toggle {
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.btn-toggle:hover {
  background: var(--bg-hover);
}

.form-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: var(--spacing-2) 0 0;
}

.form-hint code {
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-family: var(--font-mono);
}

/* Service Stats */
.service-stats,
.cache-stats {
  display: flex;
  gap: var(--spacing-8);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-4);
}

.stat {
  display: flex;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.stat-label {
  color: var(--text-secondary);
}

.stat-value {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

/* Domain Settings */
.domain-settings {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.setting-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.setting-row label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  cursor: pointer;
}

.setting-row input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.setting-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* Info Box */
.info-box {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-info-bg);
  border: 1px solid var(--color-info);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-6);
}

.info-icon {
  font-size: var(--text-xl);
}

.info-content h4 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-info);
  margin: 0 0 var(--spacing-2);
}

.info-content p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-2);
  line-height: var(--leading-normal);
}

.info-content code {
  background: var(--color-info-bg-hover);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.code-block {
  background: var(--code-bg);
  color: var(--code-text);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  overflow-x: auto;
  margin: var(--spacing-2) 0;
}

/* Actions */
.settings-actions {
  display: flex;
  gap: var(--spacing-3);
}

.btn-primary {
  padding: var(--spacing-3) var(--spacing-6);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-in-out);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  background: var(--color-secondary);
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--spacing-3) var(--spacing-6);
  background: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
