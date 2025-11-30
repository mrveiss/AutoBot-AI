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
          <span class="icon">🔍</span>
          {{ loading ? 'Analyzing...' : 'Analyze Codebase' }}
        </button>
        <button class="btn-refresh" @click="refreshData" :disabled="loading">
          <span class="icon">↻</span>
          Refresh
        </button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="summary-cards">
      <div class="summary-card high-risk">
        <div class="card-icon">⚠️</div>
        <div class="card-content">
          <span class="card-value">{{ summary.high_risk_files }}</span>
          <span class="card-label">High Risk Files</span>
        </div>
        <div class="card-indicator critical">Needs Attention</div>
      </div>

      <div class="summary-card predictions">
        <div class="card-icon">🐛</div>
        <div class="card-content">
          <span class="card-value">{{ summary.predicted_bugs_next_sprint }}</span>
          <span class="card-label">Predicted Bugs</span>
        </div>
        <div class="card-indicator">Next Sprint</div>
      </div>

      <div class="summary-card accuracy">
        <div class="card-icon">🎯</div>
        <div class="card-content">
          <span class="card-value">{{ summary.model_accuracy.toFixed(1) }}%</span>
          <span class="card-label">Model Accuracy</span>
        </div>
        <div class="accuracy-bar">
          <div class="accuracy-fill" :style="{ width: summary.model_accuracy + '%' }"></div>
        </div>
      </div>

      <div class="summary-card analyzed">
        <div class="card-icon">📁</div>
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
          <h3>🔥 High Risk Files</h3>
          <span class="panel-count">{{ highRiskFiles.length }} files</span>
        </div>
        <div class="panel-content">
          <div v-if="highRiskFiles.length === 0" class="empty-state">
            <span class="empty-icon">✨</span>
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
          <h3>📊 Top Risk Factors</h3>
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
          <h3>📈 Prediction Accuracy</h3>
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
                <line v-for="i in 5" :key="'h' + i" x1="40" x2="580" :y1="i * 30 + 10" :y2="i * 30 + 10" stroke="#2a2a3e" stroke-dasharray="2,2" />
              </g>

              <!-- Y-Axis -->
              <g class="y-axis">
                <text x="35" y="15" text-anchor="end" fill="#666" font-size="9">100%</text>
                <text x="35" y="75" text-anchor="end" fill="#666" font-size="9">75%</text>
                <text x="35" y="135" text-anchor="end" fill="#666" font-size="9">50%</text>
              </g>

              <!-- Accuracy Line -->
              <path v-if="trendLinePath" :d="trendLinePath" fill="none" stroke="#22c55e" stroke-width="2" stroke-linecap="round" />

              <!-- Data Points -->
              <g class="data-points">
                <circle
                  v-for="(point, i) in trendPoints"
                  :key="'p' + i"
                  :cx="point.x"
                  :cy="point.y"
                  r="4"
                  fill="#22c55e"
                  @mouseenter="hoveredPoint = point"
                  @mouseleave="hoveredPoint = null"
                />
              </g>

              <!-- Tooltip -->
              <g v-if="hoveredPoint" class="tooltip">
                <rect :x="hoveredPoint.x - 35" :y="hoveredPoint.y - 40" width="70" height="30" rx="4" fill="#1a1a2e" />
                <text :x="hoveredPoint.x" :y="hoveredPoint.y - 25" text-anchor="middle" fill="#fff" font-size="11">
                  {{ hoveredPoint.accuracy.toFixed(1) }}%
                </text>
                <text :x="hoveredPoint.x" :y="hoveredPoint.y - 12" text-anchor="middle" fill="#888" font-size="9">
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
        <h3>💡 Recommendations</h3>
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
          <button class="btn-close" @click="selectedFile = null">×</button>
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
import { ref, computed, onMounted, watch } from 'vue';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for BugPredictionDashboard
const logger = createLogger('BugPredictionDashboard');

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
    }
  } catch (error) {
    logger.error('Failed to load summary:', error);
    // Demo data
    summary.value = {
      total_files_analyzed: 247,
      high_risk_files: 3,
      predicted_bugs_next_sprint: 8,
      model_accuracy: 72.5,
      top_risk_factors: [
        { factor: 'Bug History', total_score: 350, average: 50 },
        { factor: 'Complexity', total_score: 320, average: 45.7 },
        { factor: 'Change Frequency', total_score: 280, average: 40 },
        { factor: 'Test Coverage', total_score: 250, average: 35.7 },
        { factor: 'File Size', total_score: 180, average: 25.7 },
      ],
      recommendations: [
        'Focus testing efforts on 3 high-risk files',
        'Reduce complexity in src/services/agent_service.py',
        'Increase test coverage for frequently changed files',
        'Review bug patterns in workflow_engine.py',
      ],
    };
  }
}

