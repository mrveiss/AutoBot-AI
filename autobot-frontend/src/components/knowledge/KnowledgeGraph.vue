<template>
  <div class="knowledge-graph" :class="{ 'fullscreen': isFullscreen }">
    <!-- Header Section -->
    <div class="graph-header">
      <div class="header-content">
        <h3><i class="fas fa-project-diagram"></i> Knowledge Graph</h3>
        <p class="header-description">Visualize entities and their relationships</p>
      </div>
      <div class="header-actions">
        <button
          @click="refreshGraph"
          :disabled="isLoading"
          class="action-btn refresh"
          title="Refresh graph data"
        >
          <i class="fas fa-sync" :class="{ 'fa-spin': isLoading }"></i>
          Refresh
        </button>
        <button
          @click="toggleLayout"
          class="action-btn"
          title="Toggle layout"
        >
          <i class="fas fa-th"></i>
          {{ layoutMode === 'force' ? 'Grid' : 'Force' }}
        </button>
        <button
          @click="fitGraph"
          class="action-btn"
          title="Fit graph to view"
        >
          <i class="fas fa-expand"></i>
          Fit
        </button>
        <button
          @click="showCleanupPanel = !showCleanupPanel"
          class="action-btn cleanup"
          :class="{ active: showCleanupPanel }"
          title="Cleanup orphaned entities"
        >
          <i class="fas fa-broom"></i>
          Cleanup
        </button>
      </div>
    </div>

    <!-- Memory Orphan Cleanup Panel (Issue #547) -->
    <transition name="slide-down">
      <div v-if="showCleanupPanel" class="cleanup-panel-wrapper">
        <MemoryOrphanManager @cleanup-complete="handleCleanupComplete" />
      </div>
    </transition>

    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" class="close-btn">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Controls Section -->
    <div class="graph-controls">
      <!-- Search -->
      <div class="control-group search-group">
        <label for="entity-search">
          <i class="fas fa-search"></i>
        </label>
        <input
          id="entity-search"
          v-model="searchQuery"
          type="text"
          placeholder="Search entities..."
          @input="handleSearch"
        />
        <button
          v-if="searchQuery"
          @click="clearSearch"
          class="clear-btn"
          title="Clear search"
        >
          <i class="fas fa-times"></i>
        </button>
      </div>

      <!-- Filter by Type -->
      <div class="control-group">
        <label for="type-filter">Type:</label>
        <select id="type-filter" v-model="selectedType" @change="filterEntities">
          <option value="">All Types</option>
          <option v-for="type in entityTypes" :key="type" :value="type">
            {{ formatTypeName(type) }}
          </option>
        </select>
      </div>

      <!-- Depth Control -->
      <div class="control-group">
        <label for="depth-control">Depth:</label>
        <select id="depth-control" v-model.number="graphDepth" @change="refreshGraph">
          <option :value="1">1 Level</option>
          <option :value="2">2 Levels</option>
          <option :value="3">3 Levels</option>
        </select>
      </div>

      <!-- Stats Summary -->
      <div class="stats-summary">
        <span class="stat">
          <i class="fas fa-circle node-icon"></i>
          {{ filteredEntities.length }} entities
        </span>
        <span class="stat">
          <i class="fas fa-link edge-icon"></i>
          {{ relationCount }} relations
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <div class="spinner">
        <i class="fas fa-circle-notch fa-spin"></i>
      </div>
      <p>Loading knowledge graph...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="entities.length === 0 && !isLoading" class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-project-diagram"></i>
      </div>
      <h4>No Entities Found</h4>
      <p>Start building your knowledge graph by adding entities.</p>
      <button @click="showCreateModal = true" class="action-btn primary">
        <i class="fas fa-plus"></i>
        Create Entity
      </button>
    </div>

    <!-- Cytoscape Graph Container -->
    <div v-else class="graph-container">
      <div ref="cytoscapeContainer" class="cytoscape-container"></div>

      <!-- Zoom Controls -->
      <div class="zoom-controls">
        <button @click="zoomIn" title="Zoom in">
          <i class="fas fa-plus"></i>
        </button>
        <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
        <button @click="zoomOut" title="Zoom out">
          <i class="fas fa-minus"></i>
        </button>
        <button @click="fitGraph" title="Fit to view">
          <i class="fas fa-expand"></i>
        </button>
        <span class="control-separator">|</span>
        <button @click="toggleFullscreen" :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'">
          <i :class="isFullscreen ? 'fas fa-compress' : 'fas fa-expand-arrows-alt'"></i>
        </button>
      </div>
    </div>

    <!-- Entity Details Panel -->
    <transition name="slide">
      <div v-if="selectedEntity" class="details-panel">
        <div class="panel-header">
          <h4>
            <span class="entity-icon" :style="{ background: getNodeColor(selectedEntity.type) }">
              {{ getEntityIcon(selectedEntity.type) }}
            </span>
            {{ selectedEntity.name }}
          </h4>
          <button @click="selectedEntity = null" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="panel-content">
          <!-- Entity Info -->
          <div class="info-section">
            <div class="info-row">
              <label>Type:</label>
              <span class="type-badge" :style="{ background: getNodeColor(selectedEntity.type) }">
                {{ formatTypeName(selectedEntity.type) }}
              </span>
            </div>
            <div class="info-row">
              <label>ID:</label>
              <code>{{ selectedEntity.id }}</code>
            </div>
            <div class="info-row" v-if="selectedEntity.created_at">
              <label>Created:</label>
              <span>{{ formatDate(selectedEntity.created_at) }}</span>
            </div>
          </div>

          <!-- Observations -->
          <div class="observations-section" v-if="selectedEntity.observations?.length">
            <h5><i class="fas fa-eye"></i> Observations</h5>
            <ul class="observations-list">
              <li v-for="(obs, idx) in selectedEntity.observations" :key="idx">
                {{ obs }}
              </li>
            </ul>
          </div>

          <!-- Relations -->
          <div class="relations-section" v-if="getEntityRelations(selectedEntity.id).length">
            <h5><i class="fas fa-link"></i> Relations</h5>
            <ul class="relations-list">
              <li
                v-for="relation in getEntityRelations(selectedEntity.id)"
                :key="`${relation.from}-${relation.to}`"
                @click="navigateToEntity(relation)"
              >
                <span class="relation-type">{{ relation.type }}</span>
                <span class="relation-target">
                  <i class="fas fa-arrow-right"></i>
                  {{ getEntityName(relation.from === selectedEntity.id ? relation.to : relation.from) }}
                </span>
              </li>
            </ul>
          </div>

          <!-- Actions -->
          <div class="panel-actions">
            <button @click="focusOnEntity(selectedEntity)" class="action-btn">
              <i class="fas fa-crosshairs"></i>
              Focus
            </button>
            <button @click="highlightNeighbors(selectedEntity)" class="action-btn">
              <i class="fas fa-expand-arrows-alt"></i>
              Neighbors
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Create Entity Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4><i class="fas fa-plus-circle"></i> Create Entity</h4>
          <button @click="showCreateModal = false" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <form @submit.prevent="createEntity" class="entity-form">
          <div class="form-group">
            <label for="entity-name">Name *</label>
            <input
              id="entity-name"
              v-model="newEntity.name"
              type="text"
              required
              placeholder="Entity name"
            />
          </div>
          <div class="form-group">
            <label for="entity-type">Type *</label>
            <select id="entity-type" v-model="newEntity.type" required>
              <option value="">Select type...</option>
              <option value="conversation">Conversation</option>
              <option value="bug_fix">Bug Fix</option>
              <option value="feature">Feature</option>
              <option value="decision">Decision</option>
              <option value="task">Task</option>
              <option value="user_preference">User Preference</option>
              <option value="context">Context</option>
              <option value="learning">Learning</option>
              <option value="research">Research</option>
              <option value="implementation">Implementation</option>
            </select>
          </div>
          <div class="form-group">
            <label for="entity-observations">Observations *</label>
            <textarea
              id="entity-observations"
              v-model="newEntity.observations"
              rows="3"
              required
              placeholder="Enter observations (one per line)"
            ></textarea>
          </div>
          <div class="form-actions">
            <button type="button" @click="showCreateModal = false" class="action-btn">
              Cancel
            </button>
            <button type="submit" class="action-btn primary" :disabled="isCreating">
              <i v-if="isCreating" class="fas fa-spinner fa-spin"></i>
              <i v-else class="fas fa-plus"></i>
              Create
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Legend -->
    <div class="graph-legend">
      <h5>Entity Types</h5>
      <div class="legend-items">
        <div
          v-for="type in entityTypes"
          :key="type"
          class="legend-item"
          @click="filterByType(type)"
          :class="{ active: selectedType === type }"
        >
          <span class="legend-color" :style="{ background: getNodeColor(type) }"></span>
          <span class="legend-label">{{ formatTypeName(type) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * KnowledgeGraph - Interactive visualization of memory entities and their relationships
 *
 * @description Provides a Cytoscape.js-powered force-directed graph for visualizing
 * knowledge entities, their types, observations, and inter-entity relationships.
 *
 * @features
 * - Interactive graph visualization with zoom, pan, and node selection
 * - Entity search with debounced input for performance
 * - Filter by entity type with visual legend
 * - Depth control for relationship traversal (1-3 levels)
 * - Entity CRUD operations (create via modal)
 * - Memory orphan cleanup integration (Issue #547)
 * - Responsive layout with grid/force-directed toggle
 *
 * @see Issue #707 - Migrated from custom SVG to Cytoscape.js
 * @see Issue #547 - Memory orphan cleanup integration
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, shallowRef, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import cytoscape, { type Core, type NodeSingular } from 'cytoscape'
// @ts-expect-error - cytoscape-fcose has no type declarations
import fcose from 'cytoscape-fcose'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { createLogger } from '@/utils/debugUtils'
import MemoryOrphanManager from '@/components/knowledge/MemoryOrphanManager.vue'

// Register fcose layout
cytoscape.use(fcose)

const logger = createLogger('KnowledgeGraph')

// ============================================================================
// Component Events
// ============================================================================

/**
 * Emitted events from this component
 * @event entity-selected - Fired when user selects an entity node
 * @event graph-refreshed - Fired after graph data is refreshed
 * @event entity-created - Fired when a new entity is created
 */
const emit = defineEmits<{
  /** Emitted when user clicks on an entity node */
  (e: 'entity-selected', entity: Entity | null): void
  /** Emitted after graph data refresh completes */
  (e: 'graph-refreshed', stats: { entities: number; relations: number }): void
  /** Emitted when a new entity is successfully created */
  (e: 'entity-created', entity: Entity): void
}>()

// ============================================================================
// Types
// ============================================================================

interface Entity {
  id: string
  name: string
  type: string
  created_at?: number
  updated_at?: number
  observations: string[]
  metadata?: Record<string, unknown>
}

interface Relation {
  from: string
  to: string
  type: string
  strength?: number
}

interface NewEntity {
  name: string
  type: string
  observations: string
}

// ============================================================================
// State
// ============================================================================

const isLoading = ref(false)
const isCreating = ref(false)
const errorMessage = ref('')
const entities = ref<Entity[]>([])
const relations = ref<Relation[]>([])
const selectedEntity = ref<Entity | null>(null)
const searchQuery = ref('')
const selectedType = ref('')
const graphDepth = ref(2)
const layoutMode = ref<'force' | 'grid'>('force')
const showCreateModal = ref(false)
const showCleanupPanel = ref(false)
const zoomLevel = ref(1)
const isFullscreen = ref(false)

// New entity form
const newEntity = ref<NewEntity>({
  name: '',
  type: '',
  observations: ''
})

// Cytoscape instance - using shallowRef for non-reactive external library instance
const cytoscapeContainer = ref<HTMLElement | null>(null)
const cy = shallowRef<Core | null>(null)

// ============================================================================
// Utilities
// ============================================================================

/**
 * Creates a debounced version of a function
 * @param fn - Function to debounce
 * @param delay - Delay in milliseconds
 * @returns Debounced function
 */
function debounce<T extends (...args: Parameters<T>) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delay)
  }
}

/** Debounced graph update for search performance (300ms delay) */
const debouncedUpdateGraph = debounce(() => {
  updateCytoscapeElements()
}, 300)

// ============================================================================
// Computed
// ============================================================================

const entityTypes = computed(() => {
  const types = new Set(entities.value.map(e => e.type))
  return Array.from(types).sort()
})

const filteredEntities = computed(() => {
  let result = entities.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(e =>
      e.name.toLowerCase().includes(query) ||
      e.type.toLowerCase().includes(query) ||
      e.observations.some(o => o.toLowerCase().includes(query))
    )
  }

  if (selectedType.value) {
    result = result.filter(e => e.type === selectedType.value)
  }

  return result
})

