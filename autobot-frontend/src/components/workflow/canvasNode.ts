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
