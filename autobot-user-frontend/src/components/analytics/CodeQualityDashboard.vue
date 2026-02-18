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
          </div>
        </div>
      </div>
    </div>

    <!-- Health Score Hero Card -->
    <div class="health-hero">
      <div class="health-score-circle">
        <svg viewBox="0 0 120 120" class="score-ring">
          <circle cx="60" cy="60" r="54" fill="none" class="score-ring-bg" stroke-width="8" />
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
              <line v-for="i in 5" :key="'h' + i" :x1="50" :x2="780" :y1="i * 35 + 10" :y2="i * 35 + 10" class="grid-line" stroke-dasharray="2,2" />
            </g>

            <!-- Y-Axis -->
            <g class="y-axis">
              <text v-for="(label, i) in yAxisLabels" :key="'y' + i" :x="45" :y="i * 35 + 15" text-anchor="end" class="axis-label" font-size="10">
                {{ label }}
              </text>
            </g>

            <!-- Gradient Area -->
            <defs>
              <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" :stop-color="chartColors.info" stop-opacity="0.3" />
                <stop offset="100%" :stop-color="chartColors.info" stop-opacity="0" />
              </linearGradient>
            </defs>

            <!-- Area Fill -->
            <path v-if="trendAreaPath" :d="trendAreaPath" fill="url(#areaGradient)" />

            <!-- Line -->
            <path v-if="trendLinePath" :d="trendLinePath" fill="none" :stroke="chartColors.info" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

            <!-- Data Points -->
            <g class="data-points">
              <circle
                v-for="(point, i) in trendPoints"
                :key="'p' + i"
                :cx="point.x"
                :cy="point.y"
                r="4"
                :fill="chartColors.info"
                class="data-point-circle"
                stroke-width="2"
                @mouseenter="hoveredTrendPoint = point"
                @mouseleave="hoveredTrendPoint = null"
              />
            </g>

            <!-- Tooltip -->
            <g v-if="hoveredTrendPoint" class="tooltip">
              <rect :x="hoveredTrendPoint.x - 45" :y="hoveredTrendPoint.y - 50" width="90" height="40" rx="6" class="tooltip-bg" :stroke="chartColors.info" stroke-width="1" />
              <text :x="hoveredTrendPoint.x" :y="hoveredTrendPoint.y - 35" text-anchor="middle" class="tooltip-value" font-size="12" font-weight="600">
                {{ hoveredTrendPoint.score.toFixed(1) }}
              </text>
              <text :x="hoveredTrendPoint.x" :y="hoveredTrendPoint.y - 20" text-anchor="middle" class="tooltip-date" font-size="10">
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
                class="axis-label"
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
import { ref, computed, onMounted, onUnmounted, watch, reactive } from 'vue';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('CodeQualityDashboard');

// Helper to get CSS variable value for JavaScript usage (SVG, charts, etc.)
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

// Reactive chart colors that read from CSS variables
const chartColors = reactive({
  success: getCssVar('--color-success', '#22c55e'),
  warning: getCssVar('--color-warning', '#f59e0b'),
  orange: getCssVar('--chart-orange', '#f97316'),
  error: getCssVar('--color-error', '#ef4444'),
  info: getCssVar('--color-info', '#3b82f6'),
  bgPrimary: getCssVar('--bg-primary', '#0a0a0f'),
  bgSurface: getCssVar('--bg-surface', '#1a1a2e'),
  borderSubtle: getCssVar('--border-subtle', '#2a2a3e'),
  textPrimary: getCssVar('--text-primary', '#ffffff'),
  textMuted: getCssVar('--text-muted', '#888888'),
  textTertiary: getCssVar('--text-tertiary', '#666666'),
});

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

// Utility Functions - Using design tokens via getCssVar helper
function getScoreColor(score: number): string {
  if (score >= 80) return getCssVar('--color-success', '#22c55e');
  if (score >= 60) return getCssVar('--color-warning', '#eab308');
  if (score >= 40) return getCssVar('--chart-orange', '#f97316');
  return getCssVar('--color-error', '#ef4444');
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
  // Update chart colors after mount to ensure CSS variables are available
  chartColors.success = getCssVar('--color-success', '#22c55e');
  chartColors.warning = getCssVar('--color-warning', '#f59e0b');
  chartColors.orange = getCssVar('--chart-orange', '#f97316');
  chartColors.error = getCssVar('--color-error', '#ef4444');
  chartColors.info = getCssVar('--color-info', '#3b82f6');
  chartColors.bgPrimary = getCssVar('--bg-primary', '#0a0a0f');
  chartColors.bgSurface = getCssVar('--bg-surface', '#1a1a2e');
  chartColors.borderSubtle = getCssVar('--border-subtle', '#2a2a3e');
  chartColors.textPrimary = getCssVar('--text-primary', '#ffffff');
  chartColors.textMuted = getCssVar('--text-muted', '#888888');
  chartColors.textTertiary = getCssVar('--text-tertiary', '#666666');
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
/* Issue #704: Uses CSS design tokens via getCssVar() helper */
.code-quality-dashboard {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  min-height: 100vh;
  color: var(--text-primary);
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
}

.header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.dashboard-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.realtime-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--color-error-bg);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--color-error);
}

