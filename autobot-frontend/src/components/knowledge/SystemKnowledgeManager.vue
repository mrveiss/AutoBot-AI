<template>
  <div class="system-knowledge-manager">
    <div class="header">
      <p class="subtitle">{{ $t('knowledge.systemKnowledge.subtitle') }}</p>
    </div>

    <!-- Host Selection for Man Pages -->
    <div class="host-selection">
      <label for="host-select">{{ $t('knowledge.systemKnowledge.targetHost') }}</label>
      <select id="host-select" v-model="selectedHost" class="host-select">
        <option value="all">{{ $t('knowledge.systemKnowledge.allHosts') }}</option>
        <option v-for="machine in machines" :key="machine.id" :value="machine.ip">
          {{ machine.name }} ({{ machine.ip }})
        </option>
      </select>
    </div>

    <!-- Status Cards -->
    <div class="status-cards">
      <BasePanel variant="elevated" size="sm">
        <div class="status-card-content">
          <div class="status-icon">📚</div>
          <div class="status-content">
            <h3>{{ stats.total_facts || 0 }}</h3>
            <p>{{ $t('knowledge.systemKnowledge.totalFacts') }}</p>
          </div>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="sm">
        <div class="status-card-content">
          <div class="status-icon">🔍</div>
          <div class="status-content">
            <h3>{{ stats.total_vectors || 0 }}</h3>
            <p>{{ $t('knowledge.systemKnowledge.searchableVectors') }}</p>
          </div>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="sm">
        <div class="status-card-content">
          <div class="status-icon">⚙️</div>
          <div class="status-content">
            <h3>{{ commandsIndexed || 0 }}</h3>
            <p>{{ $t('knowledge.systemKnowledge.commandsIndexed') }}</p>
          </div>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="sm">
        <div class="status-card-content">
          <div class="status-icon">📄</div>
          <div class="status-content">
            <h3>{{ docsIndexed || 0 }}</h3>
            <p>{{ $t('knowledge.systemKnowledge.docsIndexed') }}</p>
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
        :title="t('knowledge.systemKnowledge.vectorizeTooltip')"
        class="btn-highlight"
      >
        <span class="icon">🧬</span>
        {{ isVectorizing ? $t('knowledge.systemKnowledge.vectorizing') : getVectorizeButtonText() }}
      </BaseButton>

      <BaseButton
        variant="primary"
        @click="initializeMachineKnowledge"
        :loading="isInitializing"
        :title="t('knowledge.systemKnowledge.initializeTooltip')"
      >
        <span class="icon">🚀</span>
        {{ isInitializing ? $t('knowledge.systemKnowledge.initializing') : $t('knowledge.systemKnowledge.initializeMachineKnowledge') }}
      </BaseButton>

      <BaseButton
        variant="primary"
        @click="reindexDocuments"
        :loading="isReindexing"
        :title="t('knowledge.systemKnowledge.reindexTooltip')"
      >
        <span class="icon">🔄</span>
        {{ isReindexing ? $t('knowledge.systemKnowledge.reindexing') : $t('knowledge.systemKnowledge.reindexDocuments') }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="refreshSystemKnowledge"
        :loading="isRefreshing"
      >
        <span class="icon">📋</span>
        {{ isRefreshing ? $t('knowledge.systemKnowledge.refreshing') : $t('knowledge.systemKnowledge.refreshManPages') }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="populateManPages"
        :loading="isPopulating"
      >
        <span class="icon">⚙️</span>
        {{ isPopulating ? $t('knowledge.systemKnowledge.populating') : $t('knowledge.systemKnowledge.populateCommands') }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="populateAutoBotDocs"
        :loading="isDocPopulating"
      >
        <span class="icon">📖</span>
        {{ isDocPopulating ? $t('knowledge.systemKnowledge.populating') : $t('knowledge.systemKnowledge.indexAutoBotDocs') }}
      </BaseButton>

      <BaseButton
        variant="outline-solid"
        @click="fetchStats"
        :disabled="isLoading"
      >
        <span class="icon">📊</span>
        {{ $t('knowledge.systemKnowledge.refreshStats') }}
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
        <h4>{{ lastResult.status === 'success' ? $t('knowledge.systemKnowledge.success') : $t('knowledge.systemKnowledge.error') }}</h4>
        <p>{{ lastResult.message }}</p>
        <div v-if="lastResult.details" class="result-details">
          <p v-for="(value, key) in lastResult.details" :key="key">
            <strong>{{ formatKey(key) }}:</strong> {{ typeof value === 'object' ? JSON.stringify(value) : value }}
          </p>
        </div>
      </div>
    </div>

    <!-- Info Section -->
    <BasePanel variant="bordered" size="md">
      <template #header>
        <h3>ℹ️ {{ $t('knowledge.systemKnowledge.aboutTitle') }}</h3>
      </template>
      <div class="info-content">
        <p v-html="t('knowledge.systemKnowledge.aboutInitialize')"></p>
        <p v-html="t('knowledge.systemKnowledge.aboutReindex')"></p>
        <p v-html="t('knowledge.systemKnowledge.aboutRefreshManPages')"></p>
        <p v-html="t('knowledge.systemKnowledge.aboutPopulateCommands')"></p>
        <p v-html="t('knowledge.systemKnowledge.aboutIndexDocs')"></p>
        <p v-html="t('knowledge.systemKnowledge.aboutWhenToUse')"></p>
      </div>
    </BasePanel>

    <!-- Recent Activity Log -->
    <div v-if="activityLog.length > 0" class="activity-log">
      <h3>📝 {{ $t('knowledge.systemKnowledge.recentActivity') }}</h3>
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
import { ref, onMounted, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useMachineKnowledge } from '@/composables/knowledge/useMachineKnowledge';
import { useManPages } from '@/composables/knowledge/useManPages';
import { useKnowledgeJobs } from '@/composables/knowledge/useKnowledgeJobs';
import { useKnowledgeStore } from '@/stores/useKnowledgeStore';  // NEW: Use shared store
import { useLoadingState } from '@/composables/useLoadingState'
import { usePollingJob } from '@/composables/usePollingJob';
import { formatCategoryName as formatKey } from '@/utils/formatHelpers';
import { useHostSelection } from '@/composables/useHostSelection';
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
    const { t } = useI18n();

    // Domain composables (migrated from useKnowledgeBase BC shim in #5193).
    // `formatKey` is now imported from @/utils/formatHelpers as an alias for
    // `formatCategoryName` (snake_case/kebab-case → Title Case). It was
    // previously destructured from the shim but never defined there —
    // runtime `undefined` would have thrown in the template at line ~152.
    const {
      initializeMachineKnowledge: initializeMachineKnowledgeAPI,
      refreshSystemKnowledge: refreshSystemKnowledgeAPI,
    } = useMachineKnowledge();
    const {
      populateManPages: populateManPagesAPI,
      populateAutoBotDocs: populateAutoBotDocsAPI,
    } = useManPages();
    const {
      pollJobStatus: pollJobStatusAPI,  // NEW: Job status polling
      vectorizeFacts: vectorizeFactsAPI,
    } = useKnowledgeJobs();

    // NEW: Use shared Pinia store instead of local state
    const knowledgeStore = useKnowledgeStore();

    // Host dropdown source: REAL node registry (/api/infrastructure/hosts)
    // via useHostSelection — NOT the legacy hardcoded VM0-5 AppConfig template
    // (#10505). In co-located deploys this returns no hosts, so the dropdown
    // falls back to the single "All Hosts" option below.
    const { hosts: infraHosts, loadHosts: loadInfraHosts } = useHostSelection();

    // Use computed properties from store instead of local refs
    const stats = computed(() => knowledgeStore.stats);
    const commandsIndexed = ref(0);
    const docsIndexed = ref(0);
    const selectedHost = ref('all');
    // Map real infrastructure hosts to the dropdown shape ({ id, name, ip }),
    // deduped by IP so a co-located fleet collapses to a single entry (#10505).
    const machines = computed(() => {
      const seenIps = new Set();
      const out = [];
      for (const h of infraHosts.value) {
        const ip = h.host;
        if (!ip || seenIps.has(ip)) continue;
        seenIps.add(ip);
        out.push({ id: h.id, name: h.name, ip });
      }
      return out;
    });
    const progressMessage = ref('');
    const progressPercent = ref(0);
    const lastResult = ref(null);
    const activityLog = ref([]);

    // Use composables for async operations
    const { isLoading, wrap: fetchStatsOp } = useLoadingState()
    const { isLoading: isInitializing, wrap: initializeMachineKnowledgeOp } = useLoadingState()
    const { isLoading: isReindexing, wrap: reindexDocumentsOp } = useLoadingState()
    const { isLoading: isRefreshing, wrap: refreshSystemKnowledgeOp } = useLoadingState()
    const { isLoading: isPopulating, wrap: populateManPagesOp } = useLoadingState()
    const { isLoading: isDocPopulating, wrap: populateAutoBotDocsOp } = useLoadingState()
    const { isLoading: isVectorizing, wrap: generateVectorEmbeddingsOp } = useLoadingState()

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

      if (!confirm(t('knowledge.systemKnowledge.confirmInitialize'))) {
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

      if (!confirm(t('knowledge.systemKnowledge.confirmReindex'))) {
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

    // Issue #5191: Managed job-status polling via usePollingJob
    const refreshJob = usePollingJob(
      (taskId) => pollJobStatusAPI(taskId),
      {
        intervalMs: 2000,
        maxAttempts: 600, // up to 20 minutes at 2s intervals
        isComplete: (r) => r?.status === 'SUCCESS' || r?.status === 'FAILURE',
        onDone: async (statusResponse) => {
          if (statusResponse.status === 'SUCCESS') {
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

            await fetchStats();

            setTimeout(() => {
              progressMessage.value = '';
              progressPercent.value = 0;
              isRefreshing.value = false;
            }, 3000);
          } else {
            // FAILURE
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
        }
      }
    );

    // Mirror in-flight PENDING/PROGRESS updates into UI state
    watch(refreshJob.data, (statusResponse) => {
      if (!statusResponse) return;
      logger.debug('Poll status:', statusResponse.status);
      if (statusResponse.status === 'PENDING') {
        progressMessage.value = 'Task queued, waiting to start...';
        progressPercent.value = 5;
      } else if (statusResponse.status === 'PROGRESS') {
        const meta = statusResponse.meta || {};
        progressMessage.value = meta.status || 'Processing...';
        progressPercent.value = meta.current || 10;
      }
    });

    const refreshSystemKnowledge = async () => {
      if (isRefreshing.value) return;

      if (!confirm(t('knowledge.systemKnowledge.confirmRefreshManPages'))) {
        return;
      }

      isRefreshing.value = true;
      progressMessage.value = 'Starting background job...';
      progressPercent.value = 0;
      lastResult.value = null;

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

        refreshJob.start(taskId);

      } catch (error) {
        refreshJob.stop();

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
      const forceReindex = confirm(t('knowledge.systemKnowledge.confirmIndexDocs'));

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

      if (!confirm(t('knowledge.systemKnowledge.confirmVectorize', { totalFacts, totalVectors, needsVectorization }))) {
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
        return t('knowledge.systemKnowledge.vectorizeComplete', { vectors: totalVectors.toLocaleString(), facts: totalFacts.toLocaleString() });
      }

      // If vectors < facts, some facts need vectorization
      const pending = totalFacts - totalVectors;
      return t('knowledge.systemKnowledge.vectorizePending', { pending: pending.toLocaleString() });
    };

    onMounted(async () => {
      // Load real infrastructure hosts from the node registry. When empty
      // (co-located deploy with no infrastructure_host secrets) the dropdown
      // shows only the "All Hosts" option — no legacy VM0-5 template (#10505).
      try {
        await loadInfraHosts();
      } catch (error) {
        logger.warn('Failed to load infrastructure hosts:', error);
        // No fallback - component will just show "All Hosts" option
      }

      fetchStats();
    });

    return {
      t,
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
  margin: var(--spacing-0);
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
.host-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
  margin: var(--spacing-0);
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
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: 2px solid rgba(255, 255, 255, 0.3);
  box-shadow: var(--shadow-primary);
  font-weight: var(--font-semibold);
}

.btn-highlight:hover:not(:disabled) {
  background: var(--chart-purple);
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