const graphEdges = computed(() => {
  const entityIds = new Set(filteredEntities.value.map(e => e.id))
  return relations.value.filter(r =>
    entityIds.has(r.from) && entityIds.has(r.to)
  )
})

const relationCount = computed(() => graphEdges.value.length)

// ============================================================================
// Node Colors & Icons
// ============================================================================

/**
 * Gets a CSS variable value from the document root
 * Issue #704: Use design tokens for theming
 * @param name - CSS variable name (e.g., '--chart-blue')
 * @param fallback - Fallback value if variable is not defined
 * @returns The CSS variable value or fallback
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/**
 * Returns the color associated with an entity type for graph visualization
 * Issue #704: Uses CSS design tokens for theming support
 * @param type - The entity type (e.g., 'conversation', 'bug_fix')
 * @returns Hex color code for the entity type, defaults to gray
 */
function getNodeColor(type: string): string {
  // Issue #704: Map entity types to design token colors
  const colorMap: Record<string, string> = {
    // Knowledge Base types
    category: getCssVar('--color-primary', '#6366f1'),
    fact: getCssVar('--color-success', '#10b981'),
    // Memory entity types - using chart colors for variety
    conversation: getCssVar('--chart-blue', '#3b82f6'),
    bug_fix: getCssVar('--color-error', '#ef4444'),
    feature: getCssVar('--chart-green', '#22c55e'),
    decision: getCssVar('--color-warning', '#f59e0b'),
    task: getCssVar('--chart-purple', '#8b5cf6'),
    user_preference: getCssVar('--chart-pink', '#ec4899'),
    context: getCssVar('--color-primary', '#6366f1'),
    learning: getCssVar('--chart-teal', '#14b8a6'),
    research: getCssVar('--chart-orange', '#f97316'),
    implementation: getCssVar('--chart-cyan', '#06b6d4'),
    chat_session: getCssVar('--chart-blue', '#3b82f6')
  }
  return colorMap[type] || getCssVar('--text-tertiary', '#6b7280')
}