.realtime-status.connected {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
}

.btn-refresh,
.btn-export {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: var(--transition-all);
}

.btn-refresh {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--border-strong);
}

.btn-export {
  background: var(--color-info);
  border: none;
  color: var(--text-on-primary);
}

.btn-export:hover {
  background: var(--color-info-hover);
}

.export-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: var(--spacing-2);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
  z-index: var(--z-dropdown);
}

.dropdown-menu button {
  display: block;
  width: 100%;
  padding: var(--spacing-3) var(--spacing-4);
  background: transparent;
  border: none;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition: background var(--duration-200);
}

.dropdown-menu button:hover {
  background: var(--bg-tertiary);
}

/* Health Hero Card */
.health-hero {
  display: flex;
  align-items: center;
  gap: var(--spacing-8);
  padding: var(--spacing-8);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2xl);
  margin-bottom: var(--spacing-6);
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

.score-ring-bg {
  stroke: var(--border-subtle);
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
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  line-height: var(--leading-none);
}

.score-grade {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  margin-top: var(--spacing-1);
}

.grade-A { background: var(--color-success-bg); color: var(--color-success); }
.grade-B { background: var(--color-info-bg); color: var(--color-info); }
.grade-C { background: var(--color-warning-bg); color: var(--color-warning); }
.grade-D { background: var(--chart-orange-bg); color: var(--chart-orange); }
.grade-F { background: var(--color-error-bg); color: var(--color-error); }

.health-details {
  flex: 1;
}

.health-details h3 {
  margin: 0 0 var(--spacing-2);
  font-size: var(--text-xl);
  color: var(--text-primary);
}

.health-description {
  margin: 0 0 var(--spacing-3);
  color: var(--text-muted);
}

.trend-indicator {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-4);
}

