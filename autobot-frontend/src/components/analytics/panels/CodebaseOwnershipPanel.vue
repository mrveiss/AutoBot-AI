<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Code Ownership section (#248) -->
<template>
  <div class="ownership-section analytics-section">
    <h3>
      <i class="fas fa-users-cog"></i> {{ $t('analytics.codebase.ownership.title') }}
      <span v-if="analysis" class="total-count">
        ({{ analysis.summary.total_contributors }} contributors)
      </span>
      <button
        @click="emit('refresh')"
        :disabled="loading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
      </button>
      <div class="section-export-buttons" v-if="analysis">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
        >
          <i class="fas fa-file-alt"></i> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportJson')"
        >
          <i class="fas fa-file-code"></i> JSON
        </button>
      </div>
    </h3>

    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      {{ $t('analytics.codebase.ownership.analyzing') }}
    </div>

    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i> {{ error }}
      <button @click="emit('refresh')" class="btn-link">
        {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <div v-else-if="analysis && analysis.status === 'success'" class="section-content">
      <!-- View Mode Tabs -->
      <div class="ownership-tabs">
        <button
          :class="['tab-btn', { active: viewMode === 'overview' }]"
          @click="viewMode = 'overview'"
        >
          <i class="fas fa-chart-pie"></i> {{ $t('analytics.codebase.ownership.overview') }}
        </button>
        <button
          :class="['tab-btn', { active: viewMode === 'contributors' }]"
          @click="viewMode = 'contributors'"
        >
          <i class="fas fa-users"></i> {{ $t('analytics.codebase.ownership.contributors') }}
        </button>
        <button
          :class="['tab-btn', { active: viewMode === 'files' }]"
          @click="viewMode = 'files'"
        >
          <i class="fas fa-folder-tree"></i> {{ $t('analytics.codebase.ownership.filesTab') }}
        </button>
        <button
          :class="['tab-btn', { active: viewMode === 'gaps' }]"
          @click="viewMode = 'gaps'"
        >
          <i class="fas fa-exclamation-triangle"></i>
          {{ $t('analytics.codebase.ownership.knowledgeGaps') }}
          <span v-if="analysis.summary.critical_gaps > 0" class="gap-badge critical">
            {{ analysis.summary.critical_gaps }}
          </span>
        </button>
      </div>

      <!-- Overview Tab -->
      <div v-if="viewMode === 'overview'" class="ownership-overview">
        <div class="summary-cards">
          <div class="summary-card total">
            <div class="summary-value">{{ analysis.summary.total_files }}</div>
            <div class="summary-label">{{ $t('analytics.codebase.ownership.filesAnalyzed') }}</div>
          </div>
          <div class="summary-card info">
            <div class="summary-value">{{ analysis.summary.total_contributors }}</div>
            <div class="summary-label">{{ $t('analytics.codebase.ownership.contributors') }}</div>
          </div>
          <div
            class="summary-card"
            :class="analysis.metrics.overall_bus_factor <= 1 ? 'critical' : 'warning'"
          >
            <div class="summary-value">{{ analysis.metrics.overall_bus_factor }}</div>
            <div class="summary-label">{{ $t('analytics.codebase.ownership.busFactor') }}</div>
          </div>
          <div
            class="summary-card"
            :class="analysis.summary.critical_gaps > 0 ? 'critical' : 'success'"
          >
            <div class="summary-value">{{ analysis.summary.knowledge_gaps_count }}</div>
            <div class="summary-label">{{ $t('analytics.codebase.ownership.knowledgeGaps') }}</div>
          </div>
        </div>

        <div class="ownership-metrics">
          <div class="metric-item">
            <span class="metric-label">
              {{ $t('analytics.codebase.ownership.ownershipConcentration') }}:
            </span>
            <span
              class="metric-value"
              :class="analysis.metrics.ownership_concentration > 70 ? 'high-concentration' : ''"
            >
              {{ analysis.metrics.ownership_concentration }}%
            </span>
            <div class="metric-bar">
              <div
                class="metric-bar-fill"
                :style="{ width: analysis.metrics.ownership_concentration + '%' }"
                :class="
                  analysis.metrics.ownership_concentration > 70
                    ? 'critical'
                    : analysis.metrics.ownership_concentration > 50
                    ? 'warning'
                    : 'ok'
                "
              ></div>
            </div>
          </div>
          <div class="metric-item">
            <span class="metric-label">{{ $t('analytics.codebase.ownership.teamCoverage') }}:</span>
            <span class="metric-value">{{ analysis.metrics.team_coverage }}%</span>
            <div class="metric-bar">
              <div
                class="metric-bar-fill"
                :style="{ width: analysis.metrics.team_coverage + '%' }"
                :class="
                  analysis.metrics.team_coverage < 30
                    ? 'critical'
                    : analysis.metrics.team_coverage < 60
                    ? 'warning'
                    : 'ok'
                "
              ></div>
            </div>
          </div>
        </div>

        <div
          v-if="analysis.metrics.top_contributors.length > 0"
          class="top-contributors-preview"
        >
          <h4><i class="fas fa-trophy"></i> {{ $t('analytics.codebase.ownership.topContributors') }}</h4>
          <div class="contributor-list">
            <div
              v-for="(contrib, index) in analysis.metrics.top_contributors.slice(0, 5)"
              :key="'top-' + index"
              class="contributor-item"
            >
              <span class="rank">#{{ index + 1 }}</span>
              <span class="name">{{ contrib.name }}</span>
              <span class="lines">{{ contrib.lines.toLocaleString() }} lines</span>
              <span class="score">{{ contrib.score.toFixed(0) }} pts</span>
            </div>
          </div>
        </div>

        <div
          v-if="Object.keys(analysis.metrics.knowledge_risk_distribution).length > 0"
          class="risk-distribution"
        >
          <h4>
            <i class="fas fa-chart-bar"></i>
            {{ $t('analytics.codebase.ownership.knowledgeRiskDistribution') }}
          </h4>
          <div class="risk-badges">
            <span
              v-for="(count, risk) in analysis.metrics.knowledge_risk_distribution"
              :key="risk"
              class="risk-badge"
              :class="'risk-' + risk"
            >
              {{ formatFactorName(String(risk)) }}: {{ count }} files
            </span>
          </div>
        </div>
      </div>

      <!-- Contributors Tab -->
      <div v-if="viewMode === 'contributors'" class="ownership-contributors">
        <div
          v-for="(expert, index) in analysis.expertise_scores"
          :key="'expert-' + index"
          class="expert-card"
        >
          <div class="expert-header">
            <span class="expert-rank">#{{ index + 1 }}</span>
            <span class="expert-name">{{ expert.author_name }}</span>
            <span class="expert-score">{{ expert.overall_score.toFixed(0) }}</span>
          </div>
          <div class="expert-stats">
            <div class="stat">
              <i class="fas fa-code"></i>
              <span>{{ expert.total_lines.toLocaleString() }} lines</span>
            </div>
            <div class="stat">
              <i class="fas fa-code-commit"></i>
              <span>{{ expert.total_commits }} commits</span>
            </div>
            <div class="stat">
              <i class="fas fa-crown"></i>
              <span>{{ expert.files_owned }} files owned</span>
            </div>
          </div>
          <div class="expert-scores">
            <div class="score-bar">
              <span class="score-label">Impact</span>
              <div class="score-track">
                <div class="score-fill impact" :style="{ width: expert.impact_score + '%' }"></div>
              </div>
              <span class="score-value">{{ expert.impact_score.toFixed(0) }}</span>
            </div>
            <div class="score-bar">
              <span class="score-label">Recency</span>
              <div class="score-track">
                <div class="score-fill recency" :style="{ width: expert.recency_score + '%' }"></div>
              </div>
              <span class="score-value">{{ expert.recency_score.toFixed(0) }}</span>
            </div>
          </div>
          <div v-if="expert.expertise_areas.length > 0" class="expertise-areas">
            <span class="area-tag" v-for="area in expert.expertise_areas.slice(0, 3)" :key="area">
              {{ area }}
            </span>
          </div>
        </div>
      </div>

      <!-- Files Tab -->
      <div v-if="viewMode === 'files'" class="ownership-files">
        <div v-if="analysis.directory_ownership.length > 0" class="directories-section">
          <h4>
            <i class="fas fa-folder"></i>
            {{ $t('analytics.codebase.ownership.directoryOwnership') }}
          </h4>
          <div class="directory-list">
            <div
              v-for="(dir, index) in analysis.directory_ownership.slice(0, 15)"
              :key="'dir-' + index"
              class="directory-item"
              :class="'risk-' + dir.knowledge_risk"
            >
              <div class="dir-path">{{ dir.directory_path }}</div>
              <div class="dir-meta">
                <span class="dir-owner">{{ dir.primary_owner || 'Unknown' }}</span>
                <span class="dir-pct">{{ dir.ownership_percentage }}%</span>
                <span class="dir-bus-factor" :class="dir.bus_factor <= 1 ? 'low' : ''">
                  <i class="fas fa-users"></i> {{ dir.bus_factor }}
                </span>
                <span class="dir-lines">{{ dir.total_lines.toLocaleString() }} lines</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="analysis.file_ownership.length > 0" class="files-section">
          <h4>
            <i class="fas fa-file-code"></i>
            {{ $t('analytics.codebase.ownership.fileOwnership') }}
          </h4>
          <div class="file-list">
            <div
              v-for="(file, index) in analysis.file_ownership.slice(0, 30)"
              :key="'file-' + index"
              class="file-item"
              :class="'risk-' + file.knowledge_risk"
            >
              <div class="file-path">{{ file.file_path }}</div>
              <div class="file-meta">
                <span class="file-owner">{{ file.primary_owner || 'Unknown' }}</span>
                <span class="file-pct">{{ file.ownership_percentage }}%</span>
                <span class="file-bus-factor" :class="file.bus_factor <= 1 ? 'low' : ''">
                  <i class="fas fa-users"></i> {{ file.bus_factor }}
                </span>
                <span class="file-lines">{{ file.total_lines }} lines</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Knowledge Gaps Tab -->
      <div v-if="viewMode === 'gaps'" class="ownership-gaps">
        <div v-if="analysis.knowledge_gaps.length === 0" class="success-state">
          <i class="fas fa-check-circle"></i>
          {{ $t('analytics.codebase.ownership.noKnowledgeGaps') }}
        </div>
        <div v-else class="gaps-list">
          <div
            v-for="(gap, index) in analysis.knowledge_gaps"
            :key="'gap-' + index"
            class="gap-item"
            :class="'risk-' + gap.risk_level"
          >
            <div class="gap-header">
              <span class="gap-risk-badge" :class="gap.risk_level">
                {{ gap.risk_level.toUpperCase() }}
              </span>
              <span class="gap-type">{{ formatFactorName(gap.gap_type) }}</span>
              <span class="gap-lines">{{ gap.affected_lines.toLocaleString() }} lines</span>
            </div>
            <div class="gap-area"><i class="fas fa-folder"></i> {{ gap.area }}</div>
            <div class="gap-description">{{ gap.description }}</div>
            <div class="gap-recommendation">
              <i class="fas fa-lightbulb"></i> {{ gap.recommendation }}
            </div>
          </div>
        </div>
      </div>

      <div class="scan-timestamp">
        <i class="fas fa-clock"></i>
        Analysis completed in {{ analysis.analysis_time_seconds.toFixed(2) }}s
      </div>
    </div>

    <EmptyState
      v-else
      icon="fas fa-users-cog"
      :message="$t('analytics.codebase.ownership.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface OwnershipContributor {
  name: string
  email?: string
  lines: number
  percentage: number
}

interface FileOwnership {
  file_path: string
  total_lines: number
  primary_owner: string | null
  ownership_percentage: number
  bus_factor: number
  knowledge_risk: string
}

interface DirectoryOwnership {
  directory_path: string
  total_files: number
  total_lines: number
  primary_owner: string | null
  ownership_percentage: number
  bus_factor: number
  knowledge_risk: string
  contributors: OwnershipContributor[]
}

interface ExpertiseScore {
  author_name: string
  author_email: string
  total_lines: number
  total_commits: number
  files_owned: number
  directories_owned: number
  expertise_areas: string[]
  recency_score: number
  impact_score: number
  overall_score: number
}

interface KnowledgeGap {
  area: string
  gap_type: string
  risk_level: string
  description: string
  recommendation: string
  affected_lines: number
}

interface OwnershipMetrics {
  overall_bus_factor: number
  knowledge_risk_distribution: Record<string, number>
  top_contributors: Array<{ name: string; lines: number; score: number }>
  ownership_concentration: number
  team_coverage: number
}

interface OwnershipSummary {
  total_files: number
  total_directories: number
  total_contributors: number
  knowledge_gaps_count: number
  critical_gaps: number
  high_risk_gaps: number
}

interface OwnershipAnalysisResult {
  status: string
  analysis_time_seconds: number
  summary: OwnershipSummary
  file_ownership: FileOwnership[]
  directory_ownership: DirectoryOwnership[]
  expertise_scores: ExpertiseScore[]
  knowledge_gaps: KnowledgeGap[]
  metrics: OwnershipMetrics
}

const props = defineProps<{
  analysis: OwnershipAnalysisResult | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: string]
}>()