async function loadHighRiskFiles(): Promise<void> {
  try {
    const response = await fetch('/api/analytics/bug-prediction/high-risk?threshold=60&limit=10');
    if (response.ok) {
      highRiskFiles.value = await response.json();
    }
  } catch (error) {
    logger.error('Failed to load high risk files:', error);
    highRiskFiles.value = [
      {
        file_path: 'src/services/agent_service.py',
        risk_score: 78.5,
        risk_level: 'high',
        factors: { complexity: 85, change_frequency: 72, bug_history: 80 },
        bug_count_history: 12,
        last_bug_date: '2025-01-15',
        prevention_tips: ['Break down complex functions', 'Add regression tests'],
        suggested_tests: ['Add boundary tests', 'Test error handling'],
      },
      {
        file_path: 'src/core/workflow_engine.py',
        risk_score: 72.3,
        risk_level: 'high',
        factors: { complexity: 78, change_frequency: 65, bug_history: 75 },
        bug_count_history: 8,
        last_bug_date: '2025-01-10',
        prevention_tips: ['Review recent changes', 'Add inline comments'],
        suggested_tests: ['Add integration tests'],
      },
      {
        file_path: 'src/api/endpoints.py',
        risk_score: 68.1,
        risk_level: 'high',
        factors: { complexity: 60, change_frequency: 85, bug_history: 55 },
        bug_count_history: 6,
        last_bug_date: '2025-01-08',
        prevention_tips: ['Stabilize module', 'Add regression tests'],
        suggested_tests: ['Test new endpoints'],
      },
    ];
  }
}

async function loadHeatmap(): Promise<void> {
  try {
    const response = await fetch(`/api/analytics/bug-prediction/heatmap?grouping=${heatmapGrouping.value}`);
    if (response.ok) {
      const data = await response.json();
      heatmapData.value = data.data || [];
    }
  } catch (error) {
    logger.error('Failed to load heatmap:', error);
    heatmapData.value = [
      { name: 'src', value: 65, file_count: 150, risk_level: 'high' },
      { name: 'backend', value: 52, file_count: 45, risk_level: 'medium' },
      { name: 'tests', value: 25, file_count: 30, risk_level: 'low' },
      { name: 'scripts', value: 35, file_count: 15, risk_level: 'low' },
      { name: 'docs', value: 12, file_count: 7, risk_level: 'minimal' },
    ];
  }
}

async function loadTrends(): Promise<void> {
  try {
    const response = await fetch(`/api/analytics/bug-prediction/trends?period=${selectedPeriod.value}`);
    if (response.ok) {
      const data = await response.json();
      trendData.value = data.data_points || [];
    }
  } catch (error) {
    logger.error('Failed to load trends:', error);
    // Generate demo trend data
    const days = parseInt(selectedPeriod.value);
    trendData.value = Array.from({ length: Math.min(days, 30) }, (_, i) => {
      const date = new Date();
      date.setDate(date.getDate() - (days - 1 - i));
      return {
        date: date.toISOString().split('T')[0],
        accuracy: 65 + Math.random() * 20,
        predicted_bugs: Math.floor(5 + Math.random() * 10),
        actual_bugs: Math.floor(4 + Math.random() * 8),
      };
    });
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
    }
  } catch (error) {
    logger.error('Failed to load factors:', error);
    riskFactors.value = {
      complexity: 0.20,
      change_frequency: 0.20,
      bug_history: 0.25,
      test_coverage: 0.15,
      code_age: 0.05,
      author_experience: 0.05,
      file_size: 0.05,
      dependency_count: 0.05,
    };
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
    'Bug History': '🐛',
    'Complexity': '🔄',
    'Change Frequency': '📝',
    'Test Coverage': '🧪',
    'File Size': '📦',
  };
  return icons[factor] || '📊';
}

