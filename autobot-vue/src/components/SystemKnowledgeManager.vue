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
        <option v-for="machine in machines" :key="machine.id" :value="machine.ip">
          {{ machine.name }} ({{ machine.ip }})
        </option>
      </select>
    </div>

    <!-- Status Cards -->
    <div class="status-cards">
      <BasePanel variant="elevated" size="small">
        <div class="status-card-content">
          <div class="status-icon">📚</div>
          <div class="status-content">
            <h3>{{ stats.total_facts || 0 }}</h3>
            <p>Total Facts</p>
          </div>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small">
        <div class="status-card-content">
          <div class="status-icon">🔍</div>
          <div class="status-content">
            <h3>{{ stats.total_vectors || 0 }}</h3>
            <p>Searchable Vectors</p>
          </div>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small">
        <div class="status-card-content">
          <div class="status-icon">⚙️</div>
          <div class="status-content">
            <h3>{{ commandsIndexed || 0 }}</h3>
            <p>Commands Indexed</p>
          </div>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small">
        <div class="status-card-content">
          <div class="status-icon">📄</div>
          <div class="status-content">
            <h3>{{ docsIndexed || 0 }}</h3>
            <p>Docs Indexed</p>
          </div>
        </div>
      </BasePanel>
    </div>

    <!-- Action Buttons -->
    <div class="actions">
      <BaseButton
        variant="primary"
        @click="generateVectorEmbeddings"
        :loading="isVectorizing"
        title="Batched vector generation: Processes 50 facts per batch with 0.5s delay. Skips already vectorized facts. Safe to run periodically to vectorize new facts."
        class="btn-highlight"
      >
        <span class="icon">🧬</span>
        {{ isVectorizing ? 'Vectorizing...' : getVectorizeButtonText() }}
      </BaseButton>

      <BaseButton
        variant="primary"
        @click="initializeMachineKnowledge"
        :loading="isInitializing"
        title="Create vector embeddings for search functionality"
      >
        <span class="icon">🚀</span>
        {{ isInitializing ? 'Initializing...' : 'Initialize Machine Knowledge' }}
      </BaseButton>

      <BaseButton
        variant="primary"
        @click="reindexDocuments"
        :loading="isReindexing"
        title="Reindex all documents in the knowledge base"
      >
        <span class="icon">🔄</span>
        {{ isReindexing ? 'Reindexing...' : 'Reindex Documents' }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="refreshSystemKnowledge"
        :loading="isRefreshing"
      >
        <span class="icon">📋</span>
        {{ isRefreshing ? 'Refreshing...' : 'Refresh Man Pages' }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="populateManPages"
        :loading="isPopulating"
      >
        <span class="icon">⚙️</span>
        {{ isPopulating ? 'Populating...' : 'Populate Common Commands' }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="populateAutoBotDocs"
        :loading="isDocPopulating"
      >
        <span class="icon">📖</span>
        {{ isDocPopulating ? 'Populating...' : 'Index AutoBot Docs' }}
      </BaseButton>

      <BaseButton
        variant="outline"
        @click="fetchStats"
        :disabled="isLoading"
      >
        <span class="icon">📊</span>
        Refresh Stats
      </BaseButton>
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
    <BasePanel variant="bordered" size="medium">
      <template #header>
        <h3>ℹ️ About System Knowledge</h3>
      </template>
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
    </BasePanel>

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
import { ref, onMounted, computed } from 'vue';
import { useKnowledgeBase } from '@/composables/useKnowledgeBase';
import { useKnowledgeStore } from '@/stores/useKnowledgeStore';  // NEW: Use shared store
import { useAsyncOperation } from '@/composables/useAsyncOperation';
import appConfig from '@/config/AppConfig.js';
import BaseButton from '@/components/base/BaseButton.vue';
import BasePanel from '@/components/base/BasePanel.vue';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for SystemKnowledgeManager
const logger = createLogger('SystemKnowledgeManager');

export default {
  name: 'SystemKnowledgeManager',
  components: {
    BaseButton,
    BasePanel
  },

  setup() {
    // Use the shared composable
    const {
      initializeMachineKnowledge: initializeMachineKnowledgeAPI,
      refreshSystemKnowledge: refreshSystemKnowledgeAPI,
      pollJobStatus: pollJobStatusAPI,  // NEW: Job status polling
      populateManPages: populateManPagesAPI,
      populateAutoBotDocs: populateAutoBotDocsAPI,
      vectorizeFacts: vectorizeFactsAPI,
      formatKey
    } = useKnowledgeBase();

    // NEW: Use shared Pinia store instead of local state
    const knowledgeStore = useKnowledgeStore();

    // Use computed properties from store instead of local refs
    const stats = computed(() => knowledgeStore.stats);
    const commandsIndexed = ref(0);
    const docsIndexed = ref(0);
    const selectedHost = ref('all');
    const machines = ref([]);  // Will be loaded from appConfig
    const progressMessage = ref('');
    const progressPercent = ref(0);
    const lastResult = ref(null);
    const activityLog = ref([]);

    // Use composables for async operations
    const { execute: fetchStatsOp, loading: isLoading } = useAsyncOperation();
    const { execute: initializeMachineKnowledgeOp, loading: isInitializing } = useAsyncOperation();
    const { execute: reindexDocumentsOp, loading: isReindexing } = useAsyncOperation();
    const { execute: refreshSystemKnowledgeOp, loading: isRefreshing } = useAsyncOperation();
    const { execute: populateManPagesOp, loading: isPopulating } = useAsyncOperation();
    const { execute: populateAutoBotDocsOp, loading: isDocPopulating } = useAsyncOperation();
    const { execute: generateVectorEmbeddingsOp, loading: isVectorizing } = useAsyncOperation();

    const addLogEntry = (message, status) => {
      const time = new Date().toLocaleTimeString();
      activityLog.value.unshift({ time, message, status });
      if (activityLog.value.length > 10) {
        activityLog.value.pop();
      }
    };

    // NEW: Use shared store's refreshStats action (consolidates API calls)
    const fetchStats = async () => {
      await fetchStatsOp(async () => {
        // Call store's refreshStats - this makes the API call and updates shared state
        await knowledgeStore.refreshStats();

        // Extract command and doc counts from categories if available
        const statsValue = knowledgeStore.stats;
        if (statsValue.categories && Array.isArray(statsValue.categories)) {
          // categories is string[] according to store type
          commandsIndexed.value = statsValue.categories.includes('system_commands') ? 1 : 0;
          docsIndexed.value = statsValue.categories.includes('autobot_documentation') ? 1 : 0;
        }

        addLogEntry('Stats refreshed successfully', 'success');
      }).catch(error => {
        logger.error('Failed to fetch stats:', error);
        addLogEntry('Failed to fetch stats', 'error');
        lastResult.value = {
          status: 'error',
          message: 'Failed to fetch knowledge base statistics'
        };
      });
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
        logger.error('Initialization error:', error);

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
        logger.error('Reindexing error:', error);

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
      progressMessage.value = 'Starting background job...';
      progressPercent.value = 0;
      lastResult.value = null;

      let pollInterval = null;

      try {
        addLogEntry('Starting comprehensive system knowledge refresh (background job)', 'info');

        // Start background job (returns immediately with task_id)
        const jobResponse = await refreshSystemKnowledgeAPI();

        if (!jobResponse.task_id) {
          throw new Error('No task_id returned from server');
        }

        const taskId = jobResponse.task_id;
        progressMessage.value = 'Background job started. Polling for completion...';
        addLogEntry(`Background job started: ${taskId}`, 'info');

        // Poll job status every 2 seconds
        pollInterval = setInterval(async () => {
          try {
            const statusResponse = await pollJobStatusAPI(taskId);

            logger.debug('Poll status:', statusResponse.status);

            if (statusResponse.status === 'PENDING') {
              progressMessage.value = 'Task queued, waiting to start...';
              progressPercent.value = 5;

            } else if (statusResponse.status === 'PROGRESS') {
              // Update progress from backend
              const meta = statusResponse.meta || {};
              progressMessage.value = meta.status || 'Processing...';
              progressPercent.value = meta.current || 10;

            } else if (statusResponse.status === 'SUCCESS') {
              // Job completed successfully
              clearInterval(pollInterval);
              progressPercent.value = 100;
              progressMessage.value = 'Refresh complete!';

              const result = statusResponse.result || {};
              lastResult.value = {
                status: 'success',
                message: result.message || 'System knowledge refreshed successfully',
                details: {
                  'Commands Indexed': result.commands_indexed || 0,
                  'Total Facts': result.total_facts || 0
                }
              };

              commandsIndexed.value = result.commands_indexed || 0;
              addLogEntry(`Indexed ${result.commands_indexed || 0} commands`, 'success');

              // Refresh stats
              await fetchStats();

              // Clean up UI after 3 seconds
              setTimeout(() => {
                progressMessage.value = '';
                progressPercent.value = 0;
                isRefreshing.value = false;
              }, 3000);

            } else if (statusResponse.status === 'FAILURE') {
              // Job failed
              clearInterval(pollInterval);
              const errorMsg = statusResponse.error || 'Unknown error';

              lastResult.value = {
                status: 'error',
                message: `System knowledge refresh failed: ${errorMsg}`
              };
              addLogEntry(`System knowledge refresh failed: ${errorMsg}`, 'error');

              isRefreshing.value = false;
              progressMessage.value = '';
              progressPercent.value = 0;
            }

          } catch (pollError) {
            logger.error('Polling error:', pollError);
            // Don't stop polling on transient errors - backend may be busy
          }
        }, 2000); // Poll every 2 seconds

      } catch (error) {
        if (pollInterval) clearInterval(pollInterval);

        let errorMessage = 'Failed to start system knowledge refresh';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        logger.error('Refresh error:', error);

        lastResult.value = {
          status: 'error',
          message: errorMessage
        };
        addLogEntry(`System knowledge refresh failed: ${errorMessage}`, 'error');

        isRefreshing.value = false;
        progressMessage.value = '';
        progressPercent.value = 0;
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
        logger.error('Man pages error:', error);

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
        logger.error('Documentation indexing error:', error);

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

        logger.error('Vectorization error:', error);

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

    // Helper function for vectorization button text
    const getVectorizeButtonText = () => {
      const totalFacts = stats.value?.total_facts || 0;
      const totalVectors = stats.value?.total_vectors || 0;

      // Facts are chunked into multiple vectors (typically 5-6 vectors per fact)
      // If vectors > facts, system is working correctly (chunking enabled)
      if (totalVectors >= totalFacts) {
        return `Vectorize Facts (✓ ${totalVectors.toLocaleString()} vectors from ${totalFacts.toLocaleString()} facts)`;
      }

      // If vectors < facts, some facts need vectorization
      const pending = totalFacts - totalVectors;
      return `Vectorize Facts (${pending.toLocaleString()} pending)`;
    };

    onMounted(async () => {
      // Load infrastructure machines from appConfig
      try {
        machines.value = appConfig.getMachinesArray();
      } catch (error) {
        logger.warn('Failed to load machines from appConfig:', error);
        // No fallback - component will just show "All Hosts" option
      }

      fetchStats();
    });

    return {
      stats,
      commandsIndexed,
      docsIndexed,
      selectedHost,
      machines,
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
      getVectorizeButtonText,  // NEW: Helper for button text
      formatKey
    };
  }
};
</script>

<style scoped>
.system-knowledge-manager {
  padding: var(--spacing-5);
  width: 100%;
  flex: 1;
}

.header {
  margin-bottom: var(--spacing-8);
}

.header h2 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
}

.subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.host-selection {
  margin-bottom: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.host-selection label {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  white-space: nowrap;
}

.host-select {
  flex: 1;
  max-width: 400px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.host-select:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: var(--shadow-focus);
}

.status-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-8);
}

/* BasePanel handles card container - only content styles remain */
.status-card-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.status-icon {
  font-size: var(--text-4xl);
}

.status-content h3 {
  margin: 0 0 var(--spacing-1) 0;
  font-size: var(--text-2xl);
  color: var(--text-primary);
}

.status-content p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.actions {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-8);
  flex-wrap: wrap;
}

.btn-highlight {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--chart-purple) 100%);
  color: var(--text-on-primary);
  border: 2px solid rgba(255, 255, 255, 0.3);
  box-shadow: var(--shadow-primary);
  font-weight: var(--font-semibold);
}