const viewMode = ref<'overview' | 'files' | 'contributors' | 'gaps'>('overview')

function formatFactorName(factor: string): string {
  return factor.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
}
</script>

<style scoped>
.ownership-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.ownership-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.ownership-section h3 i {
  color: var(--chart-purple-light);
}

.ownership-section .loading-state,
.ownership-section .error-state,
.ownership-section .success-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.ownership-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.ownership-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.ownership-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

/* Ownership Tabs */
.ownership-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
  padding-bottom: 12px;
}

.ownership-tabs .tab-btn {
  padding: 8px 16px;
  background: rgba(71, 85, 105, 0.3);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9em;
  transition: all 0.2s ease;
}

.ownership-tabs .tab-btn:hover {
  background: rgba(71, 85, 105, 0.5);
  color: var(--text-secondary);
}

.ownership-tabs .tab-btn.active {
  background: rgba(167, 139, 250, 0.2);
  border-color: rgba(167, 139, 250, 0.5);
  color: var(--chart-purple-light);
}

.ownership-tabs .gap-badge {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 0.75em;
}

.ownership-tabs .gap-badge.critical {
  background: rgba(239, 68, 68, 0.5);
}

/* Ownership Overview */
.ownership-overview .ownership-metrics {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ownership-metrics .metric-item {
  display: grid;
  grid-template-columns: 180px 80px 1fr;
  align-items: center;
  gap: 12px;
}

.ownership-metrics .metric-label {
  color: var(--text-muted);
  font-size: 0.9em;
}

.ownership-metrics .metric-value {
  color: var(--text-secondary);
  font-weight: 600;
}

.ownership-metrics .metric-value.high-concentration {
  color: var(--color-warning-light);
}

.ownership-metrics .metric-bar {
  height: 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  overflow: hidden;
}

.ownership-metrics .metric-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.ownership-metrics .metric-bar-fill.ok {
  background: var(--color-success);
}

.ownership-metrics .metric-bar-fill.warning {
  background: var(--color-warning);
}

.ownership-metrics .metric-bar-fill.critical {
  background: var(--color-error);
}

/* Top Contributors Preview */
.top-contributors-preview {
  margin-top: 24px;
}

.top-contributors-preview h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.top-contributors-preview h4 i {
  color: var(--color-warning-light);
}

.contributor-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.contributor-item {
  display: grid;
  grid-template-columns: 40px 1fr 120px 80px;
  align-items: center;
  padding: 10px 14px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.contributor-item .rank {
  color: var(--chart-purple-light);
  font-weight: 600;
}

.contributor-item .name {
  color: var(--text-secondary);
  font-weight: 500;
}

.contributor-item .lines {
  color: var(--text-muted);
  font-size: 0.85em;
  text-align: right;
}

.contributor-item .score {
  color: var(--color-success-light);
  font-weight: 600;
  text-align: right;
}

/* Risk Distribution */
.risk-distribution {
  margin-top: 24px;
}

.risk-distribution h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.risk-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.risk-badge {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.85em;
  font-weight: 500;
}

.risk-badge.risk-low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.risk-badge.risk-medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
  border: 1px solid rgba(245, 158, 11, 0.4);
}

.risk-badge.risk-high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.risk-badge.risk-critical {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
  border: 1px solid rgba(239, 68, 68, 0.6);
}

/* Contributors Tab */
.ownership-contributors {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.expert-card {
  padding: 16px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 10px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.expert-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.expert-rank {
  color: var(--chart-purple-light);
  font-weight: 700;
  font-size: 1.1em;
}

.expert-name {
  color: var(--text-secondary);
  font-weight: 600;
  flex: 1;
}

.expert-score {
  background: var(--chart-purple);
  color: var(--text-on-primary);
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 700;
  font-size: 0.9em;
}

.expert-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.expert-stats .stat {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 0.85em;
}

.expert-stats .stat i {
  color: var(--text-tertiary);
}

.expert-scores {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.score-bar {
  display: grid;
  grid-template-columns: 60px 1fr 40px;
  align-items: center;
  gap: 8px;
}

.score-label {
  color: var(--text-muted);
  font-size: 0.8em;
}

.score-track {
  height: 6px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 3px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 3px;
}

.score-fill.impact {
  background: var(--color-primary);
}

.score-fill.recency {
  background: var(--color-success);
}

.score-value {
  color: var(--text-secondary);
  font-size: 0.8em;
  text-align: right;
}

.expertise-areas {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.area-tag {
  padding: 3px 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  font-size: 0.75em;
  color: var(--text-muted);
}

/* Files Tab */
.ownership-files .directories-section,
.ownership-files .files-section {
  margin-bottom: 24px;
}

.ownership-files h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ownership-files h4 i {
  color: var(--color-info);
}

.directory-list,
.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.directory-item,
.file-item {
  padding: 12px 14px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  border-left: 3px solid var(--color-success-light);
}

.directory-item.risk-medium,
.file-item.risk-medium {
  border-left-color: var(--color-warning-light);
}

.directory-item.risk-high,
.file-item.risk-high {
  border-left-color: var(--color-error-light);
}

.directory-item.risk-critical,
.file-item.risk-critical {
  border-left-color: var(--color-error);
}

.dir-path,
.file-path {
  color: var(--text-secondary);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.9em;
  margin-bottom: 6px;
}

.dir-meta,
.file-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 0.85em;
}

.dir-owner,
.file-owner {
  color: var(--chart-purple-light);
  font-weight: 500;
}

.dir-pct,
.file-pct {
  color: var(--text-muted);
}

.dir-bus-factor,
.file-bus-factor {
  color: var(--color-success-light);
}

.dir-bus-factor.low,
.file-bus-factor.low {
  color: var(--color-error-light);
}

.dir-lines,
.file-lines {
  color: var(--text-tertiary);
}

/* Knowledge Gaps Tab */
.ownership-gaps .gaps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gap-item {
  padding: 16px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 10px;
  border-left: 4px solid var(--color-error-light);
}

.gap-item.risk-medium {
  border-left-color: var(--color-warning-light);
}

.gap-item.risk-low {
  border-left-color: var(--color-success-light);
}

.gap-item.risk-critical {
  border-left-color: var(--color-error);
  background: rgba(239, 68, 68, 0.05);
}

.gap-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.gap-risk-badge {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 0.75em;
  font-weight: 700;
  text-transform: uppercase;
}

.gap-risk-badge.critical {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.gap-risk-badge.high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.gap-risk-badge.medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.gap-risk-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.gap-type {
  color: var(--text-muted);
  font-size: 0.9em;
}

.gap-lines {
  color: var(--text-tertiary);
  font-size: 0.85em;
  margin-left: auto;
}

.gap-area {
  color: var(--chart-purple-light);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.9em;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.gap-area i {
  color: var(--text-tertiary);
}

.gap-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  line-height: 1.4;
  margin-bottom: 10px;
}

.gap-recommendation {
  color: var(--color-success-light);
  font-size: 0.85em;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 6px;
}

.gap-recommendation i {
  color: var(--color-warning-light);
  margin-top: 2px;
}

/* Issue #566: Code Intelligence Section Styles */

</style>
