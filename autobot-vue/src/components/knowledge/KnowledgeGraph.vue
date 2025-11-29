<template>
  <div class="knowledge-graph">
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
      </div>
    </div>

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

    <!-- Graph Visualization -->
    <div v-else class="graph-container" ref="graphContainer">
      <!-- SVG Canvas for Graph -->
      <svg
        ref="graphSvg"
        class="graph-svg"
        :viewBox="viewBox"
        @mousedown="startPan"
        @mousemove="handlePan"
        @mouseup="endPan"
        @mouseleave="endPan"
        @wheel.prevent="handleZoom"
      >
        <defs>
          <!-- Arrow marker for directed edges -->
          <marker
            id="arrowhead"
            markerWidth="10"
            markerHeight="7"
            refX="10"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#9ca3af" />
          </marker>
          <!-- Gradient for nodes -->
          <linearGradient id="nodeGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
          </linearGradient>
        </defs>

        <g :transform="`translate(${panOffset.x}, ${panOffset.y}) scale(${zoomLevel})`">
          <!-- Edges (Relations) -->
          <g class="edges">
            <g
              v-for="edge in graphEdges"
              :key="`edge-${edge.from}-${edge.to}`"
              class="edge-group"
            >
              <line
                :x1="getNodePosition(edge.from).x"
                :y1="getNodePosition(edge.from).y"
                :x2="getNodePosition(edge.to).x"
                :y2="getNodePosition(edge.to).y"
                class="edge"
                :class="{ highlighted: isEdgeHighlighted(edge) }"
                marker-end="url(#arrowhead)"
              />
              <text
                :x="(getNodePosition(edge.from).x + getNodePosition(edge.to).x) / 2"
                :y="(getNodePosition(edge.from).y + getNodePosition(edge.to).y) / 2 - 5"
                class="edge-label"
              >
                {{ edge.type }}
              </text>
            </g>
          </g>

          <!-- Nodes (Entities) -->
          <g class="nodes">
            <g
              v-for="entity in filteredEntities"
              :key="entity.id"
              class="node-group"
              :class="{
                selected: selectedEntity?.id === entity.id,
                highlighted: highlightedEntities.includes(entity.id),
                dimmed: highlightedEntities.length > 0 && !highlightedEntities.includes(entity.id)
              }"
              :transform="`translate(${getNodePosition(entity.id).x}, ${getNodePosition(entity.id).y})`"
              @click="selectEntity(entity)"
              @mouseenter="highlightConnected(entity)"
              @mouseleave="clearHighlight"
            >
              <!-- Node circle -->
              <circle
                :r="getNodeRadius(entity)"
                :fill="getNodeColor(entity.type)"
                class="node-circle"
              />
              <!-- Node icon -->
              <text
                dy="0.35em"
                class="node-icon"
                text-anchor="middle"
              >
                {{ getEntityIcon(entity.type) }}
              </text>
              <!-- Node label -->
              <text
                :y="getNodeRadius(entity) + 15"
                class="node-label"
                text-anchor="middle"
              >
                {{ truncateText(entity.name, 15) }}
              </text>
            </g>
          </g>
        </g>
      </svg>

      <!-- Zoom Controls -->
      <div class="zoom-controls">
        <button @click="zoomIn" title="Zoom in">
          <i class="fas fa-plus"></i>
        </button>
        <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
        <button @click="zoomOut" title="Zoom out">
          <i class="fas fa-minus"></i>
        </button>
        <button @click="resetView" title="Reset view">
          <i class="fas fa-expand"></i>
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
            <button @click="expandEntity(selectedEntity)" class="action-btn">
              <i class="fas fa-expand-arrows-alt"></i>
              Expand
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
import { ref, computed, onMounted, watch } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'

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

