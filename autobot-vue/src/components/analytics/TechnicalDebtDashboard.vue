<template>
  <div class="technical-debt-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2 class="dashboard-title">Technical Debt Dashboard</h2>
        <p class="dashboard-subtitle">Track, prioritize, and manage technical debt across the codebase</p>
      </div>
      <div class="header-actions">
        <button class="btn-refresh" @click="refreshData" :disabled="loading">
          <span class="icon">↻</span>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <button class="btn-export" @click="exportReport">
          <span class="icon">↓</span>
          Export Report
        </button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="summary-cards">
      <div class="summary-card total-debt">
        <div class="card-icon">⚠️</div>
        <div class="card-content">
          <span class="card-value">{{ summary.total_items }}</span>
          <span class="card-label">Total Debt Items</span>
        </div>
        <div class="card-trend" :class="getTrendClass(summary.trend)">
          {{ formatTrend(summary.trend) }}
        </div>
      </div>

      <div class="summary-card estimated-hours">
        <div class="card-icon">⏱️</div>
        <div class="card-content">
          <span class="card-value">{{ formatHours(summary.total_hours) }}</span>
          <span class="card-label">Estimated Hours</span>
        </div>
        <div class="card-cost">${{ formatCost(summary.estimated_cost) }}</div>
      </div>

      <div class="summary-card critical-items">
        <div class="card-icon">🔴</div>
        <div class="card-content">
          <span class="card-value">{{ summary.critical_count }}</span>
          <span class="card-label">Critical Items</span>
        </div>
        <div class="card-priority">Needs Immediate Attention</div>
      </div>

      <div class="summary-card health-score">
        <div class="card-icon">💚</div>
        <div class="card-content">
          <span class="card-value">{{ summary.health_score }}%</span>
          <span class="card-label">Debt Health Score</span>
        </div>
        <div class="health-bar">
          <div class="health-fill" :style="{ width: summary.health_score + '%' }" :class="getHealthClass(summary.health_score)"></div>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid">
      <!-- Category Breakdown -->
      <div class="panel category-panel">
        <div class="panel-header">
          <h3>Debt by Category</h3>
          <div class="view-toggle">
            <button :class="{ active: categoryView === 'chart' }" @click="categoryView = 'chart'">Chart</button>
            <button :class="{ active: categoryView === 'list' }" @click="categoryView = 'list'">List</button>
          </div>
        </div>
        <div class="panel-content">
          <!-- SVG Donut Chart -->
          <div v-if="categoryView === 'chart'" class="category-chart">
            <svg viewBox="0 0 200 200" class="donut-chart">
              <g transform="translate(100, 100)">
                <circle r="70" fill="none" class="donut-bg" stroke-width="30" />
                <circle
                  v-for="(segment, index) in categorySegments"
                  :key="segment.category"
                  r="70"
                  fill="none"
                  :stroke="segment.color"
                  stroke-width="30"
                  :stroke-dasharray="segment.dashArray"
                  :stroke-dashoffset="segment.offset"
                  :transform="`rotate(${segment.rotation})`"
                  class="donut-segment"
                  @mouseenter="hoveredCategory = segment.category"
                  @mouseleave="hoveredCategory = null"
                />
                <text class="center-value donut-text-primary" text-anchor="middle" dy="0.1em" font-size="24">
                  {{ summary.total_items }}
                </text>
                <text class="center-label donut-text-secondary" text-anchor="middle" dy="1.5em" font-size="10">
                  Total Items
                </text>
              </g>
            </svg>
            <div class="chart-legend">
              <div
                v-for="segment in categorySegments"
                :key="segment.category"
                class="legend-item"
                :class="{ highlighted: hoveredCategory === segment.category }"
              >
                <span class="legend-color" :style="{ backgroundColor: segment.color }"></span>
                <span class="legend-label">{{ formatCategoryName(segment.category) }}</span>
                <span class="legend-value">{{ segment.count }}</span>
              </div>
            </div>
          </div>

          <!-- Category List View -->
          <div v-else class="category-list">
            <div
              v-for="category in categoryBreakdown"
              :key="category.category"
              class="category-item"
              @click="selectCategory(category.category)"
            >
              <div class="category-header">
                <span class="category-icon">{{ getCategoryIcon(category.category) }}</span>
                <span class="category-name">{{ formatCategoryName(category.category) }}</span>
              </div>
              <div class="category-stats">
                <span class="stat-count">{{ category.count }} items</span>
                <span class="stat-hours">{{ formatHours(category.total_hours) }}h</span>
                <span class="stat-severity" :class="category.avg_severity">
                  {{ category.avg_severity }}
                </span>
              </div>
              <div class="category-bar">
                <div
                  class="bar-fill"
                  :style="{ width: (category.count / summary.total_items * 100) + '%' }"
                  :class="getCategoryClass(category.category)"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ROI Priorities -->
      <div class="panel priorities-panel">
        <div class="panel-header">
          <h3>🎯 Quick Wins (Best ROI)</h3>
          <span class="panel-info">High impact, low effort items</span>
        </div>
        <div class="panel-content">
          <div v-if="roiPriorities.length === 0" class="empty-state">
            <span class="empty-icon">✨</span>
            <span class="empty-text">No quick wins available</span>
          </div>
          <div v-else class="priority-list">
            <div
              v-for="(item, index) in roiPriorities.slice(0, 10)"
              :key="item.id"
              class="priority-item"
              :class="{ 'top-priority': index < 3 }"
            >
              <div class="priority-rank">{{ index + 1 }}</div>
              <div class="priority-content">
                <div class="priority-header">
                  <span class="priority-file">{{ truncatePath(item.file_path) }}</span>
                  <span class="priority-category" :class="item.category">
                    {{ formatCategoryName(item.category) }}
                  </span>
                </div>
                <div class="priority-description">{{ item.description }}</div>
                <div class="priority-metrics">
                  <span class="metric roi">
                    <strong>ROI:</strong> {{ item.roi_score.toFixed(1) }}
                  </span>
                  <span class="metric impact">
                    <strong>Impact:</strong> {{ item.impact_score }}/10
                  </span>
                  <span class="metric effort">
                    <strong>Effort:</strong> {{ item.estimated_hours }}h
                  </span>
                </div>
              </div>
              <div class="priority-action">
                <button class="btn-fix" @click="showFixDetails(item)">Fix</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Trends Section -->
    <div class="panel trends-panel">
      <div class="panel-header">
        <h3>📈 Debt Trends</h3>
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
          <svg viewBox="0 0 800 200" class="line-chart" preserveAspectRatio="xMidYMid meet">
            <!-- Grid Lines -->
            <g class="grid-lines">
              <line v-for="i in 5" :key="'h' + i" :x1="50" :x2="780" :y1="i * 35 + 10" :y2="i * 35 + 10" class="chart-grid-line" stroke-dasharray="2,2" />
            </g>

            <!-- Y-Axis Labels -->
            <g class="y-axis">
              <text v-for="(label, i) in yAxisLabels" :key="'y' + i" :x="45" :y="i * 35 + 15" text-anchor="end" class="chart-axis-label" font-size="10">
                {{ label }}
              </text>
            </g>

            <!-- X-Axis Labels -->
            <g class="x-axis">
              <text
                v-for="(point, i) in trendData.slice(0, 10)"
                :key="'x' + i"
                :x="50 + i * 73"
                y="195"
                text-anchor="middle"
                class="chart-axis-label"
                font-size="9"
              >
                {{ formatTrendDate(point.date) }}
              </text>
            </g>

            <!-- Trend Line -->
            <path v-if="trendLinePath" :d="trendLinePath" fill="none" class="chart-trend-stroke" stroke-width="2" />

            <!-- Data Points -->
            <g class="data-points">
              <circle
                v-for="(point, i) in trendPoints"
                :key="'p' + i"
                :cx="point.x"
                :cy="point.y"
                r="4"
                class="data-point chart-data-point"
                @mouseenter="hoveredPoint = point"
                @mouseleave="hoveredPoint = null"
              />
            </g>

            <!-- Tooltip -->
            <g v-if="hoveredPoint" class="tooltip">
              <rect :x="hoveredPoint.x - 40" :y="hoveredPoint.y - 45" width="80" height="35" rx="4" class="chart-tooltip-bg" />
              <text :x="hoveredPoint.x" :y="hoveredPoint.y - 32" text-anchor="middle" class="chart-tooltip-text-primary" font-size="11">
                {{ hoveredPoint.count }} items
              </text>
              <text :x="hoveredPoint.x" :y="hoveredPoint.y - 18" text-anchor="middle" class="chart-tooltip-text-secondary" font-size="9">
                {{ hoveredPoint.date }}
              </text>
            </g>
          </svg>
        </div>

        <!-- Trend Summary -->
        <div class="trend-summary">
          <div class="trend-stat">
            <span class="stat-label">Period Change</span>
            <span class="stat-value" :class="getTrendClass(trendSummary.change)">
              {{ formatTrendChange(trendSummary.change) }}
            </span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Average Items</span>
            <span class="stat-value">{{ trendSummary.average }}</span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Peak</span>
            <span class="stat-value">{{ trendSummary.peak }}</span>
          </div>
          <div class="trend-stat">
            <span class="stat-label">Current</span>
            <span class="stat-value">{{ trendSummary.current }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detailed Debt Table -->
    <div class="panel table-panel">
      <div class="panel-header">
        <h3>📋 Debt Inventory</h3>
        <div class="table-filters">
          <select v-model="filterCategory" @change="applyFilters">
            <option value="">All Categories</option>
            <option v-for="cat in availableCategories" :key="cat" :value="cat">
              {{ formatCategoryName(cat) }}
            </option>
          </select>
          <select v-model="filterSeverity" @change="applyFilters">
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search files..."
            @input="applyFilters"
          />
        </div>
      </div>
      <div class="panel-content">
        <div class="debt-table-container">
          <table class="debt-table">
            <thead>
              <tr>
                <th @click="sortBy('severity')">Severity</th>
                <th @click="sortBy('category')">Category</th>
                <th @click="sortBy('file_path')">File</th>
                <th>Description</th>
                <th @click="sortBy('estimated_hours')">Est. Hours</th>
                <th @click="sortBy('roi_score')">ROI</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in paginatedDebtItems" :key="item.id" :class="'severity-' + item.severity">
                <td>
                  <span class="severity-badge" :class="item.severity">
                    {{ item.severity }}
                  </span>
                </td>
                <td>
                  <span class="category-badge" :class="item.category">
                    {{ getCategoryIcon(item.category) }} {{ formatCategoryName(item.category) }}
                  </span>
                </td>
                <td class="file-cell" :title="item.file_path">
                  {{ truncatePath(item.file_path) }}
                  <span v-if="item.line_number" class="line-number">:{{ item.line_number }}</span>
                </td>
                <td class="description-cell">{{ item.description }}</td>
                <td class="hours-cell">{{ item.estimated_hours }}h</td>
                <td class="roi-cell">
                  <span class="roi-badge" :class="getRoiClass(item.roi_score)">
                    {{ item.roi_score.toFixed(1) }}
                  </span>
                </td>
                <td class="actions-cell">
                  <button class="btn-view" @click="showItemDetails(item)">View</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="pagination">
          <button :disabled="currentPage === 1" @click="currentPage--">Previous</button>
          <span class="page-info">Page {{ currentPage }} of {{ totalPages }}</span>
          <button :disabled="currentPage === totalPages" @click="currentPage++">Next</button>
        </div>
      </div>
    </div>

    <!-- Item Details Modal -->
    <div v-if="selectedItem" class="modal-overlay" @click.self="selectedItem = null">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Debt Item Details</h3>
          <button class="btn-close" @click="selectedItem = null">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-row">
            <span class="detail-label">File:</span>
            <span class="detail-value file-path">{{ selectedItem.file_path }}</span>
          </div>
          <div v-if="selectedItem.line_number" class="detail-row">
            <span class="detail-label">Line:</span>
            <span class="detail-value">{{ selectedItem.line_number }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Category:</span>
            <span class="detail-value category-badge" :class="selectedItem.category">
              {{ formatCategoryName(selectedItem.category) }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Severity:</span>
            <span class="detail-value severity-badge" :class="selectedItem.severity">
              {{ selectedItem.severity }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Description:</span>
            <span class="detail-value">{{ selectedItem.description }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Estimated Hours:</span>
            <span class="detail-value">{{ selectedItem.estimated_hours }}h</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Impact Score:</span>
            <span class="detail-value">{{ selectedItem.impact_score }}/10</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">ROI Score:</span>
            <span class="detail-value roi-badge" :class="getRoiClass(selectedItem.roi_score)">
              {{ selectedItem.roi_score.toFixed(2) }}
            </span>
          </div>
          <div v-if="selectedItem.suggested_fix" class="detail-row full-width">
            <span class="detail-label">Suggested Fix:</span>
            <pre class="suggested-fix">{{ selectedItem.suggested_fix }}</pre>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="selectedItem = null">Close</button>
          <button class="btn-primary" @click="navigateToFile(selectedItem)">Open in Editor</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for TechnicalDebtDashboard
const logger = createLogger('TechnicalDebtDashboard');

// Types
interface DebtItem {
  id: string;
  file_path: string;
  line_number?: number;
  category: string;
  severity: string;
  description: string;
  estimated_hours: number;
  impact_score: number;
  roi_score: number;
  suggested_fix?: string;
  created_at: string;
}

interface CategoryBreakdown {
  category: string;
  count: number;
  total_hours: number;
  avg_severity: string;
}

interface TrendPoint {
  date: string;
  total_items: number;
  total_hours: number;
  by_category: Record<string, number>;
}

interface Summary {
  total_items: number;
  total_hours: number;
  estimated_cost: number;
  critical_count: number;
  health_score: number;
  trend: number;
}

// State
const loading = ref(false);
const loadError = ref<string | null>(null);
const summary = ref<Summary>({
  total_items: 0,
  total_hours: 0,
  estimated_cost: 0,
  critical_count: 0,
  health_score: 100,
  trend: 0,
});
const categoryBreakdown = ref<CategoryBreakdown[]>([]);
const roiPriorities = ref<DebtItem[]>([]);
const allDebtItems = ref<DebtItem[]>([]);
const trendData = ref<TrendPoint[]>([]);

// UI State
const categoryView = ref<'chart' | 'list'>('chart');
const selectedPeriod = ref('30d');
const hoveredCategory = ref<string | null>(null);
const hoveredPoint = ref<{ x: number; y: number; count: number; date: string } | null>(null);
const selectedItem = ref<DebtItem | null>(null);

// Filters
const filterCategory = ref('');
const filterSeverity = ref('');
const searchQuery = ref('');
const sortField = ref('roi_score');
const sortDirection = ref<'asc' | 'desc'>('desc');
const currentPage = ref(1);
const itemsPerPage = 10;

/**
 * Issue #704: Helper to read CSS custom properties from design tokens
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/**
 * Issue #704: Category colors using design tokens
 * These map debt categories to our chart color palette
 */
const getCategoryColors = (): Record<string, string> => ({
  code_complexity: getCssVar('--color-error', '#ef4444'),
  code_duplication: getCssVar('--chart-orange', '#f97316'),
  missing_tests: getCssVar('--color-warning', '#eab308'),
  missing_docs: getCssVar('--chart-green', '#84cc16'),
  anti_patterns: getCssVar('--color-success', '#22c55e'),
  security_issues: getCssVar('--chart-teal', '#14b8a6'),
  performance_issues: getCssVar('--chart-cyan', '#06b6d4'),
  outdated_dependencies: getCssVar('--chart-blue', '#3b82f6'),
  hardcoded_values: getCssVar('--chart-purple', '#8b5cf6'),
  dead_code: getCssVar('--chart-pink', '#a855f7'),
})

// Category colors - computed on access to get current theme values
const categoryColors = getCategoryColors();

// Category icons
const categoryIcons: Record<string, string> = {
  code_complexity: '🔄',
  code_duplication: '📋',
  missing_tests: '🧪',
  missing_docs: '📝',
  anti_patterns: '⚠️',
  security_issues: '🔒',
  performance_issues: '⚡',
  outdated_dependencies: '📦',
  hardcoded_values: '🔢',
  dead_code: '💀',
};

// Computed
const availableCategories = computed(() => {
  return [...new Set(allDebtItems.value.map(item => item.category))];
});

const filteredDebtItems = computed(() => {
  let items = [...allDebtItems.value];

  if (filterCategory.value) {
    items = items.filter(item => item.category === filterCategory.value);
  }

  if (filterSeverity.value) {
    items = items.filter(item => item.severity === filterSeverity.value);
  }

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    items = items.filter(
      item =>
        item.file_path.toLowerCase().includes(query) ||
        item.description.toLowerCase().includes(query)
    );
  }

  // Sort
  items.sort((a, b) => {
    const aVal = a[sortField.value as keyof DebtItem];
    const bVal = b[sortField.value as keyof DebtItem];
    const direction = sortDirection.value === 'asc' ? 1 : -1;

    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return (aVal - bVal) * direction;
    }
    return String(aVal).localeCompare(String(bVal)) * direction;
  });

  return items;
});

const totalPages = computed(() => {
  return Math.ceil(filteredDebtItems.value.length / itemsPerPage) || 1;
});

const paginatedDebtItems = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage;
  return filteredDebtItems.value.slice(start, start + itemsPerPage);
});

const categorySegments = computed(() => {
  if (categoryBreakdown.value.length === 0) return [];

  const total = categoryBreakdown.value.reduce((sum, cat) => sum + cat.count, 0);
  const circumference = 2 * Math.PI * 70;
  let offset = 0;

  return categoryBreakdown.value.map(cat => {
    const percentage = cat.count / total;
    const dashLength = percentage * circumference;
    const segment = {
      category: cat.category,
      count: cat.count,
      percentage: percentage * 100,
      color: categoryColors[cat.category] || getCssVar('--text-muted', '#666'),
      dashArray: `${dashLength} ${circumference - dashLength}`,
      offset: -offset,
      rotation: -90,
    };
    offset += dashLength;
    return segment;
  });
});

const yAxisLabels = computed(() => {
  if (trendData.value.length === 0) return ['0', '0', '0', '0', '0'];
  const max = Math.max(...trendData.value.map(p => p.total_items));
  return [max, Math.round(max * 0.75), Math.round(max * 0.5), Math.round(max * 0.25), 0].map(String);
});

const trendPoints = computed(() => {
  if (trendData.value.length === 0) return [];

  const max = Math.max(...trendData.value.map(p => p.total_items)) || 1;
  const chartWidth = 730;
  const chartHeight = 140;
  const startX = 50;

  return trendData.value.slice(0, 10).map((point, i) => ({
    x: startX + (i / Math.max(trendData.value.length - 1, 1)) * chartWidth,
    y: 10 + chartHeight - (point.total_items / max) * chartHeight,
    count: point.total_items,
    date: point.date,
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

const trendSummary = computed(() => {
  if (trendData.value.length === 0) {
    return { change: 0, average: 0, peak: 0, current: 0 };
  }

  const values = trendData.value.map(p => p.total_items);
  const current = values[values.length - 1] || 0;
  const first = values[0] || 0;
  const change = first > 0 ? ((current - first) / first) * 100 : 0;

  return {
    change,
    average: Math.round(values.reduce((a, b) => a + b, 0) / values.length),
    peak: Math.max(...values),
    current,
  };
});

// Methods
async function refreshData(): Promise<void> {
  loading.value = true;
  try {
    await Promise.all([loadSummary(), loadCategoryBreakdown(), loadRoiPriorities(), loadDebtItems(), loadTrends()]);
  } catch (error) {
    logger.error('Failed to load debt data:', error);
  } finally {
    loading.value = false;
  }
}

async function loadSummary(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/debt/* not /api/analytics/debt/*
    // Backend returns {status, summary: {...}, top_files: [...], ...}
    const response = await fetch('/api/debt/summary');
    if (response.ok) {
      const result = await response.json();
      // Issue #552: Extract summary from response structure
      summary.value = result.summary || result;
      loadError.value = null;
    } else {
      logger.warn('Failed to load summary: HTTP', response.status);
      loadError.value = `Failed to load summary (HTTP ${response.status})`;
    }
  } catch (error) {
    logger.error('Failed to load summary:', error);
    loadError.value = 'Failed to connect to analytics API';
  }
}

async function loadCategoryBreakdown(): Promise<void> {
  try {
    // Issue #552: Fixed - backend uses POST for calculate, GET for summary
    // Backend returns {status, summary: {by_category: {...}, ...}, ...}
    const response = await fetch('/api/debt/summary');
    if (response.ok) {
      const result = await response.json();
      // Issue #552: Extract by_category from nested summary structure
      categoryBreakdown.value = result.summary?.by_category || result.by_category || [];
    } else {
      logger.warn('Failed to load category breakdown: HTTP', response.status);
      categoryBreakdown.value = [];
    }
  } catch (error) {
    logger.error('Failed to load category breakdown:', error);
    categoryBreakdown.value = [];
  }
}

async function loadRoiPriorities(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/debt/* not /api/analytics/debt/*
    // Backend returns {status, priorities: [...], total_available: N}
    const response = await fetch('/api/debt/roi-priorities?limit=10');
    if (response.ok) {
      const result = await response.json();
      // Issue #552: Extract priorities from response structure
      roiPriorities.value = result.priorities || result;
    } else {
      logger.warn('Failed to load ROI priorities: HTTP', response.status);
      roiPriorities.value = [];
    }
  } catch (error) {
    logger.error('Failed to load ROI priorities:', error);
    roiPriorities.value = [];
  }
}

async function loadDebtItems(): Promise<void> {
  try {
    // Issue #552: Fixed - backend uses POST for /api/debt/calculate
    // Backend returns {status, data: {items, summary, ...}} structure
    const response = await fetch('/api/debt/calculate', { method: 'POST' });
    if (response.ok) {
      const result = await response.json();
      // Issue #552: Access items from nested data structure
      allDebtItems.value = result.data?.items || result.items || [];
    } else {
      logger.warn('Failed to load debt items: HTTP', response.status);
      allDebtItems.value = [];
    }
  } catch (error) {
    logger.error('Failed to load debt items:', error);
    allDebtItems.value = [];
  }
}

async function loadTrends(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/debt/* not /api/analytics/debt/*
    // Backend returns {status, trends: [...], data_points: N, change: {...}, direction: "..."}
    const response = await fetch(`/api/debt/trends?period=${selectedPeriod.value}`);
    if (response.ok) {
      const result = await response.json();
      // Issue #552: Extract trends from response structure
      trendData.value = result.trends || result;
    } else {
      logger.warn('Failed to load trends: HTTP', response.status);
      trendData.value = [];
    }
  } catch (error) {
    logger.error('Failed to load trends:', error);
    trendData.value = [];
  }
}

async function exportReport(): Promise<void> {
  try {
    // Issue #552: Fixed path - backend uses /api/debt/* not /api/analytics/debt/*
    // Backend returns {status, format, report: "markdown content"} for markdown format
    const response = await fetch('/api/debt/report?format=markdown');
    if (response.ok) {
      const result = await response.json();
      // Issue #552: Extract markdown report from JSON response
      const markdownContent = result.report || '';
      const blob = new Blob([markdownContent], { type: 'text/markdown' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `technical-debt-report-${new Date().toISOString().split('T')[0]}.md`;
      a.click();
      window.URL.revokeObjectURL(url);
    }
  } catch (error) {
    logger.error('Failed to export report:', error);
  }
}

function selectCategory(category: string): void {
  filterCategory.value = category;
  currentPage.value = 1;
}

function showItemDetails(item: DebtItem): void {
  selectedItem.value = item;
}

function showFixDetails(item: DebtItem): void {
  selectedItem.value = item;
}

function navigateToFile(item: DebtItem): void {
  // Emit event for parent to handle file navigation
  // Issue #701: Fixed logger.debug call - use object for context
  logger.debug('Navigate to:', { filePath: item.file_path, lineNumber: item.line_number });
  selectedItem.value = null;
}

function applyFilters(): void {
  currentPage.value = 1;
}

function sortBy(field: string): void {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortField.value = field;
    sortDirection.value = 'desc';
  }
}

// Formatters
function formatCategoryName(category: string): string {
  return category
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function getCategoryIcon(category: string): string {
  return categoryIcons[category] || '📌';
}

function getCategoryClass(category: string): string {
  return category.replace(/_/g, '-');
}

function formatHours(hours: number): string {
  if (hours >= 40) {
    return `${(hours / 40).toFixed(1)}w`;
  }
  return hours.toFixed(1);
}

function formatCost(cost: number): string {
  if (cost >= 1000) {
    return `${(cost / 1000).toFixed(1)}k`;
  }
  return cost.toFixed(0);
}

function formatTrend(trend: number): string {
  const prefix = trend > 0 ? '+' : '';
  return `${prefix}${trend.toFixed(1)}%`;
}

function formatTrendChange(change: number): string {
  const prefix = change > 0 ? '+' : '';
  return `${prefix}${change.toFixed(1)}%`;
}

function formatTrendDate(dateStr: string): string {
  const date = new Date(dateStr);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function getTrendClass(trend: number): string {
  if (trend < 0) return 'positive';
  if (trend > 0) return 'negative';
  return 'neutral';
}

function getHealthClass(score: number): string {
  if (score >= 80) return 'healthy';
  if (score >= 60) return 'moderate';
  if (score >= 40) return 'warning';
  return 'critical';
}

function getRoiClass(roi: number): string {
  if (roi >= 5) return 'excellent';
  if (roi >= 3) return 'good';
  if (roi >= 1) return 'moderate';
  return 'low';
}

function truncatePath(path: string): string {
  if (path.length <= 40) return path;
  const parts = path.split('/');
  if (parts.length <= 2) return path;
  return `.../${parts.slice(-2).join('/')}`;
}

// Lifecycle
onMounted(() => {
  refreshData();
});

// Watch for period changes
watch(selectedPeriod, () => {
  loadTrends();
});
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */
.technical-debt-dashboard {
  padding: var(--spacing-lg);
  background: var(--bg-primary);
  min-height: 100vh;
  color: var(--text-primary);
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
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
  gap: var(--spacing-sm);
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
  transition: all var(--duration-200);
}

.btn-refresh {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--border-strong);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-export {
  background: var(--color-primary);
  border: none;
  color: var(--text-on-primary);
}

.btn-export:hover {
  background: var(--color-primary-hover);
}

.icon {
  font-size: var(--text-base);
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.summary-card {
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
}

.card-icon {
  font-size: var(--text-2xl);
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
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-top: var(--spacing-xs);
}

.card-trend {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
}

.card-trend.positive {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.card-trend.negative {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.card-trend.neutral {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.card-cost {
  font-size: var(--text-sm);
  color: var(--color-warning);
  font-weight: var(--font-semibold);
}

.card-priority {
  font-size: var(--text-xs);
  color: var(--color-error);
}

.health-bar {
  width: 100%;
  height: 6px;
  background: var(--border-subtle);
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin-top: var(--spacing-sm);
}

.health-fill {
  height: 100%;
  transition: width var(--duration-300) ease;
}

.health-fill.healthy {
  background: var(--color-success);
}

.health-fill.moderate {
  background: var(--color-warning);
}

.health-fill.warning {
  background: var(--chart-orange);
}

.health-fill.critical {
  background: var(--color-error);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

@media (max-width: 1200px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}

/* Panels */
.panel {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.panel-info {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.panel-content {
  padding: var(--spacing-lg);
}

.view-toggle {
  display: flex;
  gap: var(--spacing-xs);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-xs);
}

.view-toggle button {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-150);
}

.view-toggle button.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

/* Category Chart */
.category-chart {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-lg);
}

.donut-chart {
  width: 180px;
  height: 180px;
  flex-shrink: 0;
}

.donut-segment {
  transition: opacity var(--duration-150);
  cursor: pointer;
}

.donut-segment:hover {
  opacity: 0.8;
}

.center-value {
  font-weight: var(--font-bold);
}

.center-label {
  text-transform: uppercase;
}

/* Issue #704: SVG styling using CSS variables */
.donut-bg {
  stroke: var(--border-subtle);
}

.donut-text-primary {
  fill: var(--text-primary);
}

.donut-text-secondary {
  fill: var(--text-tertiary);
}

/* Chart grid and axes */
.chart-grid-line {
  stroke: var(--border-default);
}

.chart-axis-label {
  fill: var(--text-tertiary);
}

/* Trend line and data points */
.chart-trend-stroke {
  stroke: var(--color-primary);
}

.chart-data-point {
  fill: var(--color-primary);
}

/* Chart tooltip */
.chart-tooltip-bg {
  fill: var(--bg-secondary);
}

.chart-tooltip-text-primary {
  fill: var(--text-primary);
}

.chart-tooltip-text-secondary {
  fill: var(--text-tertiary);
}

.chart-legend {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: background var(--duration-150);
}

.legend-item.highlighted {
  background: var(--bg-hover);
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.legend-label {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.legend-value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

/* Category List */
.category-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.category-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  cursor: pointer;
  transition: all var(--duration-150);
}

.category-item:hover {
  border-color: var(--color-primary);
  background: var(--bg-hover);
}

.category-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.category-icon {
  font-size: var(--text-base);
}

.category-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.category-stats {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--text-xs);
  margin-bottom: var(--spacing-sm);
}

.stat-count {
  color: var(--text-tertiary);
}

.stat-hours {
  color: var(--color-warning);
}

.stat-severity {
  padding: 0.125rem var(--spacing-xs);
  border-radius: var(--radius-sm);
  text-transform: uppercase;
  font-size: 0.65rem;
  font-weight: var(--font-semibold);
}

.stat-severity.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stat-severity.high {
  background: var(--chart-orange-bg);
  color: var(--chart-orange);
}

.stat-severity.medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.stat-severity.low {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.category-bar {
  height: 4px;
  background: var(--border-subtle);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width var(--duration-200) ease;
}

/* Priority List */
.priority-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  max-height: 400px;
  overflow-y: auto;
}

.priority-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

.priority-item.top-priority {
  border-color: var(--color-primary);
  background: linear-gradient(135deg, var(--color-primary-bg) 0%, var(--bg-secondary) 100%);
}

.priority-rank {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border-subtle);
  border-radius: 50%;
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  flex-shrink: 0;
}

.top-priority .priority-rank {
  background: var(--color-primary);
}

.priority-content {
  flex: 1;
  min-width: 0;
}

.priority-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
}

.priority-file {
  font-size: var(--text-sm);
  color: var(--color-primary);
  font-family: var(--font-mono);
}

.priority-category {
  font-size: 0.65rem;
  padding: 0.125rem var(--spacing-xs);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.priority-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-sm);
}

.priority-metrics {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--text-xs);
}

.metric {
  color: var(--text-tertiary);
}

.metric strong {
  color: var(--text-muted);
}

.metric.roi {
  color: var(--color-success);
}

.priority-action {
  flex-shrink: 0;
}

.btn-fix {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-success);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-on-success);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: background var(--duration-150);
}

.btn-fix:hover {
  background: var(--color-success-dark);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  color: var(--text-muted);
}

.empty-icon {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-sm);
}

.empty-text {
  font-size: var(--text-sm);
}

/* Trends Panel */
.trends-panel {
  margin-bottom: var(--spacing-lg);
}

.period-selector {
  display: flex;
  gap: var(--spacing-xs);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-xs);
}

.period-selector button {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-150);
}

.period-selector button.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.trends-chart {
  margin-bottom: var(--spacing-md);
}

.line-chart {
  width: 100%;
  height: 200px;
}

.trend-line {
  stroke-linecap: round;
  stroke-linejoin: round;
}

.data-point {
  cursor: pointer;
  transition: r var(--duration-150);
}

.data-point:hover {
  r: 6;
}

.trend-summary {
  display: flex;
  gap: var(--spacing-xl);
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.trend-stat {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.stat-value {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.stat-value.positive {
  color: var(--color-success);
}

.stat-value.negative {
  color: var(--color-error);
}

/* Table Panel */
.table-panel {
  margin-bottom: var(--spacing-lg);
}

.table-filters {
  display: flex;
  gap: var(--spacing-sm);
}

.table-filters select,
.table-filters input {
  padding: var(--spacing-sm) var(--spacing-sm);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.table-filters input {
  width: 200px;
}

.table-filters select:focus,
.table-filters input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.debt-table-container {
  overflow-x: auto;
}

.debt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.debt-table th {
  text-align: left;
  padding: var(--spacing-sm);
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  font-weight: var(--font-semibold);
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  white-space: nowrap;
}

.debt-table th:hover {
  color: var(--text-primary);
}

.debt-table td {
  padding: var(--spacing-sm);
  border-bottom: 1px solid var(--bg-secondary);
  color: var(--text-secondary);
}

.debt-table tr:hover td {
  background: var(--bg-hover);
}

.severity-badge,
.category-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.severity-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.severity-badge.high {
  background: var(--chart-orange-bg);
  color: var(--chart-orange);
}

.severity-badge.medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.severity-badge.low {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.category-badge {
  background: var(--bg-tertiary);
  color: var(--text-muted);
  text-transform: none;
}

.file-cell {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.line-number {
  color: var(--text-muted);
}

.description-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hours-cell {
  color: var(--color-warning);
  font-weight: var(--font-medium);
}

.roi-badge {
  display: inline-block;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.roi-badge.excellent {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.roi-badge.good {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.roi-badge.moderate {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.roi-badge.low {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.btn-view {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-150);
}

.btn-view:hover {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-subtle);
}

.pagination button {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150);
}

.pagination button:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
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
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
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
  color: var(--text-tertiary);
  font-size: var(--text-xl);
  cursor: pointer;
  transition: color var(--duration-150);
}

.btn-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-lg);
}

.detail-row {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.detail-row.full-width {
  flex-direction: column;
}

.detail-label {
  flex-shrink: 0;
  width: 120px;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.detail-value {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.detail-value.file-path {
  font-family: var(--font-mono);
  color: var(--color-primary);
  word-break: break-all;
}

.suggested-fix {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre-wrap;
  margin-top: var(--spacing-sm);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--border-subtle);
}

.btn-secondary {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150);
}

.btn-secondary:hover {
  background: var(--bg-hover);
  border-color: var(--border-emphasis);
}

.btn-primary {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-150);
}

.btn-primary:hover {
  background: var(--color-primary-dark);
}
</style>
