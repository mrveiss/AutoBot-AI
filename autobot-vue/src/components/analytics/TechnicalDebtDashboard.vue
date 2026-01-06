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
                <circle r="70" fill="none" stroke="#2a2a3e" stroke-width="30" />
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
                <text class="center-value" text-anchor="middle" dy="0.1em" font-size="24" fill="#fff">
                  {{ summary.total_items }}
                </text>
                <text class="center-label" text-anchor="middle" dy="1.5em" font-size="10" fill="#888">
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
              <line v-for="i in 5" :key="'h' + i" :x1="50" :x2="780" :y1="i * 35 + 10" :y2="i * 35 + 10" stroke="#333" stroke-dasharray="2,2" />
            </g>

            <!-- Y-Axis Labels -->
            <g class="y-axis">
              <text v-for="(label, i) in yAxisLabels" :key="'y' + i" :x="45" :y="i * 35 + 15" text-anchor="end" fill="#888" font-size="10">
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
                fill="#888"
                font-size="9"
              >
                {{ formatTrendDate(point.date) }}
              </text>
            </g>

            <!-- Trend Line -->
            <path v-if="trendLinePath" :d="trendLinePath" fill="none" stroke="#3b82f6" stroke-width="2" class="trend-line" />

            <!-- Data Points -->
            <g class="data-points">
              <circle
                v-for="(point, i) in trendPoints"
                :key="'p' + i"
                :cx="point.x"
                :cy="point.y"
                r="4"
                fill="#3b82f6"
                class="data-point"
                @mouseenter="hoveredPoint = point"
                @mouseleave="hoveredPoint = null"
              />
            </g>

            <!-- Tooltip -->
            <g v-if="hoveredPoint" class="tooltip">
              <rect :x="hoveredPoint.x - 40" :y="hoveredPoint.y - 45" width="80" height="35" rx="4" fill="#1a1a2e" />
              <text :x="hoveredPoint.x" :y="hoveredPoint.y - 32" text-anchor="middle" fill="#fff" font-size="11">
                {{ hoveredPoint.count }} items
              </text>
              <text :x="hoveredPoint.x" :y="hoveredPoint.y - 18" text-anchor="middle" fill="#888" font-size="9">
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