interface NodePosition {
  x: number
  y: number
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
const highlightedEntities = ref<string[]>([])
const searchQuery = ref('')
const selectedType = ref('')
const graphDepth = ref(2)
const layoutMode = ref<'force' | 'grid'>('force')
const showCreateModal = ref(false)

// New entity form
const newEntity = ref<NewEntity>({
  name: '',
  type: '',
  observations: ''
})

// Viewport state
const graphContainer = ref<HTMLElement | null>(null)
const graphSvg = ref<SVGElement | null>(null)
const zoomLevel = ref(1)
const panOffset = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const lastPanPoint = ref({ x: 0, y: 0 })
const viewBox = ref('0 0 1000 600')

// Node positions cache
const nodePositions = ref<Map<string, NodePosition>>(new Map())

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
// Methods - Data Fetching
// ============================================================================

async function refreshGraph() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    // Fetch all entities
    const entitiesResponse = await apiClient.get('/api/memory/entities/all')
    const parsedResponse = await parseApiResponse(entitiesResponse)

    // Handle standard API response format: { success: true, data: { entities: [...] } }
    const entitiesData = parsedResponse?.data || parsedResponse

    if (entitiesData?.entities) {
      entities.value = entitiesData.entities
    } else if (Array.isArray(entitiesData)) {
      entities.value = entitiesData
    }

    // Calculate node positions
    calculateLayout()

    // Fetch relations for each entity
    await fetchRelations()

  } catch (error) {
    console.error('Failed to fetch graph data:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Failed to load graph'
  } finally {
    isLoading.value = false
  }
}

async function fetchRelations() {
  const allRelations: Relation[] = []

  for (const entity of entities.value) {
    try {
      const response = await apiClient.get(`/api/memory/entities/${entity.id}/relations`)
      const parsedResponse = await parseApiResponse(response)

      // Handle standard API response format: { success: true, data: { related_entities: [...] } }
      const responseData = parsedResponse?.data || parsedResponse

      // Backend returns related_entities with relation metadata
      if (responseData?.related_entities) {
        // Transform related_entities into Relation objects
        for (const relatedEntity of responseData.related_entities) {
          allRelations.push({
            from: entity.id,
            to: relatedEntity.entity?.id || relatedEntity.id,
            type: relatedEntity.relation_type || relatedEntity.type || 'relates_to',
            strength: relatedEntity.strength || 1.0
          })
        }
      } else if (responseData?.relations) {
        // Fallback: backend might return relations directly
        allRelations.push(...responseData.relations)
      }
    } catch {
      // Silently skip entities without relations
      console.debug(`No relations for entity ${entity.id}`)
    }
  }

  // Deduplicate relations
  const relationSet = new Set<string>()
  relations.value = allRelations.filter(r => {
    const key = `${r.from}-${r.to}-${r.type}`
    if (relationSet.has(key)) return false
    relationSet.add(key)
    return true
  })
}

async function createEntity() {
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

    // Handle standard API response format: { success: true, data: {...entity...} }
    const responseData = parsedResponse?.data || parsedResponse

    // Backend returns the entity directly in data field
    if (responseData?.id && responseData?.name) {
      entities.value.push(responseData)
      calculateLayout()
    } else if (responseData?.entity) {
      // Fallback: entity might be nested
      entities.value.push(responseData.entity)
      calculateLayout()
    }

    showCreateModal.value = false
    newEntity.value = { name: '', type: '', observations: '' }
  } catch (error) {
    console.error('Failed to create entity:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Failed to create entity'
  } finally {
    isCreating.value = false
  }
}

// ============================================================================
// Methods - Layout
// ============================================================================

function calculateLayout() {
  const width = 1000
  const height = 600
  const padding = 80

  if (layoutMode.value === 'grid') {
    calculateGridLayout(width, height, padding)
  } else {
    calculateForceLayout(width, height, padding)
  }
}

function calculateGridLayout(width: number, height: number, padding: number) {
  const count = filteredEntities.value.length
  if (count === 0) return

  const cols = Math.ceil(Math.sqrt(count))
  const rows = Math.ceil(count / cols)
  const cellWidth = (width - 2 * padding) / cols
  const cellHeight = (height - 2 * padding) / rows

  filteredEntities.value.forEach((entity, idx) => {
    const col = idx % cols
    const row = Math.floor(idx / cols)
    nodePositions.value.set(entity.id, {
      x: padding + cellWidth * (col + 0.5),
      y: padding + cellHeight * (row + 0.5)
    })
  })
}

