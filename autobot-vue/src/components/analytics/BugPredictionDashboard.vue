<template>
  <div class="bug-prediction-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2 class="dashboard-title">Bug Prediction System</h2>
        <p class="dashboard-subtitle">Predict and prevent bugs before they occur</p>
      </div>
      <div class="header-actions">
        <button class="btn-analyze" @click="analyzeCodbase" :disabled="loading">
          <span class="icon">&#128269;</span>
          {{ loading ? 'Analyzing...' : 'Analyze Codebase' }}
        </button>
        <button class="btn-refresh" @click="refreshData" :disabled="loading">
          <span class="icon">&#8635;</span>
          Refresh
        </button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="summary-cards">
      <div class="summary-card high-risk">
        <div class="card-icon">&#9888;&#65039;</div>
        <div class="card-content">
          <span class="card-value">{{ summary.high_risk_files }}</span>
          <span class="card-label">High Risk Files</span>
        </div>
        <div class="card-indicator critical">Needs Attention</div>
      </div>

      <div class="summary-card predictions">
        <div class="card-icon">&#128027;</div>
        <div class="card-content">
          <span class="card-value">{{ summary.predicted_bugs_next_sprint }}</span>
          <span class="card-label">Predicted Bugs</span>
        </div>
        <div class="card-indicator">Next Sprint</div>
      </div>

      <div class="summary-card accuracy">
        <div class="card-icon">&#127919;</div>
        <div class="card-content">
          <span class="card-value">{{ summary.model_accuracy.toFixed(1) }}%</span>
          <span class="card-label">Model Accuracy</span>
        </div>
        <div class="accuracy-bar">
          <div class="accuracy-fill" :style="{ width: summary.model_accuracy + '%' }"></div>
        </div>
      </div>

      <div class="summary-card analyzed">
        <div class="card-icon">&#128193;</div>
        <div class="card-content">
          <span class="card-value">{{ summary.total_files_analyzed }}</span>
          <span class="card-label">Files Analyzed</span>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid">
      <!-- Risk Heatmap -->
      <div class="panel heatmap-panel">
        <div class="panel-header">
          <h3>Risk Heatmap</h3>
          <div class="grouping-toggle">
            <button :class="{ active: heatmapGrouping === 'directory' }" @click="heatmapGrouping = 'directory'; loadHeatmap()">
              By Directory
            </button>
            <button :class="{ active: heatmapGrouping === 'flat' }" @click="heatmapGrouping = 'flat'; loadHeatmap()">
              All Files
            </button>
          </div>
        </div>
        <div class="panel-content">
          <div class="heatmap-grid">
            <div
              v-for="item in heatmapData"
              :key="item.name"
              class="heatmap-cell"
              :class="'risk-' + item.risk_level"
              :style="{
                '--size': Math.max(40, Math.min(100, item.value)) + 'px',
                '--opacity': 0.3 + (item.value / 100) * 0.7
              }"
              @click="selectHeatmapItem(item)"
              :title="`${item.name}: ${item.value.toFixed(1)} risk score`"
            >
              <span class="cell-name">{{ truncateName(item.name) }}</span>
              <span class="cell-score">{{ item.value.toFixed(0) }}</span>
            </div>
          </div>
          <div class="heatmap-legend">
            <div class="legend-item">
              <span class="legend-color critical"></span>
              <span>Critical (80+)</span>
            </div>
            <div class="legend-item">
              <span class="legend-color high"></span>
              <span>High (60-79)</span>
            </div>
            <div class="legend-item">
              <span class="legend-color medium"></span>
              <span>Medium (40-59)</span>
            </div>
            <div class="legend-item">
              <span class="legend-color low"></span>
              <span>Low (20-39)</span>
            </div>
            <div class="legend-item">
              <span class="legend-color minimal"></span>
              <span>Minimal (0-19)</span>
            </div>
          </div>
        </div>
      </div>

      <!-- High Risk Files -->
      <div class="panel high-risk-panel">
        <div class="panel-header">
          <h3>&#128293; High Risk Files</h3>
          <span class="panel-count">{{ highRiskFiles.length }} files</span>
        </div>
        <div class="panel-content">
          <div v-if="highRiskFiles.length === 0" class="empty-state">
            <span class="empty-icon">&#10024;</span>
            <span class="empty-text">No high risk files detected</span>
          </div>
          <div v-else class="high-risk-list">
            <div
              v-for="(file, index) in highRiskFiles"
              :key="file.file_path"
              class="risk-file-item"
              :class="'risk-' + file.risk_level"
              @click="showFileDetails(file)"
            >
              <div class="file-rank">{{ index + 1 }}</div>
              <div class="file-info">
                <span class="file-path">{{ truncatePath(file.file_path) }}</span>
                <span class="file-bugs" v-if="file.bug_count_history">
                  {{ file.bug_count_history }} historical bugs
                </span>
              </div>
              <div class="file-score">
                <div class="score-badge" :class="file.risk_level">
                  {{ file.risk_score.toFixed(0) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Risk Factors & Trends -->
    <div class="content-grid">
      <!-- Top Risk Factors -->
      <div class="panel factors-panel">
        <div class="panel-header">
          <h3>&#128202; Top Risk Factors</h3>
        </div>
        <div class="panel-content">
          <div class="factors-list">
            <div
              v-for="factor in summary.top_risk_factors"
              :key="factor.factor"
              class="factor-item"
            >
              <div class="factor-info">
                <span class="factor-icon">{{ getFactorIcon(factor.factor) }}</span>
                <span class="factor-name">{{ factor.factor }}</span>
              </div>
              <div class="factor-bar">
                <div
                  class="bar-fill"
                  :style="{ width: Math.min(100, factor.average) + '%' }"
                  :class="getFactorClass(factor.average)"
                ></div>
              </div>
              <span class="factor-score">{{ factor.average.toFixed(1) }}</span>
            </div>
          </div>
          <div class="factors-weights">
            <h4>Factor Weights</h4>
            <div class="weights-grid">
              <div v-for="(weight, factor) in riskFactors" :key="factor" class="weight-item">
                <span class="weight-name">{{ formatFactorName(factor) }}</span>
                <span class="weight-value">{{ (weight * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Prediction Accuracy Trends -->
      <div class="panel trends-panel">
        <div class="panel-header">
          <h3>&#128200; Prediction Accuracy</h3>
          <div class="period-selector">
            <button
              v-for="period in ['7d', '30d', '90d']"
              :key="period"
              :class="{ active: selectedPeriod === period }"
              @click="selectedPeriod = period; loadTrends()"
            >
              {{ period }}
            </button>
          </div>
        </div>
        <div class="panel-content">
          <div class="trends-chart">
            <svg viewBox="0 0 600 180" class="accuracy-chart" preserveAspectRatio="xMidYMid meet">
              <!-- Grid -->
              <g class="grid">
                <line v-for="i in 5" :key="'h' + i" x1="40" x2="580" :y1="i * 30 + 10" :y2="i * 30 + 10" class="grid-line" stroke-dasharray="2,2" />
              </g>

              <!-- Y-Axis -->
              <g class="y-axis">
                <text x="35" y="15" text-anchor="end" class="axis-text" font-size="9">100%</text>
                <text x="35" y="75" text-anchor="end" class="axis-text" font-size="9">75%</text>
                <text x="35" y="135" text-anchor="end" class="axis-text" font-size="9">50%</text>
              </g>

              <!-- Accuracy Line -->
              <path v-if="trendLinePath" :d="trendLinePath" fill="none" class="trend-line" stroke-width="2" stroke-linecap="round" />

              <!-- Data Points -->
              <g class="data-points">
                <circle
                  v-for="(point, i) in trendPoints"
                  :key="'p' + i"
                  :cx="point.x"
                  :cy="point.y"
                  r="4"
                  class="data-point-circle"
                  @mouseenter="hoveredPoint = point"
                  @mouseleave="hoveredPoint = null"
                />
              </g>

              <!-- Tooltip -->
              <g v-if="hoveredPoint" class="tooltip">
                <rect :x="hoveredPoint.x - 35" :y="hoveredPoint.y - 40" width="70" height="30" rx="4" class="tooltip-bg" />
                <text :x="hoveredPoint.x" :y="hoveredPoint.y - 25" text-anchor="middle" class="tooltip-text-primary" font-size="11">
                  {{ hoveredPoint.accuracy.toFixed(1) }}%
                </text>
                <text :x="hoveredPoint.x" :y="hoveredPoint.y - 12" text-anchor="middle" class="tooltip-text-secondary" font-size="9">
                  {{ hoveredPoint.date }}
                </text>
              </g>
            </svg>
          </div>
          <div class="trend-stats">
            <div class="trend-stat">
              <span class="stat-label">Average</span>
              <span class="stat-value">{{ trendStats.average.toFixed(1) }}%</span>
            </div>
            <div class="trend-stat">
              <span class="stat-label">Predicted</span>
              <span class="stat-value">{{ trendStats.total_predicted }}</span>
            </div>
            <div class="trend-stat">
              <span class="stat-label">Actual</span>
              <span class="stat-value">{{ trendStats.total_actual }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recommendations -->
    <div class="panel recommendations-panel">
      <div class="panel-header">
        <h3>&#128161; Recommendations</h3>
      </div>
      <div class="panel-content">
        <div class="recommendations-grid">
          <div
            v-for="(rec, i) in summary.recommendations"
            :key="i"
            class="recommendation-card"
          >
            <span class="rec-number">{{ i + 1 }}</span>
            <span class="rec-text">{{ rec }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- File Details Modal -->
    <div v-if="selectedFile" class="modal-overlay" @click.self="selectedFile = null">
      <div class="modal-content">
        <div class="modal-header">
          <h3>File Risk Details</h3>
          <button class="btn-close" @click="selectedFile = null">x</button>
        </div>
        <div class="modal-body">
          <div class="detail-section">
            <h4>File Information</h4>
            <div class="detail-row">
              <span class="detail-label">Path:</span>
              <span class="detail-value file-path">{{ selectedFile.file_path }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Risk Score:</span>
              <span class="detail-value">
                <span class="score-badge large" :class="selectedFile.risk_level">
                  {{ selectedFile.risk_score.toFixed(1) }}
                </span>
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Historical Bugs:</span>
              <span class="detail-value">{{ selectedFile.bug_count_history || 0 }}</span>
            </div>
            <div v-if="selectedFile.last_bug_date" class="detail-row">
              <span class="detail-label">Last Bug:</span>
              <span class="detail-value">{{ selectedFile.last_bug_date }}</span>
            </div>
          </div>

          <div class="detail-section">
            <h4>Risk Factors</h4>
            <div class="factors-breakdown">
              <div
                v-for="(value, factor) in selectedFile.factors"
                :key="factor"
                class="factor-row"
              >
                <span class="factor-name">{{ formatFactorName(factor) }}</span>
                <div class="factor-bar-container">
                  <div
                    class="factor-bar-fill"
                    :style="{ width: value + '%' }"
                    :class="getFactorClass(value)"
                  ></div>
                </div>
                <span class="factor-value">{{ value.toFixed(0) }}</span>
              </div>
            </div>
          </div>

          <div class="detail-section">
            <h4>Prevention Tips</h4>
            <ul class="tips-list">
              <li v-for="(tip, i) in selectedFile.prevention_tips" :key="i">{{ tip }}</li>
            </ul>
          </div>

          <div class="detail-section" v-if="selectedFile.suggested_tests?.length">
            <h4>Suggested Tests</h4>
            <ul class="tests-list">
              <li v-for="(test, i) in selectedFile.suggested_tests" :key="i">{{ test }}</li>
            </ul>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="selectedFile = null">Close</button>
          <button class="btn-primary" @click="recordBug(selectedFile)">Record Bug</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * BugPredictionDashboard.vue - Bug prediction analytics dashboard
 * Issue #704: Migrated to design tokens for centralized theming
 */
import { ref, computed, onMounted, watch } from 'vue';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for BugPredictionDashboard
const logger = createLogger('BugPredictionDashboard');

/**
 * Helper function to get CSS custom property value
 * Issue #704: Added for dynamic color access in JavaScript
 */
function getCssVar(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

// Types
interface RiskFile {
  file_path: string;
  risk_score: number;
  risk_level: string;
  factors: Record<string, number>;
  bug_count_history: number;
  last_bug_date?: string;
  prevention_tips: string[];
  suggested_tests: string[];
}

interface HeatmapItem {
  name: string;
  value: number;
  file_count?: number;
  risk_level: string;
  files?: RiskFile[];
}

interface TrendPoint {
  x: number;
  y: number;
  accuracy: number;
  date: string;
}

interface Summary {
  total_files_analyzed: number;
  high_risk_files: number;
  predicted_bugs_next_sprint: number;
  model_accuracy: number;
  top_risk_factors: Array<{ factor: string; total_score: number; average: number }>;
  recommendations: string[];
}

// State
const loading = ref(false);
const selectedPeriod = ref('30d');
const heatmapGrouping = ref<'directory' | 'flat'>('directory');
const selectedFile = ref<RiskFile | null>(null);
const hoveredPoint = ref<TrendPoint | null>(null);
const isPolling = ref(true);
const lastUpdateTime = ref<Date | null>(null);
const pollingInterval = ref<number | null>(null);

const summary = ref<Summary>({
  total_files_analyzed: 0,
  high_risk_files: 0,
  predicted_bugs_next_sprint: 0,
  model_accuracy: 0,
  top_risk_factors: [],
  recommendations: [],
});

const highRiskFiles = ref<RiskFile[]>([]);
const heatmapData = ref<HeatmapItem[]>([]);
const trendData = ref<Array<{ date: string; accuracy: number; predicted_bugs: number; actual_bugs: number }>>([]);
const riskFactors = ref<Record<string, number>>({});

// Computed
const trendPoints = computed((): TrendPoint[] => {
  if (trendData.value.length === 0) return [];

  const chartWidth = 540;
  const chartHeight = 120;
  const startX = 40;

  return trendData.value.map((point, i) => ({
    x: startX + (i / Math.max(trendData.value.length - 1, 1)) * chartWidth,
    y: 10 + chartHeight - (point.accuracy / 100) * chartHeight,
    accuracy: point.accuracy,
    date: formatShortDate(point.date),
  }));
});

const trendLinePath = computed(() => {
  if (trendPoints.value.length < 2) return '';
  const points = trendPoints.value;
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    path += ` L ${points[i].x} ${points[i].y}`;
  }
  return path;
});

const trendStats = computed(() => {
  if (trendData.value.length === 0) {
    return { average: 0, total_predicted: 0, total_actual: 0 };
  }
  const accuracies = trendData.value.map(t => t.accuracy);
  return {
    average: accuracies.reduce((a, b) => a + b, 0) / accuracies.length,
    total_predicted: trendData.value.reduce((a, t) => a + t.predicted_bugs, 0),
    total_actual: trendData.value.reduce((a, t) => a + t.actual_bugs, 0),
  };
});

// Methods
async function refreshData(): Promise<void> {
  loading.value = true;
  try {
    await Promise.all([
      loadSummary(),
      loadHighRiskFiles(),
      loadHeatmap(),
      loadTrends(),
      loadFactors(),
    ]);
  } catch (error) {
    logger.error('Failed to refresh data:', error);
  } finally {
    loading.value = false;
  }
}

async function analyzeCodbase(): Promise<void> {
  loading.value = true;
  try {
    const response = await fetch('/api/analytics/bug-prediction/analyze?limit=100');
    if (response.ok) {
      const data = await response.json();
      // Refresh all data after analysis
      await refreshData();
    }
  } catch (error) {
    logger.error('Failed to analyze codebase:', error);
  } finally {
    loading.value = false;
  }
}

async function loadSummary(): Promise<void> {
  try {
    const response = await fetch('/api/analytics/bug-prediction/summary');
    if (response.ok) {
      summary.value = await response.json();
    } else {
      logger.warn('Failed to load summary: HTTP', response.status);
    }
  } catch (error) {
    logger.error('Failed to load summary:', error);
    // Keep default empty summary state
  }
}

async function loadHighRiskFiles(): Promise<void> {
  try {
    const response = await fetch('/api/analytics/bug-prediction/high-risk?threshold=60&limit=10');
    if (response.ok) {
      highRiskFiles.value = await response.json();
    } else {
      logger.warn('Failed to load high risk files: HTTP', response.status);
      highRiskFiles.value = [];
    }
  } catch (error) {
    logger.error('Failed to load high risk files:', error);
    highRiskFiles.value = [];
  }
}

async function loadHeatmap(): Promise<void> {
  try {
    const response = await fetch(`/api/analytics/bug-prediction/heatmap?grouping=${heatmapGrouping.value}`);
    if (response.ok) {
      const data = await response.json();
      heatmapData.value = data.data || [];
    } else {
      logger.warn('Failed to load heatmap: HTTP', response.status);
      heatmapData.value = [];
    }
  } catch (error) {
    logger.error('Failed to load heatmap:', error);
    heatmapData.value = [];
  }
}

async function loadTrends(): Promise<void> {
  try {
    const response = await fetch(`/api/analytics/bug-prediction/trends?period=${selectedPeriod.value}`);
    if (response.ok) {
      const data = await response.json();
      trendData.value = data.data_points || [];
    } else {
      logger.warn('Failed to load trends: HTTP', response.status);
      trendData.value = [];
    }
  } catch (error) {
    logger.error('Failed to load trends:', error);
    trendData.value = [];
  }
}

async function loadFactors(): Promise<void> {
  try {
    const response = await fetch('/api/analytics/bug-prediction/factors');
    if (response.ok) {
      const data = await response.json();
      riskFactors.value = Object.fromEntries(
        data.factors.map((f: any) => [f.name, f.weight])
      );
    } else {
      logger.warn('Failed to load factors: HTTP', response.status);
      riskFactors.value = {};
    }
  } catch (error) {
    logger.error('Failed to load factors:', error);
    riskFactors.value = {};
  }
}

function showFileDetails(file: RiskFile): void {
  selectedFile.value = file;
}

function selectHeatmapItem(item: HeatmapItem): void {
  if (item.files && item.files.length > 0) {
    // Show first file from the group
    selectedFile.value = item.files[0] as RiskFile;
  }
}

async function recordBug(file: RiskFile): Promise<void> {
  try {
    await fetch('/api/analytics/bug-prediction/record-bug', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: file.file_path,
        severity: file.risk_level,
      }),
    });
    selectedFile.value = null;
    await refreshData();
  } catch (error) {
    logger.error('Failed to record bug:', error);
  }
}

// Utility Functions
function truncatePath(path: string): string {
  if (path.length <= 40) return path;
  const parts = path.split('/');
  if (parts.length <= 2) return path;
  return `.../${parts.slice(-2).join('/')}`;
}

function truncateName(name: string): string {
  if (name.length <= 12) return name;
  return name.substring(0, 10) + '...';
}

function formatFactorName(factor: string): string {
  return factor.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function getFactorIcon(factor: string): string {
  const icons: Record<string, string> = {
    'Bug History': '\u{1F41B}',
    'Complexity': '\u{1F504}',
    'Change Frequency': '\u{1F4DD}',
    'Test Coverage': '\u{1F9EA}',
    'File Size': '\u{1F4E6}',
  };
  return icons[factor] || '\u{1F4CA}';
}

function getFactorClass(value: number): string {
  if (value >= 70) return 'critical';
  if (value >= 50) return 'high';
  if (value >= 30) return 'medium';
  return 'low';
}

function timeAgo(date: Date): string {
  const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000)

  if (seconds < 60) return `${seconds}s ago`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

// Lifecycle
onMounted(() => {
  refreshData();
});

watch(selectedPeriod, () => {
  loadTrends();
});
</script>

<style scoped>
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * BugPredictionDashboard styles - Using design tokens from design-tokens.css
 * Issue #704: Migrated all hardcoded colors to CSS custom properties
 */

.bug-prediction-dashboard {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  min-height: 100vh;
  color: var(--text-primary);
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-6);
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
  gap: var(--spacing-3);
}

.btn-analyze,
.btn-refresh {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: var(--transition-all);
}

.btn-analyze {
  background: var(--color-success);
  border: none;
  color: var(--text-on-success);
}

.btn-analyze:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.btn-refresh {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-tertiary);
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.summary-card {
  background: linear-gradient(135deg, var(--bg-surface) 0%, var(--bg-secondary) 100%);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--spacing-4);
}

.card-icon {
  font-size: var(--text-3xl);
}

.card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.card-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.card-indicator {
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.card-indicator.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.accuracy-bar {
  width: 100%;
  height: 6px;
  background: var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-top: var(--spacing-2);
}

.accuracy-fill {
  height: 100%;
  background: var(--color-success);
  transition: width 0.5s ease;
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-6);
}

@media (max-width: 1200px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}

/* Panels */
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
  margin: 0;
  font-size: var(--text-base);
  color: var(--text-primary);
}

.panel-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.panel-content {
  padding: var(--spacing-5);
}

/* Heatmap */
.grouping-toggle {
  display: flex;
  gap: var(--spacing-1);
}

.grouping-toggle button {
  padding: var(--spacing-1-5) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: var(--transition-all);
}

.grouping-toggle button.active {
  background: var(--color-info);
  border-color: var(--color-info);
  color: var(--text-on-primary);
}

.heatmap-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
}

.heatmap-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: var(--transition-all);
  min-width: 80px;
}

.heatmap-cell.risk-critical {
  background: rgba(239, 68, 68, var(--opacity, 0.5));
  border: 1px solid var(--color-error-border);
}

.heatmap-cell.risk-high {
  background: rgba(249, 115, 22, var(--opacity, 0.5));
  border: 1px solid var(--chart-orange);
}

.heatmap-cell.risk-medium {
  background: rgba(234, 179, 8, var(--opacity, 0.5));
  border: 1px solid var(--chart-yellow);
}

.heatmap-cell.risk-low {
  background: rgba(34, 197, 94, var(--opacity, 0.5));
  border: 1px solid var(--color-success-border);
}

.heatmap-cell.risk-minimal {
  background: rgba(59, 130, 246, var(--opacity, 0.5));
  border: 1px solid var(--color-info);
}

.heatmap-cell:hover {
  transform: scale(1.05);
}

.cell-name {
  font-size: var(--text-xs);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.cell-score {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.heatmap-legend {
  display: flex;
  justify-content: center;
  gap: var(--spacing-6);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-xs);
}

.legend-color.critical { background: var(--color-error); }
.legend-color.high { background: var(--chart-orange); }
.legend-color.medium { background: var(--chart-yellow); }
.legend-color.low { background: var(--color-success); }
.legend-color.minimal { background: var(--color-info); }

/* High Risk Files */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
}

.empty-icon {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-2);
}

