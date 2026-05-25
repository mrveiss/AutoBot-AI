<template>
  <div ref="container" class="graph3d-container">
    <div v-if="isEmpty" class="graph3d-empty">
      <Icon name="project-diagram" />
      <p>{{ $t('knowledge.graph.noEntities3D') }}</p>
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
 * @see Issue #3363 - WebGL teardown, i18n, shallowRef typing, nextTick fixes
 * @see Issue #4004 - Replace deep watch with length-based watch for performance
 *
 * @author mrveiss
 * @copyright (c) 2026 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss

import Icon from '@/components/ui/Icon.vue'
import { ref, shallowRef, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph'
import SpriteText from 'three-spritetext'
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore – 'three' ships without bundled type declarations in this version; types are provided transitively via 3d-force-graph
import * as THREE from 'three'
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
// shallowRef prevents Vue from deeply observing the heavy Three.js instance.
// Issue #704 pattern: same rationale as KnowledgeGraph.vue shallowRef<Core>
// Issue #3363: typed with ForceGraph3DInstance instead of any
const graph = shallowRef<ForceGraph3DInstance | null>(null)
// Issue #3370: ResizeObserver tracks container size changes; disconnected in disposeGraph()
let resizeObserver: ResizeObserver | null = null

const isEmpty = computed(() => props.entities.length === 0)

// ============================================================================
// Color Mapping (mirrors KnowledgeGraph.vue palette)
// Issue #704: All colors use CSS custom properties for theming support
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

  const width = container.value.clientWidth || container.value.offsetWidth
  const height = container.value.clientHeight || container.value.offsetHeight || 500

  // new ForceGraph3D(element, config) per IForceGraph3D constructor signature
  graph.value = new ForceGraph3D(container.value, { rendererConfig: { antialias: true, alpha: true } })
    .width(width)
    .height(height)
    .backgroundColor(getCssVar('--bg-primary', '#0f172a'))
    .graphData(buildGraphData())
    // Nodes: colored sphere + floating sprite text label
    .nodeColor((node: object) => getNodeColor((node as GraphNode).type))
    .nodeVal((node: object) => (node as GraphNode).val)
    .nodeThreeObjectExtend(true)
    .nodeThreeObject((node: object) => {
      const n = node as GraphNode
      const sprite = new SpriteText(n.name)
      sprite.color = getCssVar('--text-primary', '#e2e8f0')
      sprite.textHeight = 5
      sprite.backgroundColor = 'rgba(15, 23, 42, 0.75)'
      sprite.padding = 2
      sprite.borderRadius = 3
      // SpriteText extends THREE.Sprite — position is inherited from Object3D
      ;(sprite as unknown as THREE.Sprite).position.y = 12
      return sprite
    })
    // Links
    .linkColor(() => getCssVar('--border-default', '#475569'))
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

  // Issue #3370: update canvas dimensions whenever the container resizes
  resizeObserver = new ResizeObserver((entries) => {
    const rect = entries[0]?.contentRect
    if (graph.value && rect) {
      graph.value.width(Math.floor(rect.width)).height(Math.floor(rect.height))
      logger.debug('3D graph resized', { width: Math.floor(rect.width), height: Math.floor(rect.height) })
    }
  })
  resizeObserver.observe(container.value)

  logger.debug('3D graph initialized', { nodes: props.entities.length, links: props.edges.length })
}

/**
 * Fully disposes all Three.js GPU resources to prevent memory leaks.
 * Issue #3363: renderer.dispose() alone does not release geometry/material buffers.
 * Issue #3399: textures attached to materials must also be disposed to release GPU memory
 *   when toggling 2D/3D view repeatedly.
 */
function disposeGraph(): void {
  // Issue #3370: disconnect before tearing down the graph to avoid stale callbacks
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }

  if (!graph.value) return

  graph.value.pauseAnimation()

  const scene = graph.value.scene()
  if (scene) {
    scene.traverse((obj: THREE.Object3D) => {
      const mesh = obj as THREE.Mesh
      mesh.geometry?.dispose()
      const materials = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
      materials.forEach((m: THREE.Material) => {
        // Dispose any textures referenced by this material before releasing the material itself.
        // Issue #3399: omitting this step leaks GPU texture memory on each 2D/3D toggle.
        for (const value of Object.values(m as unknown as Record<string, unknown>)) {
          if (value instanceof THREE.Texture) {
            (value as THREE.Texture).dispose()
          }
        }
        m.dispose()
      })
    })
  }

  const renderer = graph.value.renderer()
  if (renderer) {
    renderer.forceContextLoss()
    renderer.dispose()
  }

  graph.value = null
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  // nextTick ensures the container has non-zero dimensions before initGraph reads them.
  // Issue #3363: fixes 0×0 canvas on initial mount of conditionally-rendered component.
  if (!isEmpty.value) {
    nextTick(() => initGraph())
  }
})

onUnmounted(() => {
  disposeGraph()
})

// Rebuild graph data when filtered entities/edges change.
// Issue #4004: Replace deep watch with length-based watch for performance.
// Watching array length is a lightweight proxy for data changes, avoiding 40-80ms
// deep comparison overhead on 1000+ node graphs. The graph is completely rebuilt
// on each data change, so we only need to detect when the arrays change, not which
// specific properties mutated within each entity.
watch(
  () => [props.entities?.length ?? 0, props.edges?.length ?? 0] as const,
  async () => {
    if (!graph.value) {
      if (!isEmpty.value) {
        await nextTick()
        initGraph()
      }
      return
    }
    graph.value.graphData(buildGraphData())
  }
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
  background: var(--bg-primary);
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
  font-size: var(--text-5xl);
  opacity: 0.3;
}

.graph3d-empty p {
  font-size: var(--text-sm);
}
</style>
