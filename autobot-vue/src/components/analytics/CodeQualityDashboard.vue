<template>
  <div class="code-quality-dashboard">
    <!-- Header with Real-time Status -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2 class="dashboard-title">Code Quality Dashboard</h2>
        <div class="realtime-status" :class="{ connected: wsConnected }">
          <span class="status-dot"></span>
          {{ wsConnected ? 'Live' : 'Offline' }}
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-refresh" @click="refreshData" :disabled="loading">
          <span class="icon">↻</span>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <div class="export-dropdown" v-click-outside="closeExportMenu">
          <button class="btn-export" @click="exportMenuOpen = !exportMenuOpen">
            <span class="icon">↓</span>
            Export
          </button>
          <div v-if="exportMenuOpen" class="dropdown-menu">
            <button @click="exportReport('json')">Export JSON</button>
            <button @click="exportReport('csv')">Export CSV</button>
            <button @click="exportReport('pdf')">Export PDF</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Health Score Hero Card -->
    <div class="health-hero">
      <div class="health-score-circle">
        <svg viewBox="0 0 120 120" class="score-ring">
          <circle cx="60" cy="60" r="54" fill="none" stroke="#2a2a3e" stroke-width="8" />
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            :stroke="getScoreColor(healthScore.overall)"
            stroke-width="8"
            :stroke-dasharray="scoreCircleLength"
            :stroke-dashoffset="scoreOffset"
            stroke-linecap="round"
            transform="rotate(-90 60 60)"
            class="score-progress"
          />
        </svg>
        <div class="score-content">
          <span class="score-value">{{ Math.round(healthScore.overall) }}</span>
          <span class="score-grade" :class="'grade-' + healthScore.grade">{{ healthScore.grade }}</span>
        </div>
      </div>
      <div class="health-details">
        <h3>Overall Health Score</h3>
        <p class="health-description">
          Your codebase is rated <strong :class="'grade-' + healthScore.grade">{{ getGradeDescription(healthScore.grade) }}</strong>
        </p>
        <div class="trend-indicator" :class="getTrendClass(healthScore.trend)">
          <span class="trend-arrow">{{ healthScore.trend >= 0 ? '↑' : '↓' }}</span>
          {{ Math.abs(healthScore.trend).toFixed(1) }}% from last period
        </div>
        <div class="recommendations" v-if="healthScore.recommendations.length > 0">
          <h4>Top Recommendations</h4>
          <ul>
            <li v-for="(rec, i) in healthScore.recommendations.slice(0, 3)" :key="i">
              {{ rec }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Metrics Grid -->
    <div class="metrics-grid">
      <div
        v-for="metric in metrics"
        :key="metric.category"
        class="metric-card"
        :class="{ 'low-score': metric.value < 60 }"
        @click="drillDown(metric.category)"
      >
        <div class="metric-header">
          <span class="metric-icon">{{ getMetricIcon(metric.category) }}</span>
          <span class="metric-name">{{ metric.name }}</span>
        </div>
        <div class="metric-body">
          <div class="metric-score">
            <span class="score-number">{{ metric.value.toFixed(1) }}</span>
            <span class="score-grade" :class="'grade-' + metric.grade">{{ metric.grade }}</span>
          </div>
          <div class="metric-bar">
            <div
              class="bar-fill"
              :style="{ width: metric.value + '%' }"
              :class="getScoreClass(metric.value)"
            ></div>
          </div>
        </div>
        <div class="metric-footer">
          <span class="metric-weight">Weight: {{ (metric.weight * 100).toFixed(0) }}%</span>
          <span class="metric-trend" :class="getTrendClass(metric.trend)">
            {{ metric.trend >= 0 ? '+' : '' }}{{ metric.trend.toFixed(1) }}%
          </span>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid">
      <!-- Pattern Distribution -->
      <div class="panel patterns-panel">
        <div class="panel-header">
          <h3>Pattern Distribution</h3>
          <div class="severity-filter">
            <button
              v-for="sev in ['all', 'critical', 'high', 'medium', 'low']"
              :key="sev"
              :class="{ active: selectedSeverity === sev }"
              @click="selectedSeverity = sev"
            >
              {{ sev === 'all' ? 'All' : sev }}
            </button>
          </div>
        </div>
        <div class="panel-content">
          <div class="patterns-chart">
            <div
              v-for="pattern in filteredPatterns"
              :key="pattern.type"
              class="pattern-bar"
            >
              <div class="pattern-info">
                <span class="pattern-icon" :class="'severity-' + pattern.severity">
                  {{ getPatternIcon(pattern.severity) }}
                </span>
                <span class="pattern-name">{{ pattern.display_name }}</span>
              </div>
              <div class="pattern-value">
                <div class="bar-container">
                  <div
                    class="bar"
                    :style="{ width: pattern.percentage + '%' }"
                    :class="'severity-' + pattern.severity"
                  ></div>
                </div>
                <span class="count">{{ pattern.count }}</span>
              </div>
            </div>
          </div>
          <div class="patterns-summary">
            <div class="summary-stat critical">
              <span class="stat-value">{{ patternStats.critical }}</span>
              <span class="stat-label">Critical</span>
            </div>
            <div class="summary-stat high">
              <span class="stat-value">{{ patternStats.high }}</span>
              <span class="stat-label">High</span>
            </div>
            <div class="summary-stat medium">
              <span class="stat-value">{{ patternStats.medium }}</span>
              <span class="stat-label">Medium</span>
            </div>
            <div class="summary-stat info">
              <span class="stat-value">{{ patternStats.info }}</span>
              <span class="stat-label">Info</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Complexity Hotspots -->
      <div class="panel complexity-panel">
        <div class="panel-header">
          <h3>Complexity Analysis</h3>
          <div class="complexity-stats">
            <span class="stat">
              Avg Cyclomatic: <strong>{{ complexity.averages.cyclomatic.toFixed(1) }}</strong>
            </span>
            <span class="stat">
              Max: <strong :class="{ warning: complexity.maximums.cyclomatic > 20 }">
                {{ complexity.maximums.cyclomatic }}
              </strong>
            </span>
          </div>
        </div>
        <div class="panel-content">
          <div class="hotspots-list">
            <div
              v-for="(hotspot, i) in complexity.hotspots"
              :key="hotspot.file"
              class="hotspot-item"
              :class="{ 'critical-complexity': hotspot.complexity > 20 }"
            >
              <div class="hotspot-rank">{{ i + 1 }}</div>
              <div class="hotspot-info">
                <span class="hotspot-file">{{ truncatePath(hotspot.file) }}</span>
                <span class="hotspot-lines">{{ hotspot.lines }} lines</span>
              </div>
              <div class="hotspot-complexity">
                <div class="complexity-badge" :class="getComplexityClass(hotspot.complexity)">
                  {{ hotspot.complexity }}
                </div>
              </div>
            </div>
          </div>
          <div class="complexity-thresholds">
            <div class="threshold-item">
              <span class="threshold-color safe"></span>
              <span>1-10 (Simple)</span>
            </div>
            <div class="threshold-item">
              <span class="threshold-color warning"></span>
              <span>11-20 (Complex)</span>
            </div>
            <div class="threshold-item">
              <span class="threshold-color critical"></span>
              <span>21+ (Very Complex)</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Quality Trends -->
    <div class="panel trends-panel">
      <div class="panel-header">
        <h3>Quality Trends</h3>
        <div class="period-selector">
          <button
            v-for="period in ['7d', '14d', '30d', '90d']"
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
          <svg viewBox="0 0 800 200" class="line-chart" preserveAspectRatio="xMidYMid meet">
            <!-- Grid -->
            <g class="grid">
              <line v-for="i in 5" :key="'h' + i" :x1="50" :x2="780" :y1="i * 35 + 10" :y2="i * 35 + 10" stroke="#2a2a3e" stroke-dasharray="2,2" />
            </g>

            <!-- Y-Axis -->
            <g class="y-axis">
              <text v-for="(label, i) in yAxisLabels" :key="'y' + i" :x="45" :y="i * 35 + 15" text-anchor="end" fill="#666" font-size="10">
                {{ label }}
              </text>
            </g>

            <!-- Gradient Area -->
            <defs>
              <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.3" />
                <stop offset="100%" stop-color="#3b82f6" stop-opacity="0" />
              </linearGradient>
            </defs>

            <!-- Area Fill -->
            <path v-if="trendAreaPath" :d="trendAreaPath" fill="url(#areaGradient)" />

            <!-- Line -->
            <path v-if="trendLinePath" :d="trendLinePath" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

            <!-- Data Points -->
            <g class="data-points">
              <circle
                v-for="(point, i) in trendPoints"
                :key="'p' + i"
                :cx="point.x"
                :cy="point.y"
                r="4"
                fill="#3b82f6"
                stroke="#0a0a0f"
                stroke-width="2"
                class="data-point"
                @mouseenter="hoveredTrendPoint = point"
                @mouseleave="hoveredTrendPoint = null"
              />
            </g>

            <!-- Tooltip -->
            <g v-if="hoveredTrendPoint" class="tooltip">
              <rect :x="hoveredTrendPoint.x - 45" :y="hoveredTrendPoint.y - 50" width="90" height="40" rx="6" fill="#1a1a2e" stroke="#3b82f6" stroke-width="1" />
              <text :x="hoveredTrendPoint.x" :y="hoveredTrendPoint.y - 35" text-anchor="middle" fill="#fff" font-size="12" font-weight="600">
                {{ hoveredTrendPoint.score.toFixed(1) }}
              </text>
              <text :x="hoveredTrendPoint.x" :y="hoveredTrendPoint.y - 20" text-anchor="middle" fill="#888" font-size="10">
                {{ hoveredTrendPoint.date }}
              </text>
            </g>

            <!-- X-Axis Labels -->
            <g class="x-axis">
              <text
                v-for="(label, i) in xAxisLabels"
                :key="'x' + i"
                :x="label.x"
                y="195"
                text-anchor="middle"
                fill="#666"
                font-size="9"
              >
                {{ label.text }}
              </text>
            </g>
          </svg>
        </div>

        <!-- Trend Statistics -->
        <div class="trend-stats">
          <div class="trend-stat">
            <span class="stat-label">Current</span>
            <span class="stat-value">{{ trendStats.current.toFixed(1) }}</span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Change</span>
            <span class="stat-value" :class="getTrendClass(trendStats.change)">
              {{ trendStats.change >= 0 ? '+' : '' }}{{ trendStats.change.toFixed(1) }}%
            </span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Average</span>
            <span class="stat-value">{{ trendStats.average.toFixed(1) }}</span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Min</span>
            <span class="stat-value">{{ trendStats.min.toFixed(1) }}</span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Max</span>
            <span class="stat-value">{{ trendStats.max.toFixed(1) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Codebase Stats Footer -->
    <div class="codebase-stats">
      <div class="stat-item">
        <span class="stat-icon">📁</span>
        <span class="stat-value">{{ codebaseStats.files.toLocaleString() }}</span>
        <span class="stat-label">Files</span>
      </div>
      <div class="stat-item">
        <span class="stat-icon">📝</span>
        <span class="stat-value">{{ codebaseStats.lines.toLocaleString() }}</span>
        <span class="stat-label">Lines of Code</span>
      </div>
      <div class="stat-item">
        <span class="stat-icon">⚠️</span>
        <span class="stat-value">{{ codebaseStats.issues.toLocaleString() }}</span>
        <span class="stat-label">Issues</span>
      </div>
      <div class="stat-item">
        <span class="stat-icon">🕒</span>
        <span class="stat-value">{{ lastUpdated }}</span>
        <span class="stat-label">Last Updated</span>
      </div>
    </div>

    <!-- Drill-Down Modal -->
    <div v-if="drillDownCategory" class="modal-overlay" @click.self="drillDownCategory = null">
      <div class="modal-content drill-down-modal">
        <div class="modal-header">
          <h3>{{ formatCategoryName(drillDownCategory) }} - Detailed View</h3>
          <button class="btn-close" @click="drillDownCategory = null">×</button>
        </div>
        <div class="modal-body">
          <div class="drill-down-summary">
            <div class="summary-card">
              <span class="card-value">{{ drillDownData.total_files }}</span>
              <span class="card-label">Files Affected</span>
            </div>
            <div class="summary-card">
              <span class="card-value">{{ drillDownData.total_issues }}</span>
              <span class="card-label">Total Issues</span>
            </div>
            <div class="summary-card">
              <span class="card-value">{{ drillDownData.average_score.toFixed(1) }}</span>
              <span class="card-label">Average Score</span>
            </div>
          </div>
          <div class="drill-down-files">
            <table class="files-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Issues</th>
                  <th>Score</th>
                  <th>Top Issue</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="file in drillDownData.files" :key="file.path">
                  <td class="file-path">{{ truncatePath(file.path) }}</td>
                  <td class="issues-count">{{ file.issues }}</td>
                  <td>
                    <span class="score-badge" :class="getScoreClass(file.score)">
                      {{ file.score }}
                    </span>
                  </td>
                  <td class="top-issue">{{ file.top_issue }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="drillDownCategory = null">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('CodeQualityDashboard');

// Types
interface HealthScore {
  overall: number;
  grade: string;
  trend: number;
  breakdown: Record<string, number>;
  recommendations: string[];
}

interface Metric {
  name: string;
  category: string;
  value: number;
  grade: string;
  trend: number;
  weight: number;
}

interface Pattern {
  type: string;
  display_name: string;
  count: number;
  percentage: number;
  severity: string;
}

interface Complexity {
  averages: { cyclomatic: number; cognitive: number };
  maximums: { cyclomatic: number; cognitive: number };
  hotspots: Array<{ file: string; complexity: number; lines: number }>;
}

interface TrendPoint {
  x: number;
  y: number;
  score: number;
  date: string;
}

// State
const loading = ref(false);
const wsConnected = ref(false);
const exportMenuOpen = ref(false);
const selectedSeverity = ref('all');
const selectedPeriod = ref('30d');
const drillDownCategory = ref<string | null>(null);
const hoveredTrendPoint = ref<TrendPoint | null>(null);

const healthScore = ref<HealthScore>({
  overall: 0,
  grade: 'C',
  trend: 0,
  breakdown: {},
  recommendations: [],
});

const metrics = ref<Metric[]>([]);
const patterns = ref<Pattern[]>([]);
const complexity = ref<Complexity>({
  averages: { cyclomatic: 0, cognitive: 0 },
  maximums: { cyclomatic: 0, cognitive: 0 },
  hotspots: [],
});
const trendData = ref<Array<{ date: string; score: number }>>([]);
const codebaseStats = ref({ files: 0, lines: 0, issues: 0 });
const drillDownData = ref({ total_files: 0, total_issues: 0, average_score: 0, files: [] as any[] });

let ws: WebSocket | null = null;

// Computed
const scoreCircleLength = computed(() => 2 * Math.PI * 54);
const scoreOffset = computed(() => {
  const percentage = healthScore.value.overall / 100;
  return scoreCircleLength.value * (1 - percentage);
});

const filteredPatterns = computed(() => {
  if (selectedSeverity.value === 'all') return patterns.value;
  return patterns.value.filter(p => p.severity === selectedSeverity.value);
});

const patternStats = computed(() => {
  const stats = { critical: 0, high: 0, medium: 0, info: 0 };
  patterns.value.forEach(p => {
    if (p.severity === 'critical') stats.critical += p.count;
    else if (p.severity === 'high') stats.high += p.count;
    else if (p.severity === 'medium') stats.medium += p.count;
    else stats.info += p.count;
  });
  return stats;
});

const yAxisLabels = computed(() => {
  return ['100', '80', '60', '40', '20', '0'];
});

const trendPoints = computed((): TrendPoint[] => {
  if (trendData.value.length === 0) return [];

  const chartWidth = 730;
  const chartHeight = 150;
  const startX = 50;

  return trendData.value.map((point, i) => ({
    x: startX + (i / Math.max(trendData.value.length - 1, 1)) * chartWidth,
    y: 10 + chartHeight - (point.score / 100) * chartHeight,
    score: point.score,
    date: formatDate(point.date),
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

const trendAreaPath = computed(() => {
  if (trendPoints.value.length < 2) return '';
  const points = trendPoints.value;
  const bottom = 160;
  let path = `M ${points[0].x} ${bottom}`;
  path += ` L ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    path += ` L ${points[i].x} ${points[i].y}`;
  }
  path += ` L ${points[points.length - 1].x} ${bottom}`;
  path += ' Z';
  return path;
});

const xAxisLabels = computed(() => {
  if (trendData.value.length === 0) return [];
  const step = Math.max(1, Math.floor(trendData.value.length / 7));
  return trendData.value
    .filter((_, i) => i % step === 0 || i === trendData.value.length - 1)
    .map((point, i, arr) => ({
      x: 50 + (trendData.value.indexOf(point) / Math.max(trendData.value.length - 1, 1)) * 730,
      text: formatShortDate(point.date),
    }));
});

const trendStats = computed(() => {
  if (trendData.value.length === 0) {
    return { current: 0, change: 0, average: 0, min: 0, max: 0 };
  }
  const scores = trendData.value.map(t => t.score);
  const current = scores[scores.length - 1] || 0;
  const first = scores[0] || 0;
  const change = first > 0 ? ((current - first) / first) * 100 : 0;
  return {
    current,
    change,
    average: scores.reduce((a, b) => a + b, 0) / scores.length,
    min: Math.min(...scores),
    max: Math.max(...scores),
  };
});

const lastUpdated = computed(() => {
  return new Date().toLocaleTimeString();
});

// Methods
async function refreshData(): Promise<void> {
  loading.value = true;
  try {
    await Promise.all([
      loadHealthScore(),
      loadMetrics(),
      loadPatterns(),
      loadComplexity(),
      loadTrends(),
      loadSnapshot(),
    ]);
  } catch (error) {
    logger.error('Failed to refresh data:', error);
  } finally {
    loading.value = false;
  }
}

async function loadHealthScore(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch('/api/quality/health-score');
    if (response.ok) {
      healthScore.value = await response.json();
    } else {
      logger.warn('Failed to load health score: HTTP', response.status);
    }
  } catch (error) {
    logger.error('Failed to load health score:', error);
    // Keep default empty state
  }
}

async function loadMetrics(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch('/api/quality/metrics');
    if (response.ok) {
      metrics.value = await response.json();
    } else {
      logger.warn('Failed to load metrics: HTTP', response.status);
      metrics.value = [];
    }
  } catch (error) {
    logger.error('Failed to load metrics:', error);
    metrics.value = [];
  }
}

async function loadPatterns(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch('/api/quality/patterns');
    if (response.ok) {
      patterns.value = await response.json();
    } else {
      logger.warn('Failed to load patterns: HTTP', response.status);
      patterns.value = [];
    }
  } catch (error) {
    logger.error('Failed to load patterns:', error);
    patterns.value = [];
  }
}

async function loadComplexity(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch('/api/quality/complexity?top_n=5');
    if (response.ok) {
      complexity.value = await response.json();
    } else {
      logger.warn('Failed to load complexity: HTTP', response.status);
    }
  } catch (error) {
    logger.error('Failed to load complexity:', error);
    // Keep default empty state
  }
}

async function loadTrends(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch(`/api/quality/trends?period=${selectedPeriod.value}`);
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

async function loadSnapshot(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch('/api/quality/snapshot');
    if (response.ok) {
      const data = await response.json();
      codebaseStats.value = data.codebase_stats || { files: 0, lines: 0, issues: 0 };
    } else {
      logger.warn('Failed to load snapshot: HTTP', response.status);
    }
  } catch (error) {
    logger.error('Failed to load snapshot:', error);
    // Keep default empty state
  }
}

async function drillDown(category: string): Promise<void> {
  drillDownCategory.value = category;
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch(`/api/quality/drill-down/${category}`);
    if (response.ok) {
      drillDownData.value = await response.json();
    } else {
      logger.warn('Failed to load drill-down data: HTTP', response.status);
      drillDownData.value = { total_files: 0, total_issues: 0, average_score: 0, files: [] };
    }
  } catch (error) {
    logger.error('Failed to load drill-down data:', error);
    drillDownData.value = { total_files: 0, total_issues: 0, average_score: 0, files: [] };
  }
}

async function exportReport(format: string): Promise<void> {
  exportMenuOpen.value = false;
  try {
    // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
    const response = await fetch(`/api/quality/export?format=${format}`);
    if (response.ok) {
      const data = await response.json();
      if (format === 'json') {
        downloadFile(JSON.stringify(data, null, 2), `quality-report-${Date.now()}.json`, 'application/json');
      } else if (format === 'csv') {
        downloadFile(data.content, `quality-report-${Date.now()}.csv`, 'text/csv');
      } else {
        logger.info('PDF export not yet implemented');
      }
    }
  } catch (error) {
    logger.error('Failed to export report:', error);
  }
}

function downloadFile(content: string, filename: string, type: string): void {
  const blob = new Blob([content], { type });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  window.URL.revokeObjectURL(url);
}

function closeExportMenu(): void {
  exportMenuOpen.value = false;
}

function connectWebSocket(): void {
  // Issue #552: Fixed path - backend uses /api/quality/* not /api/analytics/quality/*
  const wsUrl = `ws://${window.location.host}/api/quality/ws`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsConnected.value = true;
    logger.debug('WebSocket connected');
  };

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      handleWebSocketMessage(message);
    } catch (error) {
      logger.error('Failed to parse WebSocket message:', error);
    }
  };

  ws.onclose = () => {
    wsConnected.value = false;
    logger.debug('WebSocket disconnected');
    // Reconnect after 5 seconds
    setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = (error) => {
    logger.error('WebSocket error:', error);
    wsConnected.value = false;
  };
}

function handleWebSocketMessage(message: any): void {
  switch (message.type) {
    case 'snapshot':
      // Update all data from snapshot
      if (message.data.health_score) {
        healthScore.value = message.data.health_score;
      }
      break;
    case 'metric_update':
      // Update specific metric
      const metricIndex = metrics.value.findIndex(m => m.category === message.data.category);
      if (metricIndex >= 0) {
        metrics.value[metricIndex] = { ...metrics.value[metricIndex], ...message.data };
      }
      break;
    case 'pattern_update':
      loadPatterns();
      break;
    case 'pong':
      // Heartbeat response
      break;
  }
}

// Utility Functions
function getScoreColor(score: number): string {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#eab308';
  if (score >= 40) return '#f97316';
  return '#ef4444';
}

function getScoreClass(score: number): string {
  if (score >= 80) return 'excellent';
  if (score >= 60) return 'good';
  if (score >= 40) return 'warning';
  return 'critical';
}

function getTrendClass(trend: number): string {
  if (trend > 0) return 'positive';
  if (trend < 0) return 'negative';
  return 'neutral';
}

function getGradeDescription(grade: string): string {
  const descriptions: Record<string, string> = {
    A: 'Excellent',
    B: 'Good',
    C: 'Acceptable',
    D: 'Needs Improvement',
    F: 'Critical',
  };
  return descriptions[grade] || 'Unknown';
}

function getMetricIcon(category: string): string {
  const icons: Record<string, string> = {
    maintainability: '🔧',
    reliability: '🛡️',
    security: '🔒',
    performance: '⚡',
    testability: '🧪',
    documentation: '📝',
  };
  return icons[category] || '📊';
}

function getPatternIcon(severity: string): string {
  const icons: Record<string, string> = {
    critical: '🔴',
    high: '🟠',
    medium: '🟡',
    low: '🟢',
    info: '🔵',
  };
  return icons[severity] || '⚪';
}

function getComplexityClass(complexity: number): string {
  if (complexity <= 10) return 'safe';
  if (complexity <= 20) return 'warning';
  return 'critical';
}

function formatCategoryName(category: string): string {
  return category.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function truncatePath(path: string): string {
  if (path.length <= 35) return path;
  const parts = path.split('/');
  if (parts.length <= 2) return path;
  return `.../${parts.slice(-2).join('/')}`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

// Directive for click outside
const vClickOutside = {
  mounted(el: HTMLElement, binding: any) {
    (el as any)._clickOutside = (event: Event) => {
      if (!(el === event.target || el.contains(event.target as Node))) {
        binding.value();
      }
    };
    document.addEventListener('click', (el as any)._clickOutside);
  },
  unmounted(el: HTMLElement) {
    document.removeEventListener('click', (el as any)._clickOutside);
  },
};

// Lifecycle
onMounted(() => {
  refreshData();
  connectWebSocket();
});

onUnmounted(() => {
  if (ws) {
    ws.close();
  }
});

watch(selectedPeriod, () => {
  loadTrends();
});
</script>

<style scoped>
.code-quality-dashboard {
  padding: 1.5rem;
  background: #0a0a0f;
  min-height: 100vh;
  color: #e0e0e0;
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.dashboard-title {
  font-size: 1.75rem;
  font-weight: 600;
  color: #fff;
  margin: 0;
}

.realtime-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  background: rgba(239, 68, 68, 0.2);
  border-radius: 20px;
  font-size: 0.75rem;
  color: #ef4444;
}

.realtime-status.connected {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

.btn-refresh,
.btn-export {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh {
  background: #1a1a2e;
  border: 1px solid #333;
  color: #e0e0e0;
}

.btn-refresh:hover:not(:disabled) {
  background: #252540;
  border-color: #444;
}

.btn-export {
  background: #3b82f6;
  border: none;
  color: #fff;
}

.btn-export:hover {
  background: #2563eb;
}

.export-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.5rem;
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 8px;
  overflow: hidden;
  z-index: 100;
}

.dropdown-menu button {
  display: block;
  width: 100%;
  padding: 0.75rem 1rem;
  background: transparent;
  border: none;
  color: #e0e0e0;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.dropdown-menu button:hover {
  background: #252540;
}

/* Health Hero Card */
.health-hero {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 2rem;
  background: linear-gradient(135deg, #1a1a2e 0%, #16162a 100%);
  border: 1px solid #2a2a3e;
  border-radius: 16px;
  margin-bottom: 1.5rem;
}

.health-score-circle {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.score-ring {
  width: 100%;
  height: 100%;
}

.score-progress {
  transition: stroke-dashoffset 1s ease-out;
}

.score-content {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.score-value {
  display: block;
  font-size: 2rem;
  font-weight: 700;
  color: #fff;
  line-height: 1;
}

.score-grade {
  display: inline-block;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-top: 0.25rem;
}

.grade-A { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
.grade-B { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
.grade-C { background: rgba(234, 179, 8, 0.2); color: #eab308; }
.grade-D { background: rgba(249, 115, 22, 0.2); color: #f97316; }
.grade-F { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

.health-details {
  flex: 1;
}

.health-details h3 {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
  color: #fff;
}

.health-description {
  margin: 0 0 0.75rem;
  color: #888;
}

.trend-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  margin-bottom: 1rem;
}

.trend-indicator.positive {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.trend-indicator.negative {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.trend-indicator.neutral {
  background: rgba(156, 163, 175, 0.1);
  color: #9ca3af;
}

.recommendations h4 {
  margin: 0 0 0.5rem;
  font-size: 0.9rem;
  color: #aaa;
}

.recommendations ul {
  margin: 0;
  padding-left: 1.25rem;
}

.recommendations li {
  font-size: 0.8rem;
  color: #888;
  margin-bottom: 0.25rem;
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.metric-card {
  background: #12121a;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.2s;
}

.metric-card:hover {
  border-color: #3b82f6;
  transform: translateY(-2px);
}

.metric-card.low-score {
  border-color: rgba(239, 68, 68, 0.3);
}

.metric-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.metric-icon {
  font-size: 1.25rem;
}

.metric-name {
  font-size: 0.875rem;
  color: #ccc;
}

.metric-body {
  margin-bottom: 0.5rem;
}

.metric-score {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.score-number {
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
}

.metric-bar {
  height: 4px;
  background: #2a2a3e;
  border-radius: 2px;
  overflow: hidden;
}

.metric-bar .bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s ease;
}

.bar-fill.excellent { background: #22c55e; }
.bar-fill.good { background: #3b82f6; }
.bar-fill.warning { background: #eab308; }
.bar-fill.critical { background: #ef4444; }

.metric-footer {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  color: #666;
}

.metric-trend.positive { color: #22c55e; }
.metric-trend.negative { color: #ef4444; }

/* Panels */
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

.panel-content {
  padding: 1.25rem;
}

.severity-filter {
  display: flex;
  gap: 0.25rem;
}

.severity-filter button {
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: 1px solid #333;
  border-radius: 4px;
  color: #888;
  font-size: 0.7rem;
  text-transform: capitalize;
  cursor: pointer;
  transition: all 0.2s;
}

.severity-filter button.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}

/* Patterns */
.patterns-chart {
  margin-bottom: 1rem;
}

.pattern-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid #1a1a2e;
}

.pattern-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 150px;
}

.pattern-icon {
  font-size: 0.875rem;
}

.pattern-name {
  font-size: 0.8rem;
  color: #ccc;
}

.pattern-value {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.bar-container {
  flex: 1;
  height: 8px;
  background: #1a1a2e;
  border-radius: 4px;
  overflow: hidden;
}

.bar-container .bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
}

.bar.severity-critical { background: #ef4444; }
.bar.severity-high { background: #f97316; }
.bar.severity-medium { background: #eab308; }
.bar.severity-low { background: #22c55e; }
.bar.severity-info { background: #3b82f6; }

.count {
  min-width: 30px;
  font-size: 0.8rem;
  font-weight: 600;
  color: #fff;
  text-align: right;
}

.patterns-summary {
  display: flex;
  gap: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #2a2a3e;
}

.summary-stat {
  flex: 1;
  text-align: center;
  padding: 0.75rem;
  border-radius: 8px;
}

.summary-stat.critical { background: rgba(239, 68, 68, 0.1); }
.summary-stat.high { background: rgba(249, 115, 22, 0.1); }
.summary-stat.medium { background: rgba(234, 179, 8, 0.1); }
.summary-stat.info { background: rgba(59, 130, 246, 0.1); }

.summary-stat .stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
}

.summary-stat .stat-label {
  font-size: 0.7rem;
  color: #888;
  text-transform: uppercase;
}

/* Complexity */
.complexity-stats {
  display: flex;
  gap: 1rem;
}

.complexity-stats .stat {
  font-size: 0.75rem;
  color: #888;
}

.complexity-stats strong {
  color: #fff;
}

.complexity-stats .warning {
  color: #ef4444;
}

.hotspots-list {
  margin-bottom: 1rem;
}

.hotspot-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #1a1a2e;
  border-radius: 8px;
  margin-bottom: 0.5rem;
}

.hotspot-item.critical-complexity {
  border-left: 3px solid #ef4444;
}

.hotspot-rank {
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

.hotspot-info {
  flex: 1;
}

.hotspot-file {
  display: block;
  font-size: 0.8rem;
  font-family: monospace;
  color: #3b82f6;
}

.hotspot-lines {
  font-size: 0.7rem;
  color: #666;
}

.complexity-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 600;
}

.complexity-badge.safe {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.complexity-badge.warning {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.complexity-badge.critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.complexity-thresholds {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid #2a2a3e;
}

.threshold-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.7rem;
  color: #888;
}

.threshold-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.threshold-color.safe { background: #22c55e; }
.threshold-color.warning { background: #eab308; }
.threshold-color.critical { background: #ef4444; }

/* Trends Panel */
.trends-panel {
  margin-bottom: 1.5rem;
}

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
  transition: all 0.2s;
}

.period-selector button.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}

.trends-chart {
  margin-bottom: 1rem;
}

.line-chart {
  width: 100%;
  height: 200px;
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
  padding: 1rem;
  background: #1a1a2e;
  border-radius: 8px;
}

.trend-stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.trend-stat .stat-label {
  font-size: 0.75rem;
  color: #666;
}

.trend-stat .stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #fff;
}

.trend-stat .stat-value.positive { color: #22c55e; }
.trend-stat .stat-value.negative { color: #ef4444; }

/* Codebase Stats Footer */
.codebase-stats {
  display: flex;
  justify-content: space-around;
  padding: 1.25rem;
  background: #12121a;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.stat-item .stat-icon {
  font-size: 1.5rem;
}

.stat-item .stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #fff;
}

.stat-item .stat-label {
  font-size: 0.75rem;
  color: #888;
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
  max-width: 700px;
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
  font-size: 1.1rem;
  color: #fff;
}

.btn-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: #888;
  font-size: 1.5rem;
  cursor: pointer;
}

.btn-close:hover {
  color: #fff;
}

.modal-body {
  padding: 1.5rem;
}

.drill-down-summary {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.drill-down-summary .summary-card {
  flex: 1;
  padding: 1rem;
  background: #1a1a2e;
  border-radius: 8px;
  text-align: center;
}

.drill-down-summary .card-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
}

.drill-down-summary .card-label {
  font-size: 0.75rem;
  color: #888;
}

.files-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.files-table th {
  text-align: left;
  padding: 0.75rem;
  background: #1a1a2e;
  color: #888;
  font-weight: 600;
}

.files-table td {
  padding: 0.75rem;
  border-bottom: 1px solid #1a1a2e;
  color: #ccc;
}

.file-path {
  font-family: monospace;
  color: #3b82f6;
}

.issues-count {
  font-weight: 600;
}

.score-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
}

.score-badge.excellent {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.score-badge.good {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.score-badge.warning {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.score-badge.critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.top-issue {
  color: #888;
  font-size: 0.75rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: 1rem 1.5rem;
  border-top: 1px solid #2a2a3e;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 6px;
  color: #e0e0e0;
  font-size: 0.875rem;
  cursor: pointer;
}

.btn-secondary:hover {
  background: #252540;
}
</style>