function calculateForceLayout(width: number, height: number, padding: number) {
  const count = filteredEntities.value.length
  if (count === 0) return

  // Simple circular layout as fallback (proper force simulation would require d3)
  const centerX = width / 2
  const centerY = height / 2
  const radius = Math.min(width, height) / 2 - padding

  filteredEntities.value.forEach((entity, idx) => {
    const angle = (2 * Math.PI * idx) / count - Math.PI / 2
    nodePositions.value.set(entity.id, {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle)
    })
  })
}

function toggleLayout() {
  layoutMode.value = layoutMode.value === 'force' ? 'grid' : 'force'
  calculateLayout()
}

function getNodePosition(entityId: string): NodePosition {
  return nodePositions.value.get(entityId) || { x: 500, y: 300 }
}

function getNodeRadius(entity: Entity): number {
  // Size based on number of observations
  const baseRadius = 25
  const obsCount = entity.observations?.length || 0
  return baseRadius + Math.min(obsCount * 2, 15)
}

// ============================================================================
// Methods - Visualization
// ============================================================================

function getNodeColor(type: string): string {
  const colors: Record<string, string> = {
    conversation: '#3b82f6',
    bug_fix: '#ef4444',
    feature: '#10b981',
    decision: '#f59e0b',
    task: '#8b5cf6',
    user_preference: '#ec4899',
    context: '#6366f1',
    learning: '#14b8a6',
    research: '#f97316',
    implementation: '#06b6d4'
  }
  return colors[type] || '#6b7280'
}

function getEntityIcon(type: string): string {
  const icons: Record<string, string> = {
    conversation: '💬',
    bug_fix: '🐛',
    feature: '✨',
    decision: '⚖️',
    task: '📋',
    user_preference: '👤',
    context: '📌',
    learning: '📚',
    research: '🔬',
    implementation: '💻'
  }
  return icons[type] || '📄'
}

function formatTypeName(type: string): string {
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 1) + '…'
}

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

// ============================================================================
// Methods - Interactions
// ============================================================================

function selectEntity(entity: Entity) {
  selectedEntity.value = selectedEntity.value?.id === entity.id ? null : entity
}

function highlightConnected(entity: Entity) {
  const connected = new Set<string>([entity.id])

  relations.value.forEach(r => {
    if (r.from === entity.id) connected.add(r.to)
    if (r.to === entity.id) connected.add(r.from)
  })

  highlightedEntities.value = Array.from(connected)
}

function clearHighlight() {
  highlightedEntities.value = []
}

function isEdgeHighlighted(edge: Relation): boolean {
  return highlightedEntities.value.includes(edge.from) &&
         highlightedEntities.value.includes(edge.to)
}

function getEntityRelations(entityId: string): Relation[] {
  return relations.value.filter(r => r.from === entityId || r.to === entityId)
}

function getEntityName(entityId: string): string {
  const entity = entities.value.find(e => e.id === entityId)
  return entity?.name || entityId
}

function navigateToEntity(relation: Relation) {
  const targetId = relation.from === selectedEntity.value?.id ? relation.to : relation.from
  const target = entities.value.find(e => e.id === targetId)
  if (target) {
    selectEntity(target)
    focusOnEntity(target)
  }
}

function focusOnEntity(entity: Entity) {
  const pos = getNodePosition(entity.id)
  panOffset.value = {
    x: 500 - pos.x * zoomLevel.value,
    y: 300 - pos.y * zoomLevel.value
  }
}

function expandEntity(entity: Entity) {
  // Placeholder for expanding to show more connected entities
  console.log('Expand entity:', entity.id)
}

// ============================================================================
// Methods - Search & Filter
// ============================================================================

