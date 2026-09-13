// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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
  system_prompt?: string | null;
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
  agent_type?: string | null;
  action?: string | null;
  command?: string | null;
  prompt?: PromptSpec | null;
  tools_allowed?: string[] | null;
  tools_denied: string[];
  inputs: Record<string, unknown>;
  expected_outputs?: Record<string, string> | null;
  outputs?: Record<string, unknown> | null;
  dependencies: string[];
  requires_approval: boolean;
  priority: number;
  timeout_seconds: number;
  max_retries: number;
  retry_count: number;
  capabilities_required: string[];
  estimated_duration_seconds: number;
  status: string;
  error?: string | null;
  start_time?: number | null;
  end_time?: number | null;
  skill_name?: string | null;
  skill_action?: string | null;
  skill_resolution_method?: string | null;
  skill_preference_note?: string | null;
  pending_skill_id?: string | null;
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
  created_at_epoch?: number | null;
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
  | 'warning'
  | 'medium'
  | 'degraded'
  | 'high'
  | 'error'
  | 'critical';

/** Generated alias — same union as `Severity` (#6689 / #7226) */
export type RiskLevel = Severity;

/** Generated from `autobot_shared.auth.permissions.Role` */
export type Role =
  | 'admin'
  | 'superadmin'
  | 'operator'
  | 'analyst'
  | 'editor'
  | 'user'
  | 'readonly';

/** Generated from `autobot_shared.auth.permissions.Permission` */
export type Permission =
  | 'api.read'
  | 'api.write'
  | 'api.admin'
  | 'knowledge.read'
  | 'knowledge.write'
  | 'knowledge.delete'
  | 'knowledge.manage'
  | 'analytics.view'
  | 'analytics.export'
  | 'analytics.manage'
  | 'analytics.logs'
  | 'agent.view'
  | 'agent.execute'
  | 'agent.manage'
  | 'agent.terminal'
  | 'workflow.view'
  | 'workflow.create'
  | 'workflow.execute'
  | 'workflow.manage'
  | 'files.view'
  | 'files.download'
  | 'files.upload'
  | 'files.delete'
  | 'files.manage'
  | 'security.view'
  | 'security.audit'
  | 'security.manage'
  | 'admin.users.read'
  | 'admin.users.write'
  | 'admin.config.read'
  | 'admin.config.write'
  | 'admin.system'
  | 'admin.reporting_line.write'
  | 'mcp.read'
  | 'mcp.execute'
  | 'mcp.manage'
  | 'mcp.browser.read'
  | 'mcp.browser.control'
  | 'mcp.database.read'
  | 'mcp.database.write'
  | 'mcp.git.read'
  | 'mcp.http.read'
  | 'mcp.http.write'
  | 'mcp.metrics.read'
  | 'mcp.desktop.read'
  | 'mcp.desktop.control'
  | 'batch.view'
  | 'batch.create'
  | 'batch.execute'
  | 'batch.manage'
  | 'sandbox.view'
  | 'sandbox.execute'
  | 'sandbox.manage'
  | 'service.management'
  | 'allow_shell_execute';