.high-risk-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.risk-file-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: var(--transition-all);
  border-left: 3px solid transparent;
}

.risk-file-item.risk-critical {
  border-left-color: var(--color-error);
}

.risk-file-item.risk-high {
  border-left-color: var(--chart-orange);
}

.risk-file-item:hover {
  background: var(--bg-tertiary);
}

.file-rank {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border-subtle);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.file-info {
  flex: 1;
}

.file-path {
  display: block;
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-info);
}

.file-bugs {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.score-badge {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
}

.score-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.score-badge.high {
  background: var(--chart-orange-bg);
  color: var(--chart-orange);
}

.score-badge.medium {
  background: var(--chart-yellow-bg);
  color: var(--chart-yellow);
}

.score-badge.low {
  background: var(--color-success-bg);
  color: var(--color-success);
}

/* Factors Panel */
.factors-list {
  margin-bottom: var(--spacing-6);
}

.factor-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) 0;
  border-bottom: 1px solid var(--bg-surface);
}

.factor-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  min-width: 140px;
}

.factor-icon {
  font-size: var(--text-base);
}

.factor-name {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.factor-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: var(--radius-default);
  transition: width 0.3s;
}

.bar-fill.critical { background: var(--color-error); }
.bar-fill.high { background: var(--chart-orange); }
.bar-fill.medium { background: var(--chart-yellow); }
.bar-fill.low { background: var(--color-success); }

