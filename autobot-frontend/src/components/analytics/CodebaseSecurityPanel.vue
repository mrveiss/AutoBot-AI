<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Code Intelligence Analysis section -->
<template>
  <div class="code-intelligence-section analytics-section">
    <h3>
      <i class="fas fa-brain"></i> {{ $t('analytics.codebase.intelligence.title') }}
      <span v-if="props.totalFindings > 0" class="total-count">
        ({{ props.totalFindings.toLocaleString() }} findings)
      </span>
      <div class="section-actions">
        <button
          @click="showFileScanModal = true"
          class="action-btn"
          :title="$t('analytics.codebase.intelligence.scanFileTitle')"
        >
          <i class="fas fa-file-code"></i> {{ $t('analytics.codebase.intelligence.scanFile') }}
        </button>
        <button
          @click="emit('run-analysis')"
          :disabled="props.analysisLoading"
          class="action-btn primary"
          :title="$t('analytics.codebase.intelligence.runAnalysisTitle')"
        >
          <i :class="props.analysisLoading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          {{
            props.analysisLoading
              ? $t('analytics.codebase.buttons.analyzing')
              : $t('analytics.codebase.intelligence.analyze')
          }}
        </button>
      </div>
    </h3>

    <!-- Code Intelligence Tabs -->
    <div v-if="hasFindings" class="code-intel-tabs">
      <div class="tabs-header">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="['tab-btn', { active: activeTab === tab.id }]"
        >
          <i :class="tab.icon"></i>
          {{ $t(tab.labelKey) }}
          <span v-if="getTabCount(tab.id) > 0" class="tab-count">
            {{ getTabCount(tab.id) }}
          </span>
        </button>
      </div>

      <div class="tabs-content">
        <SecurityFindingsPanel
          v-if="activeTab === 'security'"
          :findings="props.securityFindings"
          :loading="props.findingsLoading"
        />
        <PerformanceFindingsPanel
          v-if="activeTab === 'performance'"
          :findings="props.performanceFindings"
          :loading="props.findingsLoading"
        />
        <RedisFindingsPanel
          v-if="activeTab === 'redis'"
          :findings="props.redisFindings"
          :loading="props.findingsLoading"
        />
      </div>
    </div>

    <EmptyState
      v-else-if="!props.analysisLoading"
      icon="fas fa-brain"
      :message="$t('analytics.codebase.intelligence.noData')"
      variant="info"
    >
      <template #actions>
        <button @click="emit('run-analysis')" class="btn-link">
          {{ $t('analytics.codebase.intelligence.runAnalysis') }}
        </button>
      </template>
    </EmptyState>

    <!-- File Scan Modal -->
    <FileScanModal
      :show="showFileScanModal"
      @close="showFileScanModal = false"
      @scan="(path, types) => emit('scan-file', path, types)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
} from '@/types/codeIntelligence'
import EmptyState from '@/components/ui/EmptyState.vue'
import SecurityFindingsPanel from '@/components/analytics/code-intelligence/SecurityFindingsPanel.vue'
import PerformanceFindingsPanel from '@/components/analytics/code-intelligence/PerformanceFindingsPanel.vue'
import RedisFindingsPanel from '@/components/analytics/code-intelligence/RedisFindingsPanel.vue'
import FileScanModal from '@/components/analytics/code-intelligence/FileScanModal.vue'

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { t } = useI18n()

interface Props {
  securityFindings: SecurityFinding[]
  performanceFindings: PerformanceFinding[]
  redisFindings: RedisOptimizationFinding[]
  findingsLoading: boolean
  analysisLoading: boolean
  totalFindings: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'run-analysis': []
  'scan-file': [filePath: string, scanTypes: { security: boolean; performance: boolean; redis: boolean }]
}>()

// UI-only state — kept local to this component
const activeTab = ref<'security' | 'performance' | 'redis'>('security')
const showFileScanModal = ref(false)

const tabs = [
  {
    id: 'security' as const,
    labelKey: 'analytics.codebase.intelligence.security',
    icon: 'fas fa-shield-alt',
  },
  {
    id: 'performance' as const,
    labelKey: 'analytics.codebase.intelligence.performanceLabel',
    icon: 'fas fa-tachometer-alt',
  },
  {
    id: 'redis' as const,
    labelKey: 'analytics.codebase.intelligence.redisLabel',
    icon: 'fas fa-database',
  },
]

const hasFindings = computed(() => props.totalFindings > 0)

const getTabCount = (tabId: string): number => {
  switch (tabId) {
    case 'security':
      return props.securityFindings.length
    case 'performance':
      return props.performanceFindings.length
    case 'redis':
      return props.redisFindings.length
    default:
      return 0
  }
}
</script>

<style scoped>
.code-intelligence-section h3 {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.code-intelligence-section .section-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.code-intelligence-section .action-btn {
  padding: 6px 12px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85em;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}

.code-intelligence-section .action-btn:hover:not(:disabled) {
  background: var(--bg-card);
  border-color: var(--color-info-dark);
}

.code-intelligence-section .action-btn.primary {
  background: var(--color-info-dark);
  border-color: var(--color-info-dark);
  color: white;
}

.code-intelligence-section .action-btn.primary:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.code-intelligence-section .action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Code Intelligence Tabs */
.code-intel-tabs {
  margin-top: 16px;
}

.code-intel-tabs .tabs-header {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-primary);
  margin-bottom: 16px;
}

.code-intel-tabs .tab-btn {
  padding: 8px 16px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9em;
  transition: all 0.15s ease;
}

.code-intel-tabs .tab-btn:hover {
  color: var(--text-primary);
}

.code-intel-tabs .tab-btn.active {
  color: var(--color-info-dark);
  border-bottom-color: var(--color-info-dark);
}

.code-intel-tabs .tab-count {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 0.8em;
}

.code-intel-tabs .tab-btn.active .tab-count {
  background: rgba(99, 102, 241, 0.2);
  color: var(--color-info-dark);
}

.code-intel-tabs .tabs-content {
  min-height: 200px;
}
</style>