function handleSearch() {
  // Debounced search handled by computed
}

function clearSearch() {
  searchQuery.value = ''
}

function filterEntities() {
  // Filtering handled by computed
  calculateLayout()
}

function filterByType(type: string) {
  selectedType.value = selectedType.value === type ? '' : type
  calculateLayout()
}

// ============================================================================
// Methods - Pan & Zoom
// ============================================================================

function startPan(event: MouseEvent) {
  if (event.button !== 0) return
  isPanning.value = true
  lastPanPoint.value = { x: event.clientX, y: event.clientY }
}

function handlePan(event: MouseEvent) {
  if (!isPanning.value) return

  const dx = event.clientX - lastPanPoint.value.x
  const dy = event.clientY - lastPanPoint.value.y

  panOffset.value = {
    x: panOffset.value.x + dx,
    y: panOffset.value.y + dy
  }

  lastPanPoint.value = { x: event.clientX, y: event.clientY }
}

function endPan() {
  isPanning.value = false
}

function handleZoom(event: WheelEvent) {
  const delta = event.deltaY > 0 ? -0.1 : 0.1
  const newZoom = Math.max(0.2, Math.min(3, zoomLevel.value + delta))
  zoomLevel.value = newZoom
}

function zoomIn() {
  zoomLevel.value = Math.min(3, zoomLevel.value + 0.2)
}

function zoomOut() {
  zoomLevel.value = Math.max(0.2, zoomLevel.value - 0.2)
}

function resetView() {
  zoomLevel.value = 1
  panOffset.value = { x: 0, y: 0 }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  refreshGraph()
})

// Watch for layout mode changes
watch(layoutMode, () => {
  calculateLayout()
})
</script>

<style scoped>
.knowledge-graph {
  padding: 1.5rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Header */
.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e5e7eb;
}

.header-content h3 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-content h3 i {
  color: #667eea;
}

.header-description {
  color: #6b7280;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

/* Action Buttons */
.action-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  border-color: transparent;
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.action-btn.refresh {
  border-color: #667eea;
  color: #667eea;
}

/* Error Notification */
.error-notification {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-left: 4px solid #ef4444;
  border-radius: 0.5rem;
  color: #991b1b;
}

.error-notification i.fa-exclamation-circle {
  color: #ef4444;
}

.error-notification span {
  flex: 1;
  font-size: 0.875rem;
}

.close-btn {
  background: none;
  border: none;
  padding: 0.25rem;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.close-btn:hover {
  opacity: 1;
}

/* Controls */
.graph-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.75rem;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.control-group label {
  font-size: 0.875rem;
  color: #6b7280;
  font-weight: 500;
}

.search-group {
  flex: 1;
  min-width: 200px;
  max-width: 300px;
  position: relative;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 0.5rem 0.75rem;
}

.search-group input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 0.875rem;
  width: 100%;
  background: transparent;
}

.search-group .clear-btn {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.75rem;
  color: #9ca3af;
}

.control-group select {
  padding: 0.375rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: white;
  cursor: pointer;
}

.stats-summary {
  margin-left: auto;
  display: flex;
  gap: 1rem;
}

.stats-summary .stat {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #6b7280;
}

.node-icon {
  color: #667eea;
}

.edge-icon {
  color: #9ca3af;
}

/* Loading State */
.loading-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  color: #6b7280;
}

.loading-state .spinner {
  font-size: 2rem;
  color: #667eea;
}

/* Empty State */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 3rem;
  text-align: center;
}

.empty-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea20, #764ba220);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  color: #667eea;
}

.empty-state h4 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.empty-state p {
  color: #6b7280;
  font-size: 0.875rem;
}