.btn-highlight:hover:not(:disabled) {
  background: linear-gradient(135deg, var(--chart-purple) 0%, var(--color-primary) 100%);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.6);
  transform: translateY(-2px);
}

.progress-display {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  margin-bottom: var(--spacing-5);
}

.progress-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.progress-content p {
  color: var(--text-primary);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--bg-tertiary);
  border-top-color: var(--color-info);
  border-radius: var(--radius-full);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.progress-bar {
  height: 6px;
  background: var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-info);
  transition: width var(--duration-500);
}

.result-display {
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  margin-bottom: var(--spacing-8);
  display: flex;
  gap: var(--spacing-4);
}

.result-display.success {
  background: var(--color-success-bg);
  border-left: 4px solid var(--color-success);
}

.result-display.error {
  background: var(--color-error-bg);
  border-left: 4px solid var(--color-error);
}

.result-icon {
  font-size: var(--text-4xl);
}

.result-content h4 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
}

.result-content p {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
}

.result-details {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.result-details p {
  margin: var(--spacing-1) 0;
  font-size: var(--text-sm);
}

/* BasePanel handles info section container - only content styles remain */
.info-content p {
  margin: var(--spacing-2) 0;
  line-height: var(--leading-relaxed);
  color: var(--text-secondary);
}

.activity-log {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  box-shadow: var(--shadow-md);
}

.activity-log h3 {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-primary);
}

.log-entries {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.log-entry {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
}

.log-time {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  min-width: 80px;
}

.log-message {
  flex: 1;
  color: var(--text-primary);
}

.log-status {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: uppercase;
}

.log-status.success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.log-status.error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.log-status.info {
  background: var(--color-info-bg);
  color: var(--color-info);
}
</style>