.trend-indicator.positive {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.trend-indicator.negative {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.trend-indicator.neutral {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.recommendations h4 {
  margin: 0 0 var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.recommendations ul {
  margin: 0;
  padding-left: var(--spacing-5);
}

.recommendations li {
  font-size: var(--text-sm);
  color: var(--text-muted);
  margin-bottom: var(--spacing-1);
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  padding: var(--spacing-4);
  cursor: pointer;
  transition: var(--transition-all);
}

.metric-card:hover {
  border-color: var(--color-info);
  transform: translateY(-2px);
}

.metric-card.low-score {
  border-color: var(--color-error-border);
}

.metric-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-3);
}

.metric-icon {
  font-size: var(--text-xl);
}

.metric-name {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.metric-body {
  margin-bottom: var(--spacing-2);
}

.metric-score {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.score-number {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.metric-bar {
  height: 4px;
  background: var(--border-subtle);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.metric-bar .bar-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.5s ease;
}

.bar-fill.excellent { background: var(--color-success); }
.bar-fill.good { background: var(--color-info); }
.bar-fill.warning { background: var(--color-warning); }
.bar-fill.critical { background: var(--color-error); }

.metric-footer {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.metric-trend.positive { color: var(--color-success); }
.metric-trend.negative { color: var(--color-error); }

/* Panels */
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

.panel {
  background: var(--bg-card);
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

.panel-content {
  padding: var(--spacing-5);
}

.severity-filter {
  display: flex;
  gap: var(--spacing-1);
}

.severity-filter button {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  color: var(--text-muted);
  font-size: var(--text-xs);
  text-transform: capitalize;
  cursor: pointer;
  transition: var(--transition-all);
}

.severity-filter button.active {
  background: var(--color-info);
  border-color: var(--color-info);
  color: var(--text-on-primary);
}

/* Patterns */
.patterns-chart {
  margin-bottom: var(--spacing-4);
}

.pattern-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-2) 0;
  border-bottom: 1px solid var(--bg-surface);
}

.pattern-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  min-width: 150px;
}

.pattern-icon {
  font-size: var(--text-sm);
}

.pattern-name {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.pattern-value {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.bar-container {
  flex: 1;
  height: 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.bar-container .bar {
  height: 100%;
  border-radius: var(--radius-default);
  transition: width var(--duration-300);
}

.bar.severity-critical { background: var(--color-error); }
.bar.severity-high { background: var(--chart-orange); }
.bar.severity-medium { background: var(--color-warning); }
.bar.severity-low { background: var(--color-success); }
.bar.severity-info { background: var(--color-info); }

.count {
  min-width: 30px;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  text-align: right;
}

.patterns-summary {
  display: flex;
  gap: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.summary-stat {
  flex: 1;
  text-align: center;
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
}

.summary-stat.critical { background: var(--color-error-bg); }
.summary-stat.high { background: var(--chart-orange-bg); }
.summary-stat.medium { background: var(--color-warning-bg); }
.summary-stat.info { background: var(--color-info-bg); }

.summary-stat .stat-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.summary-stat .stat-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
}

/* Complexity */
.complexity-stats {
  display: flex;
  gap: var(--spacing-4);
}

.complexity-stats .stat {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.complexity-stats strong {
  color: var(--text-primary);
}

.complexity-stats .warning {
  color: var(--color-error);
}

.hotspots-list {
  margin-bottom: var(--spacing-4);
}

.hotspot-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-2);
}

.hotspot-item.critical-complexity {
  border-left: 3px solid var(--color-error);
}

.hotspot-rank {
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

.hotspot-info {
  flex: 1;
}

.hotspot-file {
  display: block;
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  color: var(--color-info);
}

.hotspot-lines {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.complexity-badge {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.complexity-badge.safe {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.complexity-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.complexity-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.complexity-thresholds {
  display: flex;
  justify-content: center;
  gap: var(--spacing-6);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.threshold-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.threshold-color {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-xs);
}

.threshold-color.safe { background: var(--color-success); }
.threshold-color.warning { background: var(--color-warning); }
.threshold-color.critical { background: var(--color-error); }

/* Trends Panel */
.trends-panel {
  margin-bottom: var(--spacing-6);
}

.period-selector {
  display: flex;
  gap: var(--spacing-1);
}

.period-selector button {
  padding: var(--spacing-1-5) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  color: var(--text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: var(--transition-all);
}

.period-selector button.active {
  background: var(--color-info);
  border-color: var(--color-info);
  color: var(--text-on-primary);
}

.trends-chart {
  margin-bottom: var(--spacing-4);
}

.line-chart {
  width: 100%;
  height: 200px;
}

/* SVG Chart Styles */
.grid-line {
  stroke: var(--border-subtle);
}

.axis-label {
  fill: var(--text-tertiary);
}

.data-point-circle {
  stroke: var(--bg-primary);
  cursor: pointer;
  transition: r var(--duration-200);
}

.data-point-circle:hover {
  r: 6;
}

.tooltip-bg {
  fill: var(--bg-surface);
}

.tooltip-value {
  fill: var(--text-primary);
}

.tooltip-date {
  fill: var(--text-muted);
}

.trend-stats {
  display: flex;
  gap: var(--spacing-8);
  padding: var(--spacing-4);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
}

.trend-stat {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.trend-stat .stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.trend-stat .stat-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.trend-stat .stat-value.positive { color: var(--color-success); }
.trend-stat .stat-value.negative { color: var(--color-error); }

/* Codebase Stats Footer */
.codebase-stats {
  display: flex;
  justify-content: space-around;
  padding: var(--spacing-5);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
}

.stat-item .stat-icon {
  font-size: var(--text-2xl);
}

.stat-item .stat-value {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-item .stat-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
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
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 700px;
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
  font-size: var(--text-lg);
  color: var(--text-primary);
}

.btn-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: var(--text-2xl);
  cursor: pointer;
}

.btn-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-6);
}

.drill-down-summary {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.drill-down-summary .summary-card {
  flex: 1;
  padding: var(--spacing-4);
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  text-align: center;
}

.drill-down-summary .card-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.drill-down-summary .card-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.files-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.files-table th {
  text-align: left;
  padding: var(--spacing-3);
  background: var(--bg-surface);
  color: var(--text-muted);
  font-weight: var(--font-semibold);
}

.files-table td {
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--bg-surface);
  color: var(--text-secondary);
}

.file-path {
  font-family: var(--font-mono);
  color: var(--color-info);
}

.issues-count {
  font-weight: var(--font-semibold);
}

.score-badge {
  display: inline-block;
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-weight: var(--font-semibold);
}

.score-badge.excellent {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.score-badge.good {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.score-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.score-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.top-issue {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: var(--spacing-4) var(--spacing-6);
  border-top: 1px solid var(--border-subtle);
}

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
}
</style>