.factor-score {
  min-width: 30px;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  text-align: right;
}

.factors-weights {
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.factors-weights h4 {
  margin: 0 0 var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.weights-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-2);
}

.weight-item {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-1-5) var(--spacing-2);
  background: var(--bg-surface);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
}

.weight-name {
  color: var(--text-secondary);
}

.weight-value {
  color: var(--color-info);
  font-weight: var(--font-semibold);
}

/* Trends Panel */
.period-selector {
  display: flex;
  gap: var(--spacing-1);
}

.period-selector button {
  padding: var(--spacing-1-5) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
}

.period-selector button.active {
  background: var(--color-info);
  border-color: var(--color-info);
  color: var(--text-on-primary);
}

.trends-chart {
  margin-bottom: var(--spacing-4);
}

.accuracy-chart {
  width: 100%;
  height: 180px;
}

/* SVG Chart Styles using design tokens */
.grid-line {
  stroke: var(--border-subtle);
}

.axis-text {
  fill: var(--text-tertiary);
}

.trend-line {
  stroke: var(--color-success);
}

.data-point-circle {
  fill: var(--color-success);
  cursor: pointer;
  transition: r 0.2s;
}

.data-point-circle:hover {
  r: 6;
}

.tooltip-bg {
  fill: var(--bg-surface);
}