/**
 * Returns the emoji icon associated with an entity type
 * @param type - The entity type
 * @returns Emoji icon for the entity type, defaults to document icon
 */
function getEntityIcon(type: string): string {
  const icons: Record<string, string> = {
    // Knowledge Base types
    category: '📁',
    fact: '💡',
    // Memory entity types
    conversation: '💬',
    bug_fix: '🐛',
    feature: '✨',
    decision: '⚖️',
    task: '📋',
    user_preference: '👤',
    context: '📌',
    learning: '📚',
    research: '🔬',
    implementation: '💻',
    chat_session: '💬'
  }
  return icons[type] || '📄'
}

/**
 * Formats a snake_case type name to Title Case for display
 * @param type - The snake_case type name
 * @returns Formatted type name (e.g., 'bug_fix' -> 'Bug Fix')
 */
function formatTypeName(type: string): string {
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Formats a Unix timestamp to a human-readable date string
 * @param timestamp - Unix timestamp in seconds
 * @returns Formatted date string (e.g., 'Jan 7, 2026')
 */
function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

// ============================================================================
// Cytoscape Initialization
// ============================================================================

/**
 * Initializes the Cytoscape.js graph instance
 * Sets up event handlers for node selection, hover effects, and zoom tracking
 */
function initCytoscape(): void {
  if (!cytoscapeContainer.value) return

  cy.value = cytoscape({
    container: cytoscapeContainer.value,
    style: getCytoscapeStyles(),
    elements: [],
    minZoom: 0.2,
    maxZoom: 3,
    wheelSensitivity: 0.3,
    boxSelectionEnabled: false
  })

  const cyInstance = cy.value

  // Event handlers
  cyInstance.on('tap', 'node', (evt: cytoscape.EventObject) => {
    const node = evt.target as NodeSingular
    const entityId = node.id()
    const entity = entities.value.find(e => e.id === entityId)
    if (entity) {
      selectedEntity.value = entity
      emit('entity-selected', entity)
    }
  })

  cyInstance.on('tap', (evt: cytoscape.EventObject) => {
    if (evt.target === cyInstance) {
      selectedEntity.value = null
      emit('entity-selected', null)
      clearHighlight()
    }
  })

  cyInstance.on('mouseover', 'node', (evt: cytoscape.EventObject) => {
    const node = evt.target as NodeSingular
    highlightConnectedNodes(node)
  })

  cyInstance.on('mouseout', 'node', () => {
    clearHighlight()
  })

  cyInstance.on('zoom', () => {
    zoomLevel.value = cy.value?.zoom() || 1
  })

  logger.debug('Cytoscape initialized')
}

/**
 * Returns Cytoscape graph styles using design tokens
 * Issue #704: All colors now use CSS custom properties for theming
 */
function getCytoscapeStyles(): cytoscape.StylesheetStyle[] {
  // Issue #704: Read colors from design tokens at style creation time
  const textPrimary = getCssVar('--text-primary', '#e2e8f0')
  const bgSecondary = getCssVar('--bg-secondary', '#1e293b')
  const bgTertiary = getCssVar('--bg-tertiary', '#334155')
  const textSecondary = getCssVar('--text-secondary', '#94a3b8')
  const borderDefault = getCssVar('--border-default', '#64748b')
  const colorWarning = getCssVar('--color-warning', '#fbbf24')

  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'width': 'data(size)',
        'height': 'data(size)',
        'font-size': '11px',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 8,
        'color': textPrimary,
        'text-outline-color': bgSecondary,
        'text-outline-width': 2,
        'border-width': 2,
        'border-color': bgTertiary,
        'text-max-width': '100px',
        'text-wrap': 'ellipsis'
      }
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': '#ffffff'
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': colorWarning
      }
    },
    {
      selector: 'node.dimmed',
      style: {
        'opacity': 0.15
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': borderDefault,
        'target-arrow-color': borderDefault,
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(label)',
        'font-size': '9px',
        'text-rotation': 'autorotate',
        'text-margin-y': -10,
        'color': textSecondary,
        'text-outline-color': bgSecondary,
        'text-outline-width': 1,
        'opacity': 0.6
      }
    },
    {
      selector: 'edge.highlighted',
      style: {
        'line-color': colorWarning,
        'target-arrow-color': colorWarning,
        'width': 3,
        'opacity': 1
      }
    },
    {
      selector: 'edge.dimmed',
      style: {
        'opacity': 0.1
      }
    }
  ]
}

