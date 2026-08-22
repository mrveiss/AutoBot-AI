// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canvas node types (GH#13939).
 *
 * `WorkflowCanvas.vue` renders more than the workflow authoring node types:
 * Company OS reuses the same canvas to draw an organisation graph. The
 * authoring union (`WorkflowNode['type']`, owned by the workflow domain) is
 * deliberately left untouched — the canvas widens it here instead, so
 * `WorkflowBuilderView.vue` keeps emitting and receiving `WorkflowNode`.
 */

import type { WorkflowNode } from '@/composables/useWorkflowBuilder'

/** Node types the canvas can render — superset of the workflow authoring types. */
export type CanvasNodeType =
  | WorkflowNode['type']
  | 'org-person'
  | 'org-group'
  // #13963: a workflow a role runs, drawn on the org canvas as the
  // contextual entrance to the absorbed automation module.
  | 'org-process'
  // #14597: a tool one or more roles carry. One node per distinct tool name
  // (never one per role) — `buildToolCanvasNodes` folds the role -> tool
  // attachments that share a `tool_name` before this type is ever reached.
  | 'org-tool'

/** A node as the canvas sees it. `WorkflowNode` is assignable to this. */
export interface CanvasNode extends Omit<WorkflowNode, 'type'> {
  type: CanvasNodeType
}

/** One tab in the canvas tab strip. Consumers own the filtering. */
export interface CanvasTab {
  id: string
  label: string
}

/** Canvas geometry shared by the renderer and the layout builders. */
export const CANVAS_NODE_WIDTH = 240

/**
 * A node's effective height for geometry — hit-testing and port anchoring.
 *
 * Named because the renderer previously carried it as a bare `100` in the
 * connection hit-test while `240` was already a constant, so half the geometry
 * had a single source and half did not.
 */
export const CANVAS_NODE_HEIGHT = 100

/**
 * Where a connection attaches vertically: the node's mid-line.
 *
 * Derived rather than written as `50`, so it cannot drift from the height. The
 * two were independent literals before, which meant changing the height moved
 * every node while leaving every edge anchored to the old mid-line — a failure
 * that renders as edges detached from their nodes and fails no test.
 */
export const CANVAS_NODE_PORT_Y = CANVAS_NODE_HEIGHT / 2

/**
 * The pitch of the canvas's reference grid, in world units.
 *
 * This is the single definition behind three things that were independent
 * literals before (#14768): the CSS background the user actually sees, the
 * increment a dragged node snaps to, and the distance one arrow-key press
 * moves a node. The failure mode is the one #14690 already fixed for node
 * geometry — a grid the user can see, a snap that lands somewhere else, and
 * no test that can tell.
 */
export const CANVAS_GRID_SIZE = 20

/**
 * Quantise one world-space coordinate to the grid.
 *
 * Exported so tests can assert against the same rounding the component uses
 * rather than restating it, which is exactly the duplication #14726 records
 * for node width.
 */
export function snapToGrid(value: number): number {
  return Math.round(value / CANVAS_GRID_SIZE) * CANVAS_GRID_SIZE
}

/**
 * The next gridline strictly beyond `current` in the direction of `delta`.
 *
 * Used by the keyboard move path. Plain `snapToGrid(current + step)` would
 * overshoot from an off-grid start — a node at x=10 pressing ArrowRight would
 * jump to 40, skipping the gridline at 20 it was trying to reach. This moves
 * to the adjacent line instead, so the first press aligns and every press
 * after it advances exactly one cell.
 */
export function nextGridline(current: number, delta: number): number {
  if (delta === 0) return current
  return delta > 0
    ? Math.floor(current / CANVAS_GRID_SIZE) * CANVAS_GRID_SIZE + CANVAS_GRID_SIZE
    : Math.ceil(current / CANVAS_GRID_SIZE) * CANVAS_GRID_SIZE - CANVAS_GRID_SIZE
}

/**
 * Inner padding kept around the graph when fitting it to the viewport.
 *
 * Lives here rather than in the component because it is canvas geometry that
 * `WorkflowCanvas.zoomFit.test.ts` also has to reason about — the same reason
 * node width and height moved out (#14690, #14726). A test that restates a
 * layout constant is asserting the number it was told, not the behaviour.
 */
export const CANVAS_FIT_PADDING = 60