.tooltip-text-primary {
  fill: var(--text-primary);
}

.tooltip-text-secondary {
  fill: var(--text-secondary);
}

.trend-stats {
  display: flex;
  gap: var(--spacing-8);
  padding: var(--spacing-3);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
}

.trend-stat {
  display: flex;
  flex-direction: column;
}

.trend-stat .stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.trend-stat .stat-value {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

/* Recommendations Panel */
.recommendations-panel {
  margin-bottom: var(--spacing-6);
}

.recommendations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

.recommendation-card {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--color-info);
}

.rec-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-info);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-on-primary);
  flex-shrink: 0;
}

.rec-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-snug);
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid var(--border-subtle);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.btn-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: var(--text-2xl);
  cursor: pointer;
}

.modal-body {
  padding: var(--spacing-6);
}

.detail-section {
  margin-bottom: var(--spacing-6);
}

.detail-section h4 {
  margin: 0 0 var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.detail-row {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-2);
}

.detail-label {
  min-width: 100px;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.detail-value {
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.detail-value.file-path {
  font-family: var(--font-mono);
  color: var(--color-info);
  word-break: break-all;
}

.score-badge.large {
  font-size: var(--text-base);
  padding: var(--spacing-1-5) var(--spacing-3);
}

.factors-breakdown {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.factor-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.factor-row .factor-name {
  min-width: 120px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.factor-bar-container {
  flex: 1;
  height: 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.factor-bar-fill {
  height: 100%;
  border-radius: var(--radius-default);
}

.factor-bar-fill.critical { background: var(--color-error); }
.factor-bar-fill.high { background: var(--chart-orange); }
.factor-bar-fill.medium { background: var(--chart-yellow); }
.factor-bar-fill.low { background: var(--color-success); }

.factor-value {
  min-width: 30px;
  text-align: right;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.tips-list,
.tests-list {
  margin: 0;
  padding-left: var(--spacing-5);
}

.tips-list li,
.tests-list li {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-6);
  border-top: 1px solid var(--border-subtle);
}

.btn-secondary,
.btn-primary {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
}

.btn-secondary {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}

.btn-primary {
  background: var(--color-info);
  border: none;
  color: var(--text-on-primary);
}

.btn-primary:hover {
  background: var(--color-info-hover);
}
</style>