// Category colors
const categoryColors: Record<string, string> = {
  code_complexity: '#ef4444',
  code_duplication: '#f97316',
  missing_tests: '#eab308',
  missing_docs: '#84cc16',
  anti_patterns: '#22c55e',
  security_issues: '#14b8a6',
  performance_issues: '#06b6d4',
  outdated_dependencies: '#3b82f6',
  hardcoded_values: '#8b5cf6',
  dead_code: '#a855f7',
};

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
      color: categoryColors[cat.category] || '#666',
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
.technical-debt-dashboard {
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

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-export {
  background: #3b82f6;
  border: none;
  color: #fff;
}

.btn-export:hover {
  background: #2563eb;
}

.icon {
  font-size: 1rem;
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-card {
  background: linear-gradient(135deg, #1a1a2e 0%, #16162a 100%);
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
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

.card-trend {
  font-size: 0.875rem;
  font-weight: 600;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
}

.card-trend.positive {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.card-trend.negative {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.card-trend.neutral {
  background: rgba(156, 163, 175, 0.2);
  color: #9ca3af;
}

.card-cost {
  font-size: 0.875rem;
  color: #f59e0b;
  font-weight: 600;
}

.card-priority {
  font-size: 0.75rem;
  color: #ef4444;
}

.health-bar {
  width: 100%;
  height: 6px;
  background: #2a2a3e;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 0.5rem;
}

.health-fill {
  height: 100%;
  transition: width 0.5s ease;
}

.health-fill.healthy {
  background: #22c55e;
}

.health-fill.moderate {
  background: #eab308;
}

.health-fill.warning {
  background: #f97316;
}

.health-fill.critical {
  background: #ef4444;
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
  font-weight: 600;
  color: #fff;
}

.panel-info {
  font-size: 0.75rem;
  color: #666;
}

.panel-content {
  padding: 1.25rem;
}

.view-toggle {
  display: flex;
  gap: 0.25rem;
  background: #1a1a2e;
  border-radius: 6px;
  padding: 0.25rem;
}

.view-toggle button {
  padding: 0.375rem 0.75rem;
  border: none;
  background: transparent;
  color: #888;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.view-toggle button.active {
  background: #3b82f6;
  color: #fff;
}

/* Category Chart */
.category-chart {
  display: flex;
  align-items: flex-start;
  gap: 1.5rem;
}

.donut-chart {
  width: 180px;
  height: 180px;
  flex-shrink: 0;
}

.donut-segment {
  transition: opacity 0.2s;
  cursor: pointer;
}

.donut-segment:hover {
  opacity: 0.8;
}

.center-value {
  font-weight: 700;
}

.center-label {
  text-transform: uppercase;
}

.chart-legend {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem;
  border-radius: 4px;
  transition: background 0.2s;
}

.legend-item.highlighted {
  background: rgba(255, 255, 255, 0.05);
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}

.legend-label {
  flex: 1;
  font-size: 0.8rem;
  color: #ccc;
}

.legend-value {
  font-size: 0.8rem;
  font-weight: 600;
  color: #fff;
}

/* Category List */
.category-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.category-item {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.category-item:hover {
  border-color: #3b82f6;
  background: #1e1e35;
}

.category-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.category-icon {
  font-size: 1rem;
}

.category-name {
  font-weight: 500;
  color: #fff;
}

.category-stats {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  margin-bottom: 0.5rem;
}

.stat-count {
  color: #888;
}

.stat-hours {
  color: #f59e0b;
}

.stat-severity {
  padding: 0.125rem 0.375rem;
  border-radius: 3px;
  text-transform: uppercase;
  font-size: 0.65rem;
  font-weight: 600;
}

.stat-severity.critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.stat-severity.high {
  background: rgba(249, 115, 22, 0.2);
  color: #f97316;
}

.stat-severity.medium {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.stat-severity.low {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.category-bar {
  height: 4px;
  background: #2a2a3e;
  border-radius: 2px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* Priority List */
.priority-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 400px;
  overflow-y: auto;
}

.priority-item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
}

.priority-item.top-priority {
  border-color: #3b82f6;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, #1a1a2e 100%);
}

.priority-rank {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2a2a3e;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.top-priority .priority-rank {
  background: #3b82f6;
}

.priority-content {
  flex: 1;
  min-width: 0;
}

.priority-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.priority-file {
  font-size: 0.8rem;
  color: #3b82f6;
  font-family: monospace;
}

.priority-category {
  font-size: 0.65rem;
  padding: 0.125rem 0.375rem;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
  color: #888;
}

.priority-description {
  font-size: 0.8rem;
  color: #ccc;
  margin-bottom: 0.5rem;
}

.priority-metrics {
  display: flex;
  gap: 1rem;
  font-size: 0.7rem;
}

.metric {
  color: #888;
}

.metric strong {
  color: #aaa;
}

.metric.roi {
  color: #22c55e;
}

.priority-action {
  flex-shrink: 0;
}

.btn-fix {
  padding: 0.375rem 0.75rem;
  background: #22c55e;
  border: none;
  border-radius: 4px;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-fix:hover {
  background: #16a34a;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: #666;
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.empty-text {
  font-size: 0.875rem;
}

/* Trends Panel */
.trends-panel {
  margin-bottom: 1.5rem;
}

.period-selector {
  display: flex;
  gap: 0.25rem;
  background: #1a1a2e;
  border-radius: 6px;
  padding: 0.25rem;
}

.period-selector button {
  padding: 0.375rem 0.75rem;
  border: none;
  background: transparent;
  color: #888;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.period-selector button.active {
  background: #3b82f6;
  color: #fff;
}

.trends-chart {
  margin-bottom: 1rem;
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
  transition: r 0.2s;
}

.data-point:hover {
  r: 6;
}

.trend-summary {
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

.stat-label {
  font-size: 0.75rem;
  color: #666;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #fff;
}

.stat-value.positive {
  color: #22c55e;
}

.stat-value.negative {
  color: #ef4444;
}

/* Table Panel */
.table-panel {
  margin-bottom: 1.5rem;
}

.table-filters {
  display: flex;
  gap: 0.75rem;
}

.table-filters select,
.table-filters input {
  padding: 0.5rem 0.75rem;
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 6px;
  color: #e0e0e0;
  font-size: 0.8rem;
}

.table-filters input {
  width: 200px;
}

.table-filters select:focus,
.table-filters input:focus {
  outline: none;
  border-color: #3b82f6;
}

.debt-table-container {
  overflow-x: auto;
}

.debt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.debt-table th {
  text-align: left;
  padding: 0.75rem;
  background: #1a1a2e;
  color: #888;
  font-weight: 600;
  border-bottom: 1px solid #2a2a3e;
  cursor: pointer;
  white-space: nowrap;
}

.debt-table th:hover {
  color: #fff;
}

.debt-table td {
  padding: 0.75rem;
  border-bottom: 1px solid #1a1a2e;
  color: #ccc;
}

.debt-table tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}

.severity-badge,
.category-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.severity-badge.critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.severity-badge.high {
  background: rgba(249, 115, 22, 0.2);
  color: #f97316;
}

.severity-badge.medium {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.severity-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.category-badge {
  background: rgba(255, 255, 255, 0.1);
  color: #aaa;
  text-transform: none;
}

.file-cell {
  font-family: monospace;
  font-size: 0.75rem;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.line-number {
  color: #666;
}

.description-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hours-cell {
  color: #f59e0b;
  font-weight: 500;
}

.roi-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.roi-badge.excellent {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.roi-badge.good {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.roi-badge.moderate {
  background: rgba(234, 179, 8, 0.2);
  color: #eab308;
}

.roi-badge.low {
  background: rgba(156, 163, 175, 0.2);
  color: #9ca3af;
}

.btn-view {
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: 1px solid #333;
  border-radius: 4px;
  color: #888;
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-view:hover {
  background: #1a1a2e;
  border-color: #3b82f6;
  color: #3b82f6;
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #2a2a3e;
}

.pagination button {
  padding: 0.5rem 1rem;
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 6px;
  color: #e0e0e0;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.pagination button:hover:not(:disabled) {
  background: #252540;
  border-color: #3b82f6;
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.8rem;
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
  transition: color 0.2s;
}

.btn-close:hover {
  color: #fff;
}

.modal-body {
  padding: 1.5rem;
}

.detail-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.detail-row.full-width {
  flex-direction: column;
}

.detail-label {
  flex-shrink: 0;
  width: 120px;
  color: #888;
  font-size: 0.875rem;
}

.detail-value {
  color: #e0e0e0;
  font-size: 0.875rem;
}

.detail-value.file-path {
  font-family: monospace;
  color: #3b82f6;
  word-break: break-all;
}

.suggested-fix {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  padding: 1rem;
  font-family: monospace;
  font-size: 0.8rem;
  color: #ccc;
  overflow-x: auto;
  white-space: pre-wrap;
  margin-top: 0.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
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
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: #252540;
  border-color: #444;
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: #3b82f6;
  border: none;
  border-radius: 6px;
  color: #fff;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover {
  background: #2563eb;
}
</style>