/* Graph Container */
.graph-container {
  flex: 1;
  position: relative;
  background: linear-gradient(135deg, #f0f4ff, #faf5ff);
  border-radius: 0.75rem;
  overflow: hidden;
  min-height: 400px;
}

.graph-svg {
  width: 100%;
  height: 100%;
  cursor: grab;
}

.graph-svg:active {
  cursor: grabbing;
}

/* Edges */
.edge {
  stroke: #d1d5db;
  stroke-width: 2;
  fill: none;
  transition: stroke 0.2s, stroke-width 0.2s;
}

.edge.highlighted {
  stroke: #667eea;
  stroke-width: 3;
}

.edge-label {
  font-size: 10px;
  fill: #9ca3af;
  text-anchor: middle;
}

/* Nodes */
.node-group {
  cursor: pointer;
  transition: transform 0.2s;
}

.node-group:hover {
  transform: scale(1.1);
}

.node-group.selected .node-circle {
  stroke: #1f2937;
  stroke-width: 3;
}

.node-group.dimmed {
  opacity: 0.3;
}

.node-group.highlighted {
  opacity: 1;
}

.node-circle {
  stroke: white;
  stroke-width: 2;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.15));
  transition: stroke 0.2s, filter 0.2s;
}

.node-icon {
  font-size: 16px;
  fill: white;
  pointer-events: none;
}

.node-label {
  font-size: 11px;
  fill: #374151;
  font-weight: 500;
  pointer-events: none;
}

/* Zoom Controls */
.zoom-controls {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: white;
  padding: 0.5rem;
  border-radius: 0.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.zoom-controls button {
  width: 32px;
  height: 32px;
  border: 1px solid #e5e7eb;
  background: white;
  border-radius: 0.375rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  transition: all 0.2s;
}

.zoom-controls button:hover {
  background: #f3f4f6;
  color: #1f2937;
}

.zoom-level {
  font-size: 0.75rem;
  color: #6b7280;
  min-width: 40px;
  text-align: center;
}

/* Details Panel */
.details-panel {
  position: absolute;
  top: 1rem;
  right: 1rem;
  width: 320px;
  max-height: calc(100% - 2rem);
  background: white;
  border-radius: 0.75rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
}

.panel-header h4 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1rem;
  font-weight: 600;
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
  padding: 1rem;
  overflow-y: auto;
  flex: 1;
}

.info-section {
  margin-bottom: 1rem;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #f3f4f6;
}

.info-row label {
  font-size: 0.75rem;
  color: #6b7280;
  font-weight: 500;
}

.info-row code {
  font-size: 0.75rem;
  background: #f3f4f6;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.type-badge {
  font-size: 0.75rem;
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.observations-section,
.relations-section {
  margin-bottom: 1rem;
}

.observations-section h5,
.relations-section h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.observations-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.observations-list li {
  font-size: 0.8125rem;
  color: #6b7280;
  padding: 0.5rem;
  background: #f9fafb;
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
}

.relations-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.relations-list li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  padding: 0.5rem;
  background: #f9fafb;
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: background 0.2s;
}

.relations-list li:hover {
  background: #e5e7eb;
}

.relation-type {
  background: #667eea20;
  color: #667eea;
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
}

.relation-target {
  color: #374151;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.relation-target i {
  font-size: 0.625rem;
  color: #9ca3af;
}

.panel-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid #f3f4f6;
}

.panel-actions .action-btn {
  flex: 1;
  justify-content: center;
  font-size: 0.8125rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 0.75rem;
  width: 90%;
  max-width: 480px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
}

.modal-header h4 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.125rem;
  font-weight: 600;
}

.modal-header .close-btn {
  color: white;
}

.entity-form {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
  margin-bottom: 0.375rem;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  transition: border-color 0.2s;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

/* Legend */
.graph-legend {
  padding: 1rem;
  background: white;
  border-radius: 0.75rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.graph-legend h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.75rem;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  background: #f9fafb;
  border-radius: 1rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.legend-item:hover {
  background: #f3f4f6;
}

.legend-item.active {
  background: #667eea20;
  border: 1px solid #667eea;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-label {
  color: #374151;
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
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
    gap: 1rem;
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
    border-radius: 0.75rem 0.75rem 0 0;
    max-height: 50%;
  }
}
</style>