function getFactorClass(value: number): string {
  if (value >= 70) return 'critical';
  if (value >= 50) return 'high';
  if (value >= 30) return 'medium';
  return 'low';
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
.bug-prediction-dashboard {
  padding: 1.5rem;
  background: #0a0a0f;
  min-height: 100vh;
  color: #e0e0e0;
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.dashboard-title {
  font-size: 1.75rem;
  font-weight: 600;
  color: #fff;
  margin: 0;
}

.dashboard-subtitle {
  color: #888;
  margin: 0.25rem 0 0;
  font-size: 0.9rem;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

.btn-analyze,
.btn-refresh {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-analyze {
  background: #22c55e;
  border: none;
  color: #fff;
}

.btn-analyze:hover:not(:disabled) {
  background: #16a34a;
}

.btn-refresh {
  background: #1a1a2e;
  border: 1px solid #333;
  color: #e0e0e0;
}

.btn-refresh:hover:not(:disabled) {
  background: #252540;
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-card {
  background: linear-gradient(135deg, #1a1a2e 0%, #16162a 100%);
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 1rem;
}

.card-icon {
  font-size: 2rem;
}

.card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #fff;
}

.card-label {
  font-size: 0.8rem;
  color: #888;
  margin-top: 0.25rem;
}

.card-indicator {
  font-size: 0.7rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.1);
  color: #888;
}

.card-indicator.critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.accuracy-bar {
  width: 100%;
  height: 6px;
  background: #2a2a3e;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 0.5rem;
}

.accuracy-fill {
  height: 100%;
  background: #22c55e;
  transition: width 0.5s ease;
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

@media (max-width: 1200px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}

/* Panels */
.panel {
  background: #12121a;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #2a2a3e;
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #fff;
}

.panel-count {
  font-size: 0.75rem;
  color: #888;
}

.panel-content {
  padding: 1.25rem;
}

/* Heatmap */
.grouping-toggle {
  display: flex;
  gap: 0.25rem;
}

.grouping-toggle button {
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: 1px solid #333;
  border-radius: 4px;
  color: #888;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.grouping-toggle button.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}

.heatmap-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.heatmap-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.75rem;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 80px;
}

.heatmap-cell.risk-critical {
  background: rgba(239, 68, 68, var(--opacity, 0.5));
  border: 1px solid rgba(239, 68, 68, 0.5);
}

.heatmap-cell.risk-high {
  background: rgba(249, 115, 22, var(--opacity, 0.5));
  border: 1px solid rgba(249, 115, 22, 0.5);
}

.heatmap-cell.risk-medium {
  background: rgba(234, 179, 8, var(--opacity, 0.5));
  border: 1px solid rgba(234, 179, 8, 0.5);
}

.heatmap-cell.risk-low {
  background: rgba(34, 197, 94, var(--opacity, 0.5));
  border: 1px solid rgba(34, 197, 94, 0.5);
}

.heatmap-cell.risk-minimal {
  background: rgba(59, 130, 246, var(--opacity, 0.5));
  border: 1px solid rgba(59, 130, 246, 0.5);
}

.heatmap-cell:hover {
  transform: scale(1.05);
}

.cell-name {
  font-size: 0.75rem;
  color: #fff;
  margin-bottom: 0.25rem;
}

.cell-score {
  font-size: 1.25rem;
  font-weight: 700;
  color: #fff;
}

.heatmap-legend {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #2a2a3e;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.7rem;
  color: #888;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.legend-color.critical { background: #ef4444; }
.legend-color.high { background: #f97316; }
.legend-color.medium { background: #eab308; }
.legend-color.low { background: #22c55e; }
.legend-color.minimal { background: #3b82f6; }

/* High Risk Files */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2rem;
  color: #666;
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.high-risk-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.risk-file-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem;
  background: #1a1a2e;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  border-left: 3px solid transparent;
}

.risk-file-item.risk-critical {
  border-left-color: #ef4444;
}

.risk-file-item.risk-high {
  border-left-color: #f97316;
}

.risk-file-item:hover {
  background: #1e1e35;
}

.file-rank {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2a2a3e;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
}

.file-info {
  flex: 1;
}

.file-path {
  display: block;
  font-size: 0.8rem;
  font-family: monospace;
  color: #3b82f6;
}

.file-bugs {
  font-size: 0.7rem;
  color: #888;
}

.score-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 700;
}

.score-badge.critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.score-badge.high {
  background: rgba(249, 115, 22, 0.2);
  color: #f97316;
}

.score-badge.medium {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.score-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

/* Factors Panel */
.factors-list {
  margin-bottom: 1.5rem;
}

.factor-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid #1a1a2e;
}

.factor-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 140px;
}

.factor-icon {
  font-size: 1rem;
}

.factor-name {
  font-size: 0.8rem;
  color: #ccc;
}

.factor-bar {
  flex: 1;
  height: 8px;
  background: #1a1a2e;
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
}

.bar-fill.critical { background: #ef4444; }
.bar-fill.high { background: #f97316; }
.bar-fill.medium { background: #eab308; }
.bar-fill.low { background: #22c55e; }

.factor-score {
  min-width: 30px;
  font-size: 0.8rem;
  font-weight: 600;
  color: #fff;
  text-align: right;
}

.factors-weights {
  padding-top: 1rem;
  border-top: 1px solid #2a2a3e;
}

.factors-weights h4 {
  margin: 0 0 0.75rem;
  font-size: 0.85rem;
  color: #888;
}

.weights-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
}

.weight-item {
  display: flex;
  justify-content: space-between;
  padding: 0.375rem 0.5rem;
  background: #1a1a2e;
  border-radius: 4px;
  font-size: 0.75rem;
}

.weight-name {
  color: #888;
}

.weight-value {
  color: #3b82f6;
  font-weight: 600;
}

/* Trends Panel */
.period-selector {
  display: flex;
  gap: 0.25rem;
}

.period-selector button {
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: 1px solid #333;
  border-radius: 4px;
  color: #888;
  font-size: 0.75rem;
  cursor: pointer;
}

.period-selector button.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}

.trends-chart {
  margin-bottom: 1rem;
}

.accuracy-chart {
  width: 100%;
  height: 180px;
}

.data-point {
  cursor: pointer;
  transition: r 0.2s;
}

.data-point:hover {
  r: 6;
}

.trend-stats {
  display: flex;
  gap: 2rem;
  padding: 0.75rem;
  background: #1a1a2e;
  border-radius: 8px;
}

.trend-stat {
  display: flex;
  flex-direction: column;
}

.trend-stat .stat-label {
  font-size: 0.7rem;
  color: #666;
}

.trend-stat .stat-value {
  font-size: 1.1rem;
  font-weight: 600;
  color: #fff;
}

/* Recommendations Panel */
.recommendations-panel {
  margin-bottom: 1.5rem;
}

.recommendations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.recommendation-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: #1a1a2e;
  border-radius: 8px;
  border-left: 3px solid #3b82f6;
}

.rec-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #3b82f6;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}

.rec-text {
  font-size: 0.85rem;
  color: #ccc;
  line-height: 1.4;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #12121a;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #2a2a3e;
}

.modal-header h3 {
  margin: 0;
  color: #fff;
}

.btn-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: #888;
  font-size: 1.5rem;
  cursor: pointer;
}

.modal-body {
  padding: 1.5rem;
}

.detail-section {
  margin-bottom: 1.5rem;
}

.detail-section h4 {
  margin: 0 0 0.75rem;
  font-size: 0.9rem;
  color: #888;
}

.detail-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.detail-label {
  min-width: 100px;
  color: #666;
  font-size: 0.85rem;
}

.detail-value {
  color: #e0e0e0;
  font-size: 0.85rem;
}

.detail-value.file-path {
  font-family: monospace;
  color: #3b82f6;
  word-break: break-all;
}

.score-badge.large {
  font-size: 1rem;
  padding: 0.375rem 0.75rem;
}

.factors-breakdown {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.factor-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.factor-row .factor-name {
  min-width: 120px;
  font-size: 0.8rem;
  color: #888;
}

.factor-bar-container {
  flex: 1;
  height: 8px;
  background: #1a1a2e;
  border-radius: 4px;
  overflow: hidden;
}

.factor-bar-fill {
  height: 100%;
  border-radius: 4px;
}

.factor-bar-fill.critical { background: #ef4444; }
.factor-bar-fill.high { background: #f97316; }
.factor-bar-fill.medium { background: #eab308; }
.factor-bar-fill.low { background: #22c55e; }

.factor-value {
  min-width: 30px;
  text-align: right;
  font-size: 0.8rem;
  font-weight: 600;
  color: #fff;
}

.tips-list,
.tests-list {
  margin: 0;
  padding-left: 1.25rem;
}

.tips-list li,
.tests-list li {
  font-size: 0.85rem;
  color: #ccc;
  margin-bottom: 0.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #2a2a3e;
}

.btn-secondary,
.btn-primary {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
}

.btn-secondary {
  background: #1a1a2e;
  border: 1px solid #333;
  color: #e0e0e0;
}

.btn-primary {
  background: #3b82f6;
  border: none;
  color: #fff;
}

.btn-primary:hover {
  background: #2563eb;
}
</style>
