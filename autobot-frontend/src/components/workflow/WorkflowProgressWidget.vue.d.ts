// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { DefineComponent } from 'vue'

declare const WorkflowProgressWidget: DefineComponent<
  {
    workflowId?: string
  },
  Record<string, never>,
  unknown
>

export default WorkflowProgressWidget
