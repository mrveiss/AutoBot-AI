// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
//
// AUTO-GENERATED — DO NOT EDIT
//
// Source: autobot-infrastructure/shared/scripts/gen_frontend_types.py
// Run `python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py`
// to regenerate. CI checks this file is in sync with the canonical
// Python dataclasses in `autobot_shared/workflow/types.py` (#7122).

/* eslint-disable */

/** Generated from `autobot_shared.workflow.types.PromptSpec` */
export interface PromptSpec {
  user_prompt: string;
  system_prompt: unknown;
  template_vars: Record<string, unknown>;
  version: string;
}

/** Generated from `autobot_shared.workflow.types.ExecutionStrategy` */
export type ExecutionStrategy =
  | 'sequential'
  | 'parallel'
  | 'pipeline'
  | 'collaborative'
  | 'adaptive';

/** Generated from `autobot_shared.workflow.types.WorkflowTask` */
export interface WorkflowTask {
  task_id: string;
  description: string;
  agent_type: unknown;
  action: unknown;
  command: unknown;
  prompt: unknown;
  tools_allowed: string[] | null;
  tools_denied: string[];
  inputs: Record<string, unknown>;
  expected_outputs: Record<string, string> | null;
  outputs: Record<string, unknown> | null;
  dependencies: string[];
  requires_approval: boolean;
  priority: number;
  timeout_seconds: number;
  max_retries: number;
  retry_count: number;
  capabilities_required: string[];
  estimated_duration_seconds: number;
  status: string;
  error: unknown;
  start_time: unknown;
  end_time: unknown;
  skill_name: unknown;
  skill_action: unknown;
  skill_resolution_method: unknown;
  pending_skill_id: unknown;
  preconditions: string[];
  effects: string[];
  metadata: Record<string, unknown>;
}

/** Generated from `autobot_shared.workflow.types.WorkflowPlan` */
export interface WorkflowPlan {
  plan_id: string;
  goal: string;
  tasks: WorkflowTask[];
  description: string;
  strategy: 'sequential' | 'parallel' | 'pipeline' | 'collaborative' | 'adaptive';
  dependencies_graph: Record<string, string[]>;
  estimated_total_duration_seconds: number;
  resource_requirements: Record<string, unknown>;
  success_criteria: string[];
  fallback_plans: WorkflowPlan[];
  approval_required: boolean;
  approved: boolean;
  status: string;
  is_goap_plan: boolean;
  goap_goal: string[];
  created_at_epoch: unknown;
  metadata: Record<string, unknown>;
}

/** Generated from `services.workflow_automation.models.WorkflowStepStatus` */
export type WorkflowStepStatus =
  | 'pending'
  | 'waiting_approval'
  | 'approved'
  | 'executing'
  | 'completed'
  | 'skipped'
  | 'failed'
  | 'paused';

/** Generated from `autobot_shared.status_enums.Severity` */
export type Severity =
  | 'unknown'
  | 'info'
  | 'minimal'
  | 'low'
  | 'medium'
  | 'high'
  | 'critical';

/** Generated alias — same union as `Severity` (#6689 / #7226) */
export type RiskLevel = Severity;
