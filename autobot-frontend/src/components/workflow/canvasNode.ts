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
export type CanvasNodeType = WorkflowNode['type'] | 'org-person' | 'org-group'

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
