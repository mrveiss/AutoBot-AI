<template>
  <div class="system-knowledge-manager">
    <div class="header">
      <h2>🧠 System Knowledge Management</h2>
      <p class="subtitle">Manage man pages and documentation indexing</p>
    </div>

    <!-- Status Cards -->
    <div class="status-cards">
      <div class="status-card">
        <div class="status-icon">📚</div>
        <div class="status-content">
          <h3>{{ stats.total_facts || 0 }}</h3>
          <p>Total Facts</p>
        </div>
      </div>

      <div class="status-card">
        <div class="status-icon">🔍</div>
        <div class="status-content">
          <h3>{{ stats.total_vectors || 0 }}</h3>
          <p>Searchable Vectors</p>
        </div>
      </div>

      <div class="status-card">
        <div class="status-icon">⚙️</div>
        <div class="status-content">
          <h3>{{ commandsIndexed || 0 }}</h3>
          <p>Commands Indexed</p>
        </div>
      </div>

      <div class="status-card">
        <div class="status-icon">📄</div>
        <div class="status-content">
          <h3>{{ docsIndexed || 0 }}</h3>
          <p>Docs Indexed</p>
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="actions">
      <button
        @click="refreshSystemKnowledge"
        :disabled="isRefreshing"
        class="btn btn-primary"
      >
        <span class="icon">🔄</span>
        {{ isRefreshing ? 'Refreshing...' : 'Refresh All Man Pages' }}
      </button>

      <button
        @click="populateManPages"
        :disabled="isPopulating"
        class="btn btn-secondary"
      >
        <span class="icon">📋</span>
        {{ isPopulating ? 'Populating...' : 'Populate Common Commands' }}
      </button>

      <button
        @click="populateAutoBotDocs"
        :disabled="isDocPopulating"
        class="btn btn-secondary"
      >
        <span class="icon">📖</span>
        {{ isDocPopulating ? 'Populating...' : 'Index AutoBot Docs' }}
      </button>

      <button
        @click="fetchStats"
        :disabled="isLoading"
        class="btn btn-outline"
      >
        <span class="icon">📊</span>
        Refresh Stats
      </button>
    </div>

    <!-- Progress Display -->
    <div v-if="progressMessage" class="progress-display">
      <div class="progress-content">
        <div class="spinner"></div>
        <p>{{ progressMessage }}</p>
      </div>
      <div v-if="progressPercent > 0" class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- Results Display -->
    <div v-if="lastResult" class="result-display" :class="lastResult.status">
      <div class="result-icon">
        {{ lastResult.status === 'success' ? '✅' : '❌' }}
      </div>
      <div class="result-content">
        <h4>{{ lastResult.status === 'success' ? 'Success' : 'Error' }}</h4>
        <p>{{ lastResult.message }}</p>
        <div v-if="lastResult.details" class="result-details">
          <p v-for="(value, key) in lastResult.details" :key="key">
            <strong>{{ formatKey(key) }}:</strong> {{ value }}
          </p>
        </div>
      </div>
    </div>

    <!-- Info Section -->
    <div class="info-section">
      <h3>ℹ️ About System Knowledge</h3>
      <div class="info-content">
        <p>
          <strong>Man Pages:</strong> Linux manual pages for all CLI commands available on this machine.
          Enables the chat agent to understand and help with command-line tools.
        </p>
        <p>
          <strong>AutoBot Documentation:</strong> Project guidelines, API references, architecture docs,
          and troubleshooting guides. Enables the chat agent to be self-aware of its capabilities.
        </p>
        <p>
          <strong>When to Refresh:</strong> After installing new packages, updating the system,
          or making changes to AutoBot documentation.
        </p>
      </div>
    </div>

    <!-- Recent Activity Log -->
    <div v-if="activityLog.length > 0" class="activity-log">
      <h3>📝 Recent Activity</h3>
      <div class="log-entries">
        <div v-for="(entry, index) in activityLog" :key="index" class="log-entry">
          <span class="log-time">{{ entry.time }}</span>
          <span class="log-message">{{ entry.message }}</span>
          <span class="log-status" :class="entry.status">{{ entry.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';
import apiClient from '@/utils/ApiClient';

export default {
  name: 'SystemKnowledgeManager',

  setup() {
    const stats = ref({});
    const commandsIndexed = ref(0);
    const docsIndexed = ref(0);
    const isLoading = ref(false);
    const isRefreshing = ref(false);
    const isPopulating = ref(false);
    const isDocPopulating = ref(false);
    const progressMessage = ref('');
    const progressPercent = ref(0);
    const lastResult = ref(null);
    const activityLog = ref([]);

    const addLogEntry = (message, status) => {
      const time = new Date().toLocaleTimeString();
      activityLog.value.unshift({ time, message, status });
      if (activityLog.value.length > 10) {
        activityLog.value.pop();
      }
    };

    const fetchStats = async () => {
      isLoading.value = true;
      try {
        const response = await apiClient.get('/api/knowledge_base/stats');
        stats.value = response.data;

        // Extract command and doc counts from categories if available
        if (stats.value.categories) {
          commandsIndexed.value = stats.value.categories.system_commands || 0;
          docsIndexed.value = stats.value.categories.autobot_documentation || 0;
        }

        addLogEntry('Stats refreshed successfully', 'success');
      } catch (error) {
        console.error('Failed to fetch stats:', error);
        addLogEntry('Failed to fetch stats', 'error');
      } finally {
        isLoading.value = false;
      }
    };

    const refreshSystemKnowledge = async () => {
      if (isRefreshing.value) return;

      if (!confirm('This will index ALL man pages on the system. This may take 5-10 minutes. Continue?')) {
        return;
      }

      isRefreshing.value = true;
      progressMessage.value = 'Scanning system for all available commands...';
      progressPercent.value = 0;
      lastResult.value = null;

      try {
        addLogEntry('Starting comprehensive system knowledge refresh', 'info');

        // Simulate progress updates
        const progressInterval = setInterval(() => {
          if (progressPercent.value < 90) {
            progressPercent.value += 5;
            if (progressPercent.value < 30) {
              progressMessage.value = 'Scanning system for commands...';
            } else if (progressPercent.value < 60) {
              progressMessage.value = 'Indexing man pages...';
            } else {
              progressMessage.value = 'Creating vector embeddings...';
            }
          }
        }, 3000);

        const response = await apiClient.post('/knowledge_base/refresh_system_knowledge', {});

        clearInterval(progressInterval);
        progressPercent.value = 100;
        progressMessage.value = 'Refresh complete!';

        lastResult.value = {
          status: 'success',
          message: response.data.message || 'System knowledge refreshed successfully',
          details: {
            'Commands Indexed': response.data.commands_indexed || 0,
            'Total Facts': response.data.total_facts || 0
          }
        };

        commandsIndexed.value = response.data.commands_indexed || 0;
        addLogEntry(`Indexed ${commandsIndexed.value} commands`, 'success');

        // Refresh stats
        await fetchStats();

      } catch (error) {
        lastResult.value = {
          status: 'error',
          message: error.response?.data?.detail || 'Failed to refresh system knowledge'
        };
        addLogEntry('System knowledge refresh failed', 'error');
      } finally {
        isRefreshing.value = false;
        setTimeout(() => {
          progressMessage.value = '';
          progressPercent.value = 0;
        }, 3000);
      }
    };

    const populateManPages = async () => {
      if (isPopulating.value) return;

      isPopulating.value = true;
      progressMessage.value = 'Populating common command man pages...';
      lastResult.value = null;

      try {
        addLogEntry('Populating common man pages', 'info');

        const response = await apiClient.post('/knowledge_base/populate_man_pages', {});

        lastResult.value = {
          status: 'success',
          message: response.data.message || 'Man pages populated successfully',
          details: {
            'Items Added': response.data.items_added || 0,
            'Total Commands': response.data.total_commands || 0
          }
        };

        addLogEntry(`Populated ${response.data.items_added} man pages`, 'success');
        await fetchStats();

      } catch (error) {
        lastResult.value = {
          status: 'error',
          message: error.response?.data?.detail || 'Failed to populate man pages'
        };
        addLogEntry('Man pages population failed', 'error');
      } finally {
        isPopulating.value = false;
        progressMessage.value = '';
      }
    };

    const populateAutoBotDocs = async () => {
      if (isDocPopulating.value) return;

      isDocPopulating.value = true;
      progressMessage.value = 'Indexing AutoBot documentation...';
      lastResult.value = null;

      try {
        addLogEntry('Indexing AutoBot documentation', 'info');

        const response = await apiClient.post('/knowledge_base/populate_autobot_docs', {});

        lastResult.value = {
          status: 'success',
          message: response.data.message || 'Documentation indexed successfully',
          details: {
            'Items Added': response.data.items_added || 0
          }
        };

        docsIndexed.value = response.data.items_added || 0;
        addLogEntry(`Indexed ${docsIndexed.value} documentation files`, 'success');
        await fetchStats();

      } catch (error) {
        lastResult.value = {
          status: 'error',
          message: error.response?.data?.detail || 'Failed to index documentation'
        };
        addLogEntry('Documentation indexing failed', 'error');
      } finally {
        isDocPopulating.value = false;
        progressMessage.value = '';
      }
    };

    const formatKey = (key) => {
      return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    };

    onMounted(() => {
      fetchStats();
    });

    return {
      stats,
      commandsIndexed,
      docsIndexed,
      isLoading,
      isRefreshing,
      isPopulating,
      isDocPopulating,
      progressMessage,
      progressPercent,
      lastResult,
      activityLog,
      fetchStats,
      refreshSystemKnowledge,
      populateManPages,
      populateAutoBotDocs,
      formatKey
    };
  }
};
</script>

<style scoped>
.system-knowledge-manager {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.header {
  margin-bottom: 30px;
}

.header h2 {
  margin: 0 0 10px 0;
  color: #2c3e50;
}

.subtitle {
  margin: 0;
  color: #7f8c8d;
  font-size: 14px;
}

.status-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.status-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  display: flex;
  align-items: center;
  gap: 15px;
}

.status-icon {
  font-size: 32px;
}

.status-content h3 {
  margin: 0 0 5px 0;
  font-size: 24px;
  color: #2c3e50;
}

.status-content p {
  margin: 0;
  color: #7f8c8d;
  font-size: 12px;
}

.actions {
  display: flex;
  gap: 15px;
  margin-bottom: 30px;
  flex-wrap: wrap;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #3498db;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2980b9;
}

.btn-secondary {
  background: #2ecc71;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #27ae60;
}

.btn-outline {
  background: white;
  color: #3498db;
  border: 2px solid #3498db;
}

.btn-outline:hover:not(:disabled) {
  background: #3498db;
  color: white;
}

.progress-display {
  background: #ecf0f1;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.progress-content {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 15px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #ecf0f1;
  border-top-color: #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.progress-bar {
  height: 6px;
  background: #ddd;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #3498db;
  transition: width 0.5s;
}

.result-display {
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 30px;
  display: flex;
  gap: 15px;
}

.result-display.success {
  background: #d5f4e6;
  border-left: 4px solid #2ecc71;
}

.result-display.error {
  background: #fadbd8;
  border-left: 4px solid #e74c3c;
}

.result-icon {
  font-size: 32px;
}

.result-content h4 {
  margin: 0 0 10px 0;
}

.result-content p {
  margin: 0 0 10px 0;
}

.result-details {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid rgba(0,0,0,0.1);
}

.result-details p {
  margin: 5px 0;
  font-size: 14px;
}

.info-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 30px;
}

.info-section h3 {
  margin: 0 0 15px 0;
  color: #2c3e50;
}

.info-content p {
  margin: 10px 0;
  line-height: 1.6;
  color: #555;
}

.activity-log {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.activity-log h3 {
  margin: 0 0 15px 0;
  color: #2c3e50;
}

.log-entries {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.log-entry {
  display: flex;
  gap: 15px;
  padding: 10px;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 13px;
}

.log-time {
  color: #7f8c8d;
  font-family: monospace;
  min-width: 80px;
}

.log-message {
  flex: 1;
  color: #2c3e50;
}

.log-status {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.log-status.success {
  background: #d5f4e6;
  color: #27ae60;
}

.log-status.error {
  background: #fadbd8;
  color: #e74c3c;
}

.log-status.info {
  background: #d6eaf8;
  color: #2980b9;
}
</style>