// ============================================================================
// Graph Data Management
// ============================================================================

/**
 * Updates Cytoscape graph elements based on filtered entities and relations
 * Rebuilds nodes and edges, then runs the layout algorithm
 */
function updateCytoscapeElements(): void {
  if (!cy.value) return

  const elements: cytoscape.ElementDefinition[] = []

  // Add nodes
  for (const entity of filteredEntities.value) {
    const obsCount = entity.observations?.length || 0
    const size = 40 + Math.min(obsCount * 3, 20)

    elements.push({
      data: {
        id: entity.id,
        label: truncateText(entity.name, 15),
        color: getNodeColor(entity.type),
        size: size,
        type: entity.type
      }
    })
  }

  // Add edges
  for (const edge of graphEdges.value) {
    elements.push({
      data: {
        id: `${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        label: edge.type
      }
    })
  }

  // Update graph
  cy.value.elements().remove()
  cy.value.add(elements)

  // Run layout
  runLayout()
}

/**
 * Runs the graph layout algorithm (force-directed or grid)
 * Uses fcose for force-directed layout with customized physics settings
 */
function runLayout(): void {
  if (!cy.value) return

  const layoutOptions = layoutMode.value === 'force'
    ? {
        name: 'fcose',
        animate: true,
        animationDuration: 500,
        fit: true,
        padding: 50,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 150,
        nodeRepulsion: 8000,
        gravity: 0.25,
        gravityRange: 1.5
      }
    : {
        name: 'grid',
        animate: true,
        animationDuration: 300,
        fit: true,
        padding: 50,
        avoidOverlap: true,
        nodeDimensionsIncludeLabels: true
      }

  cy.value.layout(layoutOptions as cytoscape.LayoutOptions).run()
}

/**
 * Truncates text to a maximum length, adding ellipsis if needed
 * @param text - The text to truncate
 * @param maxLength - Maximum allowed length
 * @returns Truncated text with ellipsis or original text if shorter
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 1) + '…'
}

// ============================================================================
// Data Fetching
// ============================================================================

/**
 * Handles cleanup completion from MemoryOrphanManager
 * Hides the cleanup panel and refreshes the graph
 */
function handleCleanupComplete(): void {
  showCleanupPanel.value = false
  refreshGraph()
}

/**
 * Refreshes the knowledge graph by fetching entities and relations from the API
 * Emits 'graph-refreshed' event on successful load with entity/relation counts
 */
async function refreshGraph(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''

  try {
    // Fetch from unified knowledge graph endpoint (includes categories + facts)
    const unifiedResponse = await apiClient.get('/api/knowledge/unified/graph?max_facts=100&include_categories=true')
    const unifiedData = await parseApiResponse(unifiedResponse)

    // Also fetch memory entities for backward compatibility
    const memoryResponse = await apiClient.get('/api/memory/entities/all')
    const memoryData = await parseApiResponse(memoryResponse)

    // Merge entities from both sources
    const unifiedEntities = unifiedData?.data?.entities || []
    const memoryEntities = memoryData?.data?.entities || memoryData?.entities || []

    // Combine entities, avoiding duplicates by ID
    const entityMap = new Map<string, Entity>()
    for (const entity of [...unifiedEntities, ...memoryEntities]) {
      if (entity.id && !entityMap.has(entity.id)) {
        entityMap.set(entity.id, entity)
      }
    }
    entities.value = Array.from(entityMap.values())

    // Get relations from unified endpoint
    const unifiedRelations = unifiedData?.data?.relations || []
    relations.value = unifiedRelations

    // Also fetch memory relations if we have memory entities
    if (memoryEntities.length > 0) {
      await fetchMemoryRelations(memoryEntities)
    }

    // Wait for DOM to render the graph container (it's conditionally rendered)
    await nextTick()

    // Initialize Cytoscape if not already done (container now exists)
    if (!cy.value && cytoscapeContainer.value) {
      initCytoscape()
    }

    updateCytoscapeElements()

    // Emit refresh event with statistics
    emit('graph-refreshed', {
      entities: entities.value.length,
      relations: relations.value.length
    })

    logger.info(`Loaded unified graph: ${entities.value.length} entities, ${relations.value.length} relations`)

  } catch (error) {
    logger.error('Failed to fetch graph data:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Failed to load graph'
  } finally {
    isLoading.value = false
  }
}

/**
 * Fetches relations for memory entities using parallel requests
 * Uses Promise.allSettled to handle partial failures gracefully
 * Deduplicates relations to avoid duplicate edges in the graph
 */
async function fetchMemoryRelations(memoryEntities: Entity[]): Promise<void> {
  const allRelations: Relation[] = [...relations.value] // Keep existing relations

  const relationResults = await Promise.allSettled(
    memoryEntities.map(async (entity) => {
      const response = await apiClient.get(`/api/memory/entities/${entity.id}/relations`)
      const parsedResponse = await parseApiResponse(response)
      return { entity, parsedResponse }
    })
  )

  for (const result of relationResults) {
    if (result.status === 'rejected') {
      continue
    }

    const { entity, parsedResponse } = result.value
    const responseData = parsedResponse?.data || parsedResponse

    if (responseData?.related_entities) {
      for (const relatedEntity of responseData.related_entities) {
        allRelations.push({
          from: entity.id,
          to: relatedEntity.entity?.id || relatedEntity.id,
          type: relatedEntity.relation_type || relatedEntity.type || 'relates_to',
          strength: relatedEntity.strength || 1.0
        })
      }
    } else if (responseData?.relations) {
      allRelations.push(...responseData.relations)
    }
  }

  // Deduplicate relations using Set for O(1) lookups
  const relationSet = new Set<string>()
  relations.value = allRelations.filter(r => {
    const key = `${r.from}-${r.to}-${r.type}`
    if (relationSet.has(key)) return false
    relationSet.add(key)
    return true
  })
}

/**
 * Creates a new entity via the API
 * Validates required fields and emits 'entity-created' event on success
 */
async function createEntity(): Promise<void> {
  if (!newEntity.value.name || !newEntity.value.type || !newEntity.value.observations) {
    errorMessage.value = 'Please fill in all required fields'
    return
  }

  isCreating.value = true
  errorMessage.value = ''

  try {
    const observations = newEntity.value.observations
      .split('\n')
      .map(o => o.trim())
      .filter(o => o.length > 0)

    const response = await apiClient.post('/api/memory/entities', {
      name: newEntity.value.name,
      entity_type: newEntity.value.type,
      observations
    })

    const parsedResponse = await parseApiResponse(response)
    const responseData = parsedResponse?.data || parsedResponse

    let createdEntity: Entity | null = null
    if (responseData?.id && responseData?.name) {
      createdEntity = responseData as Entity
      entities.value.push(createdEntity)
    } else if (responseData?.entity) {
      createdEntity = responseData.entity as Entity
      entities.value.push(createdEntity)
    }

    updateCytoscapeElements()

    // Emit entity created event
    if (createdEntity) {
      emit('entity-created', createdEntity)
    }

    showCreateModal.value = false
    newEntity.value = { name: '', type: '', observations: '' }
  } catch (error) {
    logger.error('Failed to create entity:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Failed to create entity'
  } finally {
    isCreating.value = false
  }
}

// ============================================================================
// Interactions
// ============================================================================

/**
 * Highlights a node and its connected neighbors, dimming all other elements
 * @param node - The Cytoscape node to highlight
 */
function highlightConnectedNodes(node: NodeSingular): void {
  if (!cy.value) return

  const neighborhood = node.neighborhood().add(node)
  cy.value.elements().addClass('dimmed')
  neighborhood.removeClass('dimmed').addClass('highlighted')
}

/**
 * Highlights an entity's neighbors in the graph
 * @param entity - The entity whose neighbors to highlight
 */
function highlightNeighbors(entity: Entity): void {
  if (!cy.value) return

  const node = cy.value.getElementById(entity.id)
  if (node.length) {
    highlightConnectedNodes(node as NodeSingular)
  }
}

/**
 * Clears all highlight effects from the graph
 */
function clearHighlight(): void {
  if (!cy.value) return
  cy.value.elements().removeClass('dimmed').removeClass('highlighted')
}

/**
 * Centers and zooms the graph on a specific entity
 * @param entity - The entity to focus on
 */
function focusOnEntity(entity: Entity): void {
  if (!cy.value) return

  const node = cy.value.getElementById(entity.id)
  if (node.length) {
    cy.value.animate({
      center: { eles: node },
      zoom: 1.5
    }, {
      duration: 300
    })
  }
}

/**
 * Gets all relations involving a specific entity
 * @param entityId - The entity ID to find relations for
 * @returns Array of relations where the entity is either source or target
 */
function getEntityRelations(entityId: string): Relation[] {
  return relations.value.filter(r => r.from === entityId || r.to === entityId)
}

/**
 * Gets the display name for an entity by ID
 * @param entityId - The entity ID to look up
 * @returns Entity name or the ID if entity not found
 */
function getEntityName(entityId: string): string {
  const entity = entities.value.find(e => e.id === entityId)
  return entity?.name || entityId
}

/**
 * Navigates to the other entity in a relation and focuses on it
 * @param relation - The relation to navigate through
 */
function navigateToEntity(relation: Relation): void {
  const targetId = relation.from === selectedEntity.value?.id ? relation.to : relation.from
  const target = entities.value.find(e => e.id === targetId)
  if (target) {
    selectedEntity.value = target
    emit('entity-selected', target)
    focusOnEntity(target)
  }
}

// ============================================================================
// Controls
// ============================================================================

/**
 * Handles search input with debouncing for performance
 * Uses 300ms delay to avoid excessive graph updates during typing
 */
function handleSearch(): void {
  debouncedUpdateGraph()
}

/**
 * Clears the search query and updates the graph immediately
 */
function clearSearch(): void {
  searchQuery.value = ''
  updateCytoscapeElements()
}

/**
 * Filters entities by type and updates the graph
 */
function filterEntities(): void {
  updateCytoscapeElements()
}

/**
 * Toggles type filter - selecting same type again clears the filter
 * @param type - The entity type to filter by
 */
function filterByType(type: string): void {
  selectedType.value = selectedType.value === type ? '' : type
  updateCytoscapeElements()
}

/**
 * Toggles between force-directed and grid layout modes
 */
function toggleLayout(): void {
  layoutMode.value = layoutMode.value === 'force' ? 'grid' : 'force'
  runLayout()
}

/**
 * Zooms the graph in by 25%
 */
function zoomIn(): void {
  if (!cy.value) return
  cy.value.zoom(cy.value.zoom() * 1.25)
  cy.value.center()
}

/**
 * Zooms the graph out by 20%
 */
function zoomOut(): void {
  if (!cy.value) return
  cy.value.zoom(cy.value.zoom() * 0.8)
  cy.value.center()
}

/**
 * Fits the entire graph within the viewport with 50px padding
 */
function fitGraph(): void {
  if (!cy.value) return
  cy.value.fit(undefined, 50)
  zoomLevel.value = cy.value.zoom()
}

/**
 * Toggles fullscreen mode for the graph visualization
 */
function toggleFullscreen(): void {
  isFullscreen.value = !isFullscreen.value
  // Re-fit the graph after transition
  nextTick(() => {
    setTimeout(() => {
      if (cy.value) {
        cy.value.resize()
        fitGraph()
      }
    }, 100)
  })
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  // Don't init Cytoscape here - container may not exist yet (conditionally rendered)
  // It will be initialized in refreshGraph() after data loads
  refreshGraph()
})

onUnmounted(() => {
  if (cy.value) {
    cy.value.destroy()
    cy.value = null
  }
})

watch(layoutMode, () => {
  runLayout()
})
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */
.knowledge-graph {
  padding: var(--spacing-lg);
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  background: var(--bg-primary);
}

/* Header */
.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-subtle);
}

.header-content h3 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.header-content h3 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

/* Action Buttons */
.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: var(--color-primary);
  color: white;
  border-color: transparent;
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-primary);
}

.action-btn.refresh {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.action-btn.cleanup {
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.action-btn.cleanup:hover:not(:disabled) {
  background: var(--color-warning-bg);
}

.action-btn.cleanup.active {
  background: var(--color-warning);
  color: white;
}

/* Cleanup Panel */
.cleanup-panel-wrapper {
  margin-bottom: var(--spacing-md);
}

/* Slide down transition */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all var(--duration-300) ease;
  overflow: hidden;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-10px);
  max-height: 0;
}

.slide-down-enter-to,
.slide-down-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 1000px;
}

/* Error Notification */
.error-notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-left: 4px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error-text);
}

.error-notification i.fa-exclamation-circle {
  color: var(--color-error);
}

.error-notification span {
  flex: 1;
  font-size: var(--text-sm);
}

.close-btn {
  background: none;
  border: none;
  padding: var(--spacing-xs);
  cursor: pointer;
  color: var(--text-secondary);
  opacity: 0.7;
  transition: opacity var(--duration-200);
}

.close-btn:hover {
  opacity: 1;
}

/* Controls */
.graph-controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  align-items: center;
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.control-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.control-group label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.search-group {
  flex: 1;
  min-width: 200px;
  max-width: 300px;
  position: relative;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-sm);
}

.search-group input {
  flex: 1;
  border: none;
  outline: none;
  font-size: var(--text-sm);
  width: 100%;
  background: transparent;
  color: var(--text-primary);
}

.search-group input::placeholder {
  color: var(--text-tertiary);
}

.search-group .clear-btn {
  position: absolute;
  right: var(--spacing-sm);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.control-group select {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
}

.stats-summary {
  margin-left: auto;
  display: flex;
  gap: var(--spacing-md);
}

.stats-summary .stat {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.node-icon {
  color: var(--color-primary);
}

.edge-icon {
  color: var(--text-tertiary);
}

/* Loading State */
.loading-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  color: var(--text-secondary);
}

.loading-state .spinner {
  font-size: 2rem;
  color: var(--color-primary);
}

/* Empty State */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  text-align: center;
}

.empty-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  color: var(--color-primary);
}

.empty-state h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.empty-state p {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

/* Graph Container */
.graph-container {
  flex: 1;
  position: relative;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  min-height: 500px;
  border: 1px solid var(--border-subtle);
}

.cytoscape-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  min-height: 400px;
}

/* Zoom Controls */
.zoom-controls {
  position: absolute;
  bottom: var(--spacing-md);
  right: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  background: var(--bg-card);
  padding: var(--spacing-sm);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-subtle);
}

.zoom-controls button {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--duration-200);
}

.zoom-controls button:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.zoom-level {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  min-width: 40px;
  text-align: center;
}

/* Details Panel */
.details-panel {
  position: absolute;
  top: var(--spacing-md);
  right: var(--spacing-md);
  width: 320px;
  max-height: calc(100% - 2rem);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-subtle);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--color-primary);
  color: white;
}

.panel-header h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.entity-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.panel-header .close-btn {
  color: white;
}

.panel-content {
  padding: var(--spacing-md);
  overflow-y: auto;
  flex: 1;
}

.info-section {
  margin-bottom: var(--spacing-md);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.info-row label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.info-row code {
  font-size: var(--text-xs);
  background: var(--bg-secondary);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}

.type-badge {
  font-size: var(--text-xs);
  color: white;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
}

.observations-section,
.relations-section {
  margin-bottom: var(--spacing-md);
}

.observations-section h5,
.relations-section h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.observations-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.observations-list li {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-sm);
}

.relations-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.relations-list li {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  padding: var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-sm);
  cursor: pointer;
  transition: background var(--duration-200);
}

.relations-list li:hover {
  background: var(--bg-hover);
}

.relation-type {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.relation-target {
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.relation-target i {
  font-size: 10px;
  color: var(--text-tertiary);
}

.panel-actions {
  display: flex;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-subtle);
}

.panel-actions .action-btn {
  flex: 1;
  justify-content: center;
  font-size: var(--text-sm);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 480px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xl);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-primary);
  color: white;
}

.modal-header h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.modal-header .close-btn {
  color: white;
}

.entity-form {
  padding: var(--spacing-lg);
}

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
}

/* Legend */
.graph-legend {
  padding: var(--spacing-md);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-subtle);
}

.graph-legend h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-200);
  border: 1px solid transparent;
}

.legend-item:hover {
  background: var(--bg-hover);
}

.legend-item.active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-label {
  color: var(--text-primary);
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all var(--duration-300) ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

/* Responsive */
@media (max-width: 768px) {
  .graph-header {
    flex-direction: column;
    gap: var(--spacing-md);
    align-items: flex-start;
  }

  .graph-controls {
    flex-direction: column;
    align-items: stretch;
  }

  .search-group {
    max-width: none;
  }

  .stats-summary {
    margin-left: 0;
    justify-content: center;
  }

  .details-panel {
    width: 100%;
    max-width: none;
    top: auto;
    bottom: 0;
    right: 0;
    left: 0;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    max-height: 50%;
  }
}

/* Fullscreen mode */
.knowledge-graph.fullscreen {
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  z-index: var(--z-maximum) !important;
  border-radius: 0 !important;
  margin: 0 !important;
  background: var(--bg-primary);
}

.knowledge-graph.fullscreen .graph-container {
  flex: 1;
  min-height: calc(100vh - 250px);
}

.knowledge-graph.fullscreen .cytoscape-container {
  min-height: calc(100vh - 300px);
}

.control-separator {
  color: var(--border-default);
  font-size: 14px;
  margin: 0 4px;
}
</style>
