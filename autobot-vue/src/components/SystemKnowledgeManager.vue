<template>
  <div class="system-knowledge-manager">
    <div class="header">
      <p class="subtitle">Initialize, reindex, and repopulate knowledge base</p>
    </div>

    <!-- Host Selection for Man Pages -->
    <div class="host-selection">
      <label for="host-select">Target Host for Man Pages:</label>
      <select id="host-select" v-model="selectedHost" class="host-select">
        <option value="all">All Hosts</option>
        <option value="172.16.168.20">Main (172.16.168.20)</option>
        <option value="172.16.168.21">Frontend (172.16.168.21)</option>
        <option value="172.16.168.22">NPU Worker (172.16.168.22)</option>
        <option value="172.16.168.23">Redis (172.16.168.23)</option>
        <option value="172.16.168.24">AI Stack (172.16.168.24)</option>
        <option value="172.16.168.25">Browser (172.16.168.25)</option>
      </select>
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
        @click="generateVectorEmbeddings"
        :disabled="isVectorizing"
        class="btn btn-primary btn-highlight"
        title="Batched vector generation: Processes 50 facts per batch with 0.5s delay. Skips already vectorized facts. Safe to run periodically to vectorize new facts."
      >
        <span class="icon">🧬</span>
        {{ isVectorizing ? 'Vectorizing...' : `Vectorize Facts (${stats.total_facts - (stats.total_vectors || 0)} pending)` }}
      </button>

      <button
        @click="initializeMachineKnowledge"
        :disabled="isInitializing"
        class="btn btn-primary"
        title="Create vector embeddings for search functionality"
      >
        <span class="icon">🚀</span>
        {{ isInitializing ? 'Initializing...' : 'Initialize Machine Knowledge' }}
      </button>

      <button
        @click="reindexDocuments"
        :disabled="isReindexing"
        class="btn btn-primary"
        title="Reindex all documents in the knowledge base"
      >
        <span class="icon">🔄</span>
        {{ isReindexing ? 'Reindexing...' : 'Reindex Documents' }}
      </button>

      <button
        @click="refreshSystemKnowledge"
        :disabled="isRefreshing"
        class="btn btn-secondary"
      >
        <span class="icon">📋</span>
        {{ isRefreshing ? 'Refreshing...' : 'Refresh Man Pages' }}
      </button>

      <button
        @click="populateManPages"
        :disabled="isPopulating"
        class="btn btn-secondary"
      >
        <span class="icon">⚙️</span>
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
            <strong>{{ formatKey(key) }}:</strong> {{ typeof value === 'object' ? JSON.stringify(value) : value }}
          </p>
        </div>
      </div>
    </div>

    <!-- Info Section -->
    <div class="info-section">
      <h3>ℹ️ About System Knowledge</h3>
      <div class="info-content">
        <p>
          <strong>Initialize Machine Knowledge:</strong> Creates vector embeddings for all documents in the knowledge base.
          Required for search functionality to work. Run this first if search returns no results.
        </p>
        <p>
          <strong>Reindex Documents:</strong> Rebuilds the entire knowledge base from scratch, repopulating with:
          text entries, uploaded files, and indexed websites. Use when documents seem outdated or corrupted.
        </p>
        <p>
          <strong>Refresh Man Pages:</strong> Scans and indexes ALL Linux manual pages available on this machine.
          Enables the chat agent to understand and help with command-line tools.
        </p>
        <p>
          <strong>Populate Common Commands:</strong> Quick index of frequently-used commands (ls, cd, grep, etc).
          Faster alternative to full man page refresh.
        </p>
        <p>
          <strong>Index AutoBot Docs:</strong> Indexes project guidelines, API references, architecture docs,
          and troubleshooting guides. Enables the chat agent to be self-aware of its capabilities.
        </p>
        <p>
          <strong>When to Use:</strong> Initialize after first install, Reindex when documents are outdated,
          Refresh after installing packages or updating docs.
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
import { useKnowledgeBase } from '@/composables/useKnowledgeBase';

