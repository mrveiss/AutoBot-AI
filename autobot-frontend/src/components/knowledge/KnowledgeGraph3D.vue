<template>
  <div ref="container" class="graph3d-container">
    <div v-if="isEmpty" class="graph3d-empty">
      <i class="fas fa-project-diagram"></i>
      <p>No entities to display</p>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * KnowledgeGraph3D - Three.js 3D force-directed graph renderer for knowledge entities
 *
 * @description Renders entities and relations as an interactive 3D force graph using
 * 3d-force-graph (Three.js/WebGL). Receives pre-filtered data from KnowledgeGraph.vue
 * and emits node selection events back to the parent.
 *
 * @see KnowledgeGraph.vue - Parent component that owns data fetching and controls
 * @see Issue #3330 - 3D graph view toggle feature
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import ForceGraph3D from '3d-force-graph'
import SpriteText from 'three-spritetext'
import { getCssVar } from '@/composables/useCssVars'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeGraph3D')

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

interface GraphNode {
  id: string
  name: string
  type: string
  val: number
  entity: Entity
}

interface GraphLink {
  source: string
  target: string
  type: string
}

// ============================================================================
// Props & Emits
// ============================================================================

const props = defineProps<{
  entities: Entity[]
  edges: Relation[]
}>()

const emit = defineEmits<{
  (e: 'entity-selected', entity: Entity | null): void
}>()

// ============================================================================
// State
// ============================================================================

const container = ref<HTMLElement | null>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let graph: any = null

const isEmpty = computed(() => props.entities.length === 0)

// ============================================================================
// Color Mapping (mirrors KnowledgeGraph.vue palette)
// ============================================================================

function getNodeColor(type: string): string {
  const colorMap: Record<string, string> = {
    category: getCssVar('--color-primary', '#6366f1'),
    fact: getCssVar('--color-success', '#10b981'),
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

// ============================================================================
// Graph Data
// ============================================================================

function buildGraphData(): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodes: GraphNode[] = props.entities.map(e => ({
    id: e.id,
    name: e.name,
    type: e.type,
    val: 1 + Math.min((e.observations?.length || 0) * 0.5, 3),
    entity: e
  }))

  const nodeIds = new Set(nodes.map(n => n.id))
  const links: GraphLink[] = props.edges
    .filter(r => nodeIds.has(r.from) && nodeIds.has(r.to))
    .map(r => ({ source: r.from, target: r.to, type: r.type }))

  return { nodes, links }
}

// ============================================================================
// Graph Initialization
// ============================================================================

function initGraph(): void {
  if (!container.value) return

  const width = container.value.clientWidth
  const height = container.value.clientHeight

  graph = ForceGraph3D({ antialias: true, alpha: true })(container.value)
    .width(width)
    .height(height)
    .backgroundColor('#0f172a')
    .graphData(buildGraphData())
    // Nodes: colored sphere + floating sprite text label
    .nodeColor((node: object) => getNodeColor((node as GraphNode).type))
    .nodeVal((node: object) => (node as GraphNode).val)
    .nodeThreeObjectExtend(true)
    .nodeThreeObject((node: object) => {
      const n = node as GraphNode
      const sprite = new SpriteText(n.name)
      sprite.color = '#e2e8f0'
      sprite.textHeight = 5
      sprite.backgroundColor = 'rgba(15, 23, 42, 0.75)'
      sprite.padding = 2
      sprite.borderRadius = 3
      sprite.position.y = 12
      return sprite
    })
    // Links
    .linkColor(() => '#475569')
    .linkOpacity(0.5)
    .linkWidth(1)
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(1)
    .linkDirectionalParticleSpeed(0.004)
    // Interaction
    .onNodeClick((node: object | null) => {
      if (node) {
        emit('entity-selected', (node as GraphNode).entity)
      }
    })
    .onBackgroundClick(() => {
      emit('entity-selected', null)
    })

  logger.debug('3D graph initialized', { nodes: props.entities.length, links: props.edges.length })
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  if (!isEmpty.value) {
    initGraph()
  }
})

onUnmounted(() => {
  if (graph) {
    // Pause animation and release renderer resources
    graph.pauseAnimation()
    graph.renderer()?.dispose()
    graph = null
  }
})

// Rebuild graph data when filtered entities/edges change
watch(
  () => [props.entities, props.edges] as const,
  () => {
    if (!graph) {
      if (!isEmpty.value) initGraph()
      return
    }
    graph.graphData(buildGraphData())
  },
  { deep: true }
)
</script>

<style scoped>
.graph3d-container {
  width: 100%;
  height: 100%;
  min-height: 500px;
  position: relative;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: #0f172a;
}

.graph3d-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  color: var(--text-tertiary);
}

.graph3d-empty i {
  font-size: 3rem;
  opacity: 0.3;
}

.graph3d-empty p {
  font-size: var(--text-sm);
}
</style>