export default {
  name: 'SystemKnowledgeManager',

  setup() {
    // Use the shared composable
    const {
      fetchStats: fetchStatsAPI,
      initializeMachineKnowledge: initializeMachineKnowledgeAPI,
      refreshSystemKnowledge: refreshSystemKnowledgeAPI,
      populateManPages: populateManPagesAPI,
      populateAutoBotDocs: populateAutoBotDocsAPI,
      vectorizeFacts: vectorizeFactsAPI,
      formatKey
    } = useKnowledgeBase();

    const stats = ref({});
    const commandsIndexed = ref(0);
    const docsIndexed = ref(0);
    const selectedHost = ref('all');
    const isLoading = ref(false);
    const isInitializing = ref(false);
    const isReindexing = ref(false);
    const isRefreshing = ref(false);
    const isPopulating = ref(false);
    const isDocPopulating = ref(false);
    const isVectorizing = ref(false);
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
        const response = await fetchStatsAPI();
        console.log('[SystemKnowledgeManager] fetchStats response:', response);

        if (response) {
          // Ensure we're not storing a Promise
          if (response instanceof Promise) {
            console.error('[SystemKnowledgeManager] Response is a Promise!', response);
            const resolved = await response;
            stats.value = resolved;
          } else {
            stats.value = response;
          }

          // Extract command and doc counts from categories if available
          if (stats.value.categories) {
            commandsIndexed.value = stats.value.categories.system_commands || 0;
            docsIndexed.value = stats.value.categories.autobot_documentation || 0;
          }

          addLogEntry('Stats refreshed successfully', 'success');
        }
      } catch (error) {
        console.error('Failed to fetch stats:', error);
        addLogEntry('Failed to fetch stats', 'error');
      } finally {
        isLoading.value = false;
      }
    };

    const initializeMachineKnowledge = async () => {
      if (isInitializing.value) return;

      if (!confirm('Initialize machine knowledge? This creates vector embeddings for search. Continue?')) {
        return;
      }

      isInitializing.value = true;
      progressMessage.value = 'Initializing machine knowledge...';
      progressPercent.value = 0;
      lastResult.value = null;

      try {
        addLogEntry('Initializing machine knowledge', 'info');

        const progressInterval = setInterval(() => {
          if (progressPercent.value < 90) {
            progressPercent.value += 10;
          }
        }, 2000);

        const response = await initializeMachineKnowledgeAPI(false);

        clearInterval(progressInterval);
        progressPercent.value = 100;
        progressMessage.value = 'Initialization complete!';

        lastResult.value = {
          status: 'success',
          message: 'Machine knowledge initialized successfully',
          details: response || {}
        };

        addLogEntry('Machine knowledge initialized', 'success');
        await fetchStats();

      } catch (error) {
        let errorMessage = 'Failed to initialize machine knowledge';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        console.error('[SystemKnowledgeManager] Initialization error:', error);
        
        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`Machine knowledge initialization failed: ${errorMessage}`, 'error');
      } finally {
        isInitializing.value = false;
        setTimeout(() => {
          progressMessage.value = '';
          progressPercent.value = 0;
        }, 3000);
      }
    };

    const reindexDocuments = async () => {
      if (isReindexing.value) return;

      if (!confirm('Reindex all documents? This will rebuild the knowledge base. Continue?')) {
        return;
      }

      isReindexing.value = true;
      progressMessage.value = 'Reindexing documents...';
      progressPercent.value = 0;
      lastResult.value = null;

      try {
        addLogEntry('Starting document reindexing', 'info');

        const progressInterval = setInterval(() => {
          if (progressPercent.value < 90) {
            progressPercent.value += 5;
          }
        }, 1500);

        // Use the initialize function with force=true to reindex
        const response = await initializeMachineKnowledgeAPI(true);

        clearInterval(progressInterval);
        progressPercent.value = 100;
        progressMessage.value = 'Reindexing complete!';

        lastResult.value = {
          status: 'success',
          message: 'Documents reindexed successfully',
          details: response || {}
        };

        addLogEntry('Documents reindexed', 'success');
        await fetchStats();

      } catch (error) {
        let errorMessage = 'Failed to reindex documents';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        console.error('[SystemKnowledgeManager] Reindexing error:', error);
        
        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`Document reindexing failed: ${errorMessage}`, 'error');
      } finally {
        isReindexing.value = false;
        setTimeout(() => {
          progressMessage.value = '';
          progressPercent.value = 0;
        }, 3000);
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

        const response = await refreshSystemKnowledgeAPI();

        clearInterval(progressInterval);
        progressPercent.value = 100;
        progressMessage.value = 'Refresh complete!';

        lastResult.value = {
          status: 'success',
          message: response.message || 'System knowledge refreshed successfully',
          details: {
            'Commands Indexed': response.commands_indexed || 0,
            'Total Facts': response.total_facts || 0
          }
        };

        commandsIndexed.value = response.commands_indexed || 0;
        addLogEntry(`Indexed ${commandsIndexed.value} commands`, 'success');

        // Refresh stats
        await fetchStats();

      } catch (error) {
        let errorMessage = 'Failed to refresh system knowledge';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        console.error('[SystemKnowledgeManager] Refresh error:', error);
        
        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`System knowledge refresh failed: ${errorMessage}`, 'error');
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

        const response = await populateManPagesAPI();

        lastResult.value = {
          status: 'success',
          message: response.message || 'Man pages populated successfully',
          details: {
            'Items Added': response.items_added || 0,
            'Total Commands': response.total_commands || 0
          }
        };

        addLogEntry(`Populated ${response.items_added || 0} man pages`, 'success');
        await fetchStats();

      } catch (error) {
        let errorMessage = 'Failed to populate man pages';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        console.error('[SystemKnowledgeManager] Man pages error:', error);
        
        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`Man pages population failed: ${errorMessage}`, 'error');
      } finally {
        isPopulating.value = false;
        progressMessage.value = '';
      }
    };

    const populateAutoBotDocs = async () => {
      if (isDocPopulating.value) return;

      // Ask if user wants to force reindex all files
      const forceReindex = confirm('Index AutoBot documentation?\n\nChoose:\n- OK: Force reindex ALL 182 docs files (ignores cache)\n- Cancel: Quick update (only new/changed files)');

      isDocPopulating.value = true;
      progressMessage.value = forceReindex ? 'Force reindexing ALL AutoBot documentation...' : 'Indexing AutoBot documentation...';
      lastResult.value = null;

      try {
        addLogEntry(forceReindex ? 'Force reindexing AutoBot documentation' : 'Indexing AutoBot documentation', 'info');

        const response = await populateAutoBotDocsAPI(forceReindex);

        lastResult.value = {
          status: 'success',
          message: response.message || 'Documentation indexed successfully',
          details: {
            'Items Added': response.items_added || 0,
            'Items Skipped': response.items_skipped || 0,
            'Items Failed': response.items_failed || 0,
            'Total Files': response.total_files || 0
          }
        };

        docsIndexed.value = response.items_added || 0;
        addLogEntry(`Indexed ${response.items_added || 0} documentation files (${response.items_skipped || 0} skipped)`, 'success');
        await fetchStats();

      } catch (error) {
        let errorMessage = 'Failed to index documentation';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        console.error('[SystemKnowledgeManager] Documentation indexing error:', error);
        
        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`Documentation indexing failed: ${errorMessage}`, 'error');
      } finally {
        isDocPopulating.value = false;
        progressMessage.value = '';
      }
    };

    const generateVectorEmbeddings = async () => {
      if (isVectorizing.value) return;

      const totalFacts = stats.value.total_facts || 0;
      const totalVectors = stats.value.total_vectors || 0;
      const needsVectorization = totalFacts - totalVectors;

      if (!confirm(
        `Generate vector embeddings using batched processing?\n\n` +
        `Total Facts: ${totalFacts}\n` +
        `Already Vectorized: ${totalVectors}\n` +
        `Needs Vectorization: ${needsVectorization}\n\n` +
        `Process: 50 facts per batch, 0.5s delay between batches\n` +
        `This prevents resource lockup and can be run periodically.\n\n` +
        `Continue?`
      )) {
        return;
      }

      isVectorizing.value = true;
      progressMessage.value = 'Starting batched vectorization...';
      progressPercent.value = 0;
      lastResult.value = null;

      try {
        addLogEntry('Starting batched vector embeddings generation', 'info');

        const progressInterval = setInterval(() => {
          if (progressPercent.value < 90) {
            progressPercent.value += 5;
            if (progressPercent.value < 30) {
              progressMessage.value = 'Processing batch 1... (Loading facts from Redis)';
            } else if (progressPercent.value < 60) {
              progressMessage.value = 'Processing batches... (Generating embeddings)';
            } else {
              progressMessage.value = 'Final batch... (Building search index)';
            }
          }
        }, 2000);

        // Call with batched parameters: 50 facts per batch, 0.5s delay, skip existing vectors
        const response = await vectorizeFactsAPI(50, 0.5, true);

        clearInterval(progressInterval);
        progressPercent.value = 100;
        progressMessage.value = 'Batched vectorization complete!';

        lastResult.value = {
          status: 'success',
          message: response.message || 'Vector embeddings generated successfully',
          details: {
            'Total Facts': response.processed || 0,
            'Successfully Vectorized': response.success || 0,
            'Skipped (Already Vectorized)': response.skipped || 0,
            'Failed': response.failed || 0,
            'Batches Processed': response.batches || 0
          }
        };

        addLogEntry(
          `Batched vectorization: ${response.success || 0} created, ${response.skipped || 0} skipped, ${response.batches || 0} batches`,
          'success'
        );
        await fetchStats();

      } catch (error) {
        // Enhanced error handling for fetch-style errors (not axios)
        let errorMessage = 'Failed to generate vector embeddings';
        
        if (error instanceof Error) {
          errorMessage = error.message;
        } else if (typeof error === 'string') {
          errorMessage = error;
        }
        
        console.error('[SystemKnowledgeManager] Vectorization error:', error);
        
        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`Batched vectorization failed: ${errorMessage}`, 'error');
      } finally {
        isVectorizing.value = false;
        setTimeout(() => {
          progressMessage.value = '';
          progressPercent.value = 0;
        }, 3000);
      }
    };

    onMounted(() => {
      fetchStats();
    });

    return {
      stats,
      commandsIndexed,
      docsIndexed,
      selectedHost,
      isLoading,
      isInitializing,
      isReindexing,
      isRefreshing,
      isPopulating,
      isDocPopulating,
      isVectorizing,
      progressMessage,
      progressPercent,
      lastResult,
      activityLog,
      fetchStats,
      initializeMachineKnowledge,
      reindexDocuments,
      refreshSystemKnowledge,
      populateManPages,
      populateAutoBotDocs,
      generateVectorEmbeddings,
      formatKey
    };
  }
};
</script>

<style scoped>
.system-knowledge-manager {
  padding: 20px;
  width: 100%;
  flex: 1;
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

.host-selection {
  margin-bottom: 25px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 15px;
}

.host-selection label {
  font-weight: 600;
  color: #2c3e50;
  white-space: nowrap;
}

.host-select {
  flex: 1;
  max-width: 400px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  font-size: 14px;
  cursor: pointer;
}

.host-select:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.1);
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

.btn-highlight {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: 2px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
  font-weight: 600;
}

.btn-highlight:hover:not(:disabled) {
  background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
  transform: translateY(-2px);
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
