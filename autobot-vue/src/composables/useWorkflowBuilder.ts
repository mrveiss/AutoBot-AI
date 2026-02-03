// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Workflow Builder Composable
 *
 * Provides reactive state and API integration for the Workflow Automation Builder.
 * Issue #585: GUI Integration - Workflow Automation Builder
 *
 * Backend APIs:
 * - /api/orchestrator/* - Enhanced multi-agent orchestration
 * - /api/workflow_automation/* - Workflow automation management
 */

import { ref, computed, reactive, onUnmounted, onMounted } from 'vue';
import { getBackendUrl } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';
import type { ApiResponse } from '@/types/api';
import { useWorkflowTemplates } from '@/composables/useWorkflowTemplates';
import type { WorkflowTemplateSummary, WorkflowTemplateDetail } from '@/types/workflowTemplates';

const logger = createLogger('useWorkflowBuilder');

// ==================================================================================
// TYPE DEFINITIONS
// ==================================================================================

/** Workflow step status */
export type WorkflowStepStatus =
  | 'pending'
  | 'waiting_approval'
  | 'approved'
  | 'executing'
  | 'completed'
  | 'skipped'
  | 'failed'
  | 'paused';

/** Automation execution modes */
export type AutomationMode = 'manual' | 'semi_automatic' | 'automatic';

/** Plan approval modes */
export type PlanApprovalMode = 'full_plan' | 'per_step' | 'hybrid' | 'auto_safe';

/** Plan approval status */
export type PlanApprovalStatus =
  | 'pending'
  | 'presented'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'modified'
  | 'timeout';

/** Execution strategy */
export type ExecutionStrategy =
  | 'sequential'
  | 'parallel'
  | 'pipeline'
  | 'collaborative'
  | 'adaptive';

/** Risk level */
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

/** Workflow step definition */
export interface WorkflowStep {
  step_id: string;
  command: string;
  description: string;
  explanation?: string;
  requires_confirmation: boolean;
  risk_level: RiskLevel;
  estimated_duration: number;
  dependencies?: string[];
  status: WorkflowStepStatus;
  execution_result?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}

/** Active workflow definition */
export interface ActiveWorkflow {
  workflow_id: string;
  name: string;
  description: string;
  session_id: string;
  steps: WorkflowStep[];
  current_step: number;
  total_steps: number;
  is_paused: boolean;
  is_cancelled: boolean;
  automation_mode: AutomationMode;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  user_interventions: Record<string, unknown>[];
}

/** Plan approval request */
export interface PlanApprovalRequest {
  workflow_id: string;
  plan_summary: string;
  total_steps: number;
  steps: WorkflowStep[];
  approval_mode: PlanApprovalMode;
  status: PlanApprovalStatus;
  risk_assessment?: string;
  estimated_total_duration: number;
  timeout_seconds: number;
  created_at?: string;
}

/** Workflow template */
export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  steps: Omit<WorkflowStep, 'step_id' | 'status'>[];
}

/** Execution strategy info */
export interface StrategyInfo {
  name: string;
  description: string;
  best_for: string;
}

/** Agent capability */
export interface AgentCapability {
  agent: string;
  capabilities: string[];
  performance: {
    reliability: number;
    total_tasks: number;
  };
}

/** Agent performance metrics */
export interface AgentPerformance {
  agent_name: string;
  total_tasks: number;
  successful_tasks: number;
  failed_tasks: number;
  average_duration: number;
  reliability_score: number;
}

/** Orchestration status */
export interface OrchestrationStatus {
  status: string;
  active_workflows: number;
  max_parallel_tasks: number;
  total_agents: number;
  capabilities: {
    execution_strategies: string[];
    agent_coordination: boolean;
    performance_tracking: boolean;
    automatic_failover: boolean;
    resource_optimization: boolean;
  };
}

/** Workflow execution result */
export interface WorkflowExecutionResult {
  type: 'workflow_orchestration' | 'direct_execution';
  workflow_id: string;
  workflow_response?: {
    workflow_preview: string[];
    strategy_used: string;
    execution_time: number;
  };
  result?: {
    response: string;
    response_text: string;
    messageType: string;
  };
  details: Record<string, unknown>;
}

/** Workflow plan */
export interface WorkflowPlan {
  plan_id: string;
  goal: string;
  strategy: ExecutionStrategy;
  estimated_duration: number;
  tasks: Array<{
    task_id: string;
    agent_type: string;
    action: string;
    priority: number;
    dependencies: string[];
    capabilities_required: string[];
  }>;
  success_criteria: string[];
  resource_requirements: Record<string, unknown>;
}

/** Workflow node for canvas */
export interface WorkflowNode {
  id: string;
  type: 'step' | 'condition' | 'parallel' | 'loop';
  position: { x: number; y: number };
  data: WorkflowStep | Record<string, unknown>;
  connections: string[];
}

// ==================================================================================
// API CLIENT
// ==================================================================================

class WorkflowBuilderApiClient {
  private baseUrl: string;
  private timeout: number;

  constructor() {
    this.baseUrl = getBackendUrl();
    this.timeout = 60000;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return {
          success: false,
          error: errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        };
      }

      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      clearTimeout(timeoutId);
      const message = error instanceof Error ? error.message : 'Unknown error';
      logger.error('API request failed:', { endpoint, error: message });
      return { success: false, error: message };
    }
  }

  // ==================================================================================
  // ORCHESTRATION API (/api/orchestrator)
  // ==================================================================================

  /** Execute a workflow with multi-agent orchestration */
  async executeWorkflow(
    goal: string,
    strategy?: ExecutionStrategy,
    context?: Record<string, unknown>,
    maxParallelTasks?: number
  ): Promise<ApiResponse<WorkflowExecutionResult>> {
    return this.request('/api/orchestrator/workflow/execute', {
      method: 'POST',
      body: JSON.stringify({
        goal,
        strategy,
        context,
        max_parallel_tasks: maxParallelTasks,
      }),
    });
  }

  /** Create a workflow plan without executing */
  async createWorkflowPlan(
    goal: string,
    context?: Record<string, unknown>
  ): Promise<ApiResponse<{ status: string; plan: WorkflowPlan; task_count: number }>> {
    return this.request('/api/orchestrator/workflow/plan', {
      method: 'POST',
      body: JSON.stringify({ goal, context }),
    });
  }

  /** Get active workflows */
  async getActiveOrchestrationWorkflows(): Promise<
    ApiResponse<{ status: string; active_count: number; workflows: ActiveWorkflow[] }>
  > {
    return this.request('/api/orchestrator/workflow/active');
  }

  /** Get agent performance metrics */
  async getAgentPerformance(): Promise<
    ApiResponse<{ status: string; performance_data: Record<string, AgentPerformance> }>
  > {
    return this.request('/api/orchestrator/agents/performance');
  }

  /** Get agent recommendations */
  async getAgentRecommendations(
    taskType: string,
    capabilitiesNeeded: string[]
  ): Promise<
    ApiResponse<{
      status: string;
      task_type: string;
      capabilities_requested: string[];
      recommended_agents: string[];
      agent_count: number;
    }>
  > {
    return this.request('/api/orchestrator/agents/recommend', {
      method: 'POST',
      body: JSON.stringify({
        task_type: taskType,
        capabilities_needed: capabilitiesNeeded,
      }),
    });
  }

  /** Get available execution strategies */
  async getExecutionStrategies(): Promise<
    ApiResponse<{ strategies: Record<string, StrategyInfo>; default: string }>
  > {
    return this.request('/api/orchestrator/strategies');
  }

  /** Get agent capabilities */
  async getAgentCapabilities(): Promise<
    ApiResponse<{
      capability_coverage: Record<string, number>;
      agents: Record<string, AgentCapability>;
      total_agents: number;
    }>
  > {
    return this.request('/api/orchestrator/capabilities');
  }

  /** Get orchestration system status */
  async getOrchestrationStatus(): Promise<ApiResponse<OrchestrationStatus>> {
    return this.request('/api/orchestrator/status');
  }

  /** Get example workflows */
  async getExampleWorkflows(): Promise<
    ApiResponse<{
      examples: Record<string, { goal: string; strategy: string; description: string }>;
      usage_tips: string[];
    }>
  > {
    return this.request('/api/orchestrator/examples');
  }

  // ==================================================================================
  // WORKFLOW AUTOMATION API (/api/workflow_automation)
  // ==================================================================================

  /** Create a new workflow */
  async createWorkflow(
    name: string,
    description: string,
    steps: Omit<WorkflowStep, 'step_id' | 'status'>[],
    sessionId: string,
    automationMode: AutomationMode = 'semi_automatic'
  ): Promise<ApiResponse<{ success: boolean; workflow_id: string; message: string }>> {
    return this.request('/api/workflow_automation/create_workflow', {
      method: 'POST',
      body: JSON.stringify({
        name,
        description,
        steps: steps.map((step) => ({
          command: step.command,
          description: step.description,
          explanation: step.explanation,
          requires_confirmation: step.requires_confirmation,
          risk_level: step.risk_level,
          dependencies: step.dependencies || [],
        })),
        session_id: sessionId,
        automation_mode: automationMode,
      }),
    });
  }

  /** Start workflow execution */
  async startWorkflow(
    workflowId: string
  ): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return this.request(`/api/workflow_automation/start_workflow/${workflowId}`, {
      method: 'POST',
    });
  }

  /** Control workflow execution */
  async controlWorkflow(
    workflowId: string,
    action: 'pause' | 'resume' | 'cancel' | 'approve_step' | 'skip_step',
    stepId?: string,
    userInput?: string
  ): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return this.request('/api/workflow_automation/control_workflow', {
      method: 'POST',
      body: JSON.stringify({
        workflow_id: workflowId,
        action,
        step_id: stepId,
        user_input: userInput,
      }),
    });
  }

  /** Get workflow status */
  async getWorkflowStatus(
    workflowId: string
  ): Promise<ApiResponse<{ success: boolean; workflow: ActiveWorkflow }>> {
    return this.request(`/api/workflow_automation/workflow_status/${workflowId}`);
  }

  /** Get all active workflows */
  async getActiveWorkflows(): Promise<
    ApiResponse<{ success: boolean; workflows: ActiveWorkflow[]; count: number }>
  > {
    return this.request('/api/workflow_automation/active_workflows');
  }

  /** Create workflow from natural language */
  async createWorkflowFromChat(
    userRequest: string,
    sessionId: string,
    autoStart: boolean = true,
    requireApproval: boolean = false,
    approvalMode: PlanApprovalMode = 'full_plan'
  ): Promise<
    ApiResponse<{
      success: boolean;
      workflow_id?: string;
      message: string;
      status?: string;
      plan?: PlanApprovalRequest;
    }>
  > {
    return this.request('/api/workflow_automation/create_from_chat', {
      method: 'POST',
      body: JSON.stringify({
        user_request: userRequest,
        session_id: sessionId,
        auto_start: autoStart,
        require_approval: requireApproval,
        approval_mode: approvalMode,
      }),
    });
  }

  /** Present plan for approval */
  async presentPlanForApproval(
    workflowId: string,
    approvalMode: PlanApprovalMode = 'full_plan',
    timeoutSeconds: number = 300
  ): Promise<
    ApiResponse<{
      success: boolean;
      workflow_id: string;
      status: string;
      plan: PlanApprovalRequest;
    }>
  > {
    return this.request(`/api/workflow_automation/present_plan/${workflowId}`, {
      method: 'POST',
      body: JSON.stringify({
        workflow_id: workflowId,
        approval_mode: approvalMode,
        include_risk_assessment: true,
        timeout_seconds: timeoutSeconds,
      }),
    });
  }

  /** Approve or reject plan */
  async approvePlan(
    workflowId: string,
    approved: boolean,
    approvalMode: PlanApprovalMode = 'full_plan',
    modifications?: string[],
    reason?: string
  ): Promise<
    ApiResponse<{
      success: boolean;
      workflow_id: string;
      status: string;
      message: string;
    }>
  > {
    return this.request('/api/workflow_automation/approve_plan', {
      method: 'POST',
      body: JSON.stringify({
        workflow_id: workflowId,
        approved,
        approval_mode: approvalMode,
        modifications,
        reason,
      }),
    });
  }

  /** Get pending approval */
  async getPendingApproval(
    workflowId: string
  ): Promise<
    ApiResponse<{
      success: boolean;
      workflow_id: string;
      has_pending_approval: boolean;
      approval: PlanApprovalRequest | null;
    }>
  > {
    return this.request(`/api/workflow_automation/pending_approval/${workflowId}`);
  }
}

// Singleton instance
const apiClient = new WorkflowBuilderApiClient();

// ==================================================================================
// COMPOSABLE
// ==================================================================================

export function useWorkflowBuilder() {
  // ==================================================================================
  // STATE
  // ==================================================================================

  // Loading states
  const loading = ref(false);
  const executingWorkflow = ref(false);
  const loadingStrategies = ref(false);
  const loadingCapabilities = ref(false);
  const loadingExamples = ref(false);

  // Error state
  const error = ref<string | null>(null);

  // Data state
  const activeWorkflows = ref<ActiveWorkflow[]>([]);
  const currentWorkflow = ref<ActiveWorkflow | null>(null);
  const workflowPlan = ref<WorkflowPlan | null>(null);
  const pendingApproval = ref<PlanApprovalRequest | null>(null);

  // Orchestration data
  const orchestrationStatus = ref<OrchestrationStatus | null>(null);
  const executionStrategies = ref<Record<string, StrategyInfo>>({});
  const agentCapabilities = ref<Record<string, AgentCapability>>({});
  const agentPerformance = ref<Record<string, AgentPerformance>>({});
  const exampleWorkflows = ref<Record<string, { goal: string; strategy: string; description: string }>>({});

  // Canvas state for visual builder
  const workflowNodes = ref<WorkflowNode[]>([]);
  const selectedNodeId = ref<string | null>(null);

  // WebSocket connection
  let wsConnection: WebSocket | null = null;
  const wsConnected = ref(false);

  // ==================================================================================
  // COMPUTED
  // ==================================================================================

  const hasActiveWorkflows = computed(() => activeWorkflows.value.length > 0);
  const isWorkflowPaused = computed(() => currentWorkflow.value?.is_paused ?? false);
  const currentStepIndex = computed(() => currentWorkflow.value?.current_step ?? 0);
  const totalSteps = computed(() => currentWorkflow.value?.total_steps ?? 0);
  const progress = computed(() => {
    if (totalSteps.value === 0) return 0;
    return Math.round((currentStepIndex.value / totalSteps.value) * 100);
  });

  const selectedNode = computed(() => {
    if (!selectedNodeId.value) return null;
    return workflowNodes.value.find((n) => n.id === selectedNodeId.value) || null;
  });

  // ==================================================================================
  // WORKFLOW TEMPLATES - API Integration (Issue #778)
  // ==================================================================================

  // Templates API composable
  const {
    templates: apiTemplates,
    loading: loadingApiTemplates,
    error: apiTemplatesError,
    fetchTemplates: fetchApiTemplates,
    createWorkflowFromTemplate: createFromApiTemplate,
    executeTemplate: executeApiTemplate
  } = useWorkflowTemplates();

  // Hardcoded fallback templates
  const builtInTemplates: WorkflowTemplate[] = [
    {
      id: 'system_update',
      name: 'System Update',
      description: 'Update and upgrade system packages',
      category: 'System',
      icon: 'fas fa-sync-alt',
      steps: [
        {
          command: 'sudo apt update',
          description: 'Update package repositories',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 30,
        },
        {
          command: 'sudo apt upgrade -y',
          description: 'Upgrade installed packages',
          risk_level: 'medium',
          requires_confirmation: true,
          estimated_duration: 120,
        },
        {
          command: 'sudo apt autoremove -y',
          description: 'Remove unnecessary packages',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 15,
        },
        {
          command: 'apt list --upgradable',
          description: 'Check for remaining updates',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 5,
        },
      ],
    },
    {
      id: 'dev_environment',
      name: 'Development Environment',
      description: 'Setup development environment with common tools',
      category: 'Development',
      icon: 'fas fa-code',
      steps: [
        {
          command: 'sudo apt update',
          description: 'Update system packages',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 30,
        },
        {
          command: 'sudo apt install -y git',
          description: 'Install Git version control',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 20,
        },
        {
          command: 'curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -',
          description: 'Setup Node.js repository',
          risk_level: 'medium',
          requires_confirmation: true,
          estimated_duration: 30,
        },
        {
          command: 'sudo apt install -y nodejs',
          description: 'Install Node.js and npm',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 45,
        },
        {
          command: 'sudo apt install -y python3 python3-pip',
          description: 'Install Python 3 and pip',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 30,
        },
        {
          command: 'git --version && node --version && python3 --version',
          description: 'Verify installations',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 5,
        },
      ],
    },
    {
      id: 'security_scan',
      name: 'Security Scan',
      description: 'Run security scanning workflow',
      category: 'Security',
      icon: 'fas fa-shield-alt',
      steps: [
        {
          command: 'sudo apt update',
          description: 'Update package database',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 30,
        },
        {
          command: 'sudo apt install -y nmap lynis',
          description: 'Install security scanning tools',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 60,
        },
        {
          command: 'sudo nmap -sS -O localhost',
          description: 'Scan local ports and services',
          risk_level: 'medium',
          requires_confirmation: true,
          estimated_duration: 120,
        },
        {
          command: 'sudo lynis audit system',
          description: 'Run system security audit',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 300,
        },
        {
          command: 'find /etc -perm -o=w -type f 2>/dev/null',
          description: 'Check for world-writable files in /etc',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 10,
        },
      ],
    },
    {
      id: 'backup_creation',
      name: 'Backup Creation',
      description: 'Create backups of important files',
      category: 'Backup',
      icon: 'fas fa-archive',
      steps: [
        {
          command: 'mkdir -p ~/backups/$(date +%Y%m%d)',
          description: 'Create dated backup directory',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 2,
        },
        {
          command: 'tar -czf ~/backups/$(date +%Y%m%d)/config_backup.tar.gz ~/.bashrc ~/.profile /etc/hosts',
          description: 'Backup configuration files',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 10,
        },
        {
          command: 'tar -czf ~/backups/$(date +%Y%m%d)/docs_backup.tar.gz ~/Documents',
          description: 'Backup documents directory',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 60,
        },
        {
          command: 'ls -la ~/backups/$(date +%Y%m%d)/',
          description: 'Verify backup files created',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 2,
        },
        {
          command: 'find ~/backups -type d -mtime +30 -exec rm -rf {} +',
          description: 'Clean up backups older than 30 days',
          risk_level: 'medium',
          requires_confirmation: true,
          estimated_duration: 5,
        },
      ],
    },
  ];

  // Templates with API fallback - use API templates if available, otherwise fallback to built-in
  const templates = computed<WorkflowTemplate[]>(() => {
    if (apiTemplates.value.length > 0) {
      // Convert API templates to WorkflowTemplate format
      return apiTemplates.value.map(apiTemplate => ({
        id: apiTemplate.id,
        name: apiTemplate.name,
        description: apiTemplate.description,
        category: apiTemplate.category,
        icon: apiTemplate.icon || getDefaultIconForCategory(apiTemplate.category),
        steps: 'steps' in apiTemplate
          ? (apiTemplate as WorkflowTemplateDetail).steps.map(step => ({
              command: step.command,
              description: step.description,
              risk_level: step.risk_level,
              requires_confirmation: step.requires_confirmation,
              estimated_duration: step.estimated_duration_seconds
            }))
          : []
      }));
    }
    return builtInTemplates;
  });

  // Helper to get default icon for category
  function getDefaultIconForCategory(category: string): string {
    const icons: Record<string, string> = {
      security: 'fas fa-shield-alt',
      research: 'fas fa-search',
      development: 'fas fa-code',
      system_admin: 'fas fa-server',
      analysis: 'fas fa-chart-bar',
      System: 'fas fa-cog',
      Development: 'fas fa-code',
      Security: 'fas fa-lock',
      Backup: 'fas fa-database'
    };
    return icons[category] || 'fas fa-tasks';
  }

  /** Load templates from API */
  async function loadTemplates(): Promise<void> {
    await fetchApiTemplates();
    logger.debug('Templates loaded from API:', apiTemplates.value.length);
  }

  // ==================================================================================
  // METHODS - ORCHESTRATION API
  // ==================================================================================

  /** Load orchestration system status */
  async function loadOrchestrationStatus(): Promise<void> {
    loading.value = true;
    error.value = null;

    const response = await apiClient.getOrchestrationStatus();
    if (response.success && response.data) {
      orchestrationStatus.value = response.data;
      logger.debug('Orchestration status loaded:', response.data);
    } else {
      error.value = response.error || 'Failed to load orchestration status';
      logger.error('Failed to load orchestration status:', response.error);
    }

    loading.value = false;
  }

  /** Load execution strategies */
  async function loadExecutionStrategies(): Promise<void> {
    loadingStrategies.value = true;

    const response = await apiClient.getExecutionStrategies();
    if (response.success && response.data) {
      executionStrategies.value = response.data.strategies;
      logger.debug('Strategies loaded:', response.data);
    } else {
      logger.error('Failed to load strategies:', response.error);
    }

    loadingStrategies.value = false;
  }

  /** Load agent capabilities */
  async function loadAgentCapabilities(): Promise<void> {
    loadingCapabilities.value = true;

    const response = await apiClient.getAgentCapabilities();
    if (response.success && response.data) {
      agentCapabilities.value = response.data.agents;
      logger.debug('Agent capabilities loaded:', response.data);
    } else {
      logger.error('Failed to load agent capabilities:', response.error);
    }

    loadingCapabilities.value = false;
  }

  /** Load agent performance metrics */
  async function loadAgentPerformance(): Promise<void> {
    const response = await apiClient.getAgentPerformance();
    if (response.success && response.data) {
      agentPerformance.value = response.data.performance_data;
      logger.debug('Agent performance loaded:', response.data);
    } else {
      logger.error('Failed to load agent performance:', response.error);
    }
  }

  /** Load example workflows */
  async function loadExampleWorkflows(): Promise<void> {
    loadingExamples.value = true;

    const response = await apiClient.getExampleWorkflows();
    if (response.success && response.data) {
      exampleWorkflows.value = response.data.examples;
      logger.debug('Example workflows loaded:', response.data);
    } else {
      logger.error('Failed to load example workflows:', response.error);
    }

    loadingExamples.value = false;
  }

  /** Execute workflow with orchestration */
  async function executeOrchestrationWorkflow(
    goal: string,
    strategy?: ExecutionStrategy,
    context?: Record<string, unknown>
  ): Promise<WorkflowExecutionResult | null> {
    executingWorkflow.value = true;
    error.value = null;

    const response = await apiClient.executeWorkflow(goal, strategy, context);
    executingWorkflow.value = false;

    if (response.success && response.data) {
      logger.info('Workflow executed:', response.data);
      return response.data;
    } else {
      error.value = response.error || 'Failed to execute workflow';
      logger.error('Workflow execution failed:', response.error);
      return null;
    }
  }

  /** Create workflow plan without executing */
  async function createPlan(
    goal: string,
    context?: Record<string, unknown>
  ): Promise<WorkflowPlan | null> {
    loading.value = true;
    error.value = null;

    const response = await apiClient.createWorkflowPlan(goal, context);
    loading.value = false;

    if (response.success && response.data) {
      workflowPlan.value = response.data.plan;
      logger.info('Workflow plan created:', response.data);
      return response.data.plan;
    } else {
      error.value = response.error || 'Failed to create workflow plan';
      logger.error('Plan creation failed:', response.error);
      return null;
    }
  }

  // ==================================================================================
  // METHODS - WORKFLOW AUTOMATION API
  // ==================================================================================

  /** Load active workflows */
  async function loadActiveWorkflows(): Promise<void> {
    loading.value = true;
    error.value = null;

    const response = await apiClient.getActiveWorkflows();
    if (response.success && response.data) {
      activeWorkflows.value = response.data.workflows;
      logger.debug('Active workflows loaded:', response.data);
    } else {
      error.value = response.error || 'Failed to load active workflows';
      logger.error('Failed to load active workflows:', response.error);
    }

    loading.value = false;
  }

  /** Get workflow status */
  async function getWorkflowStatus(workflowId: string): Promise<ActiveWorkflow | null> {
    const response = await apiClient.getWorkflowStatus(workflowId);
    if (response.success && response.data) {
      currentWorkflow.value = response.data.workflow;
      return response.data.workflow;
    }
    return null;
  }

  /** Create workflow from template */
  async function createWorkflowFromTemplate(
    template: WorkflowTemplate,
    sessionId: string,
    automationMode: AutomationMode = 'semi_automatic'
  ): Promise<string | null> {
    loading.value = true;
    error.value = null;

    const response = await apiClient.createWorkflow(
      template.name,
      template.description,
      template.steps,
      sessionId,
      automationMode
    );

    loading.value = false;

    if (response.success && response.data) {
      logger.info('Workflow created from template:', response.data);
      await loadActiveWorkflows();
      return response.data.workflow_id;
    } else {
      error.value = response.error || 'Failed to create workflow';
      logger.error('Workflow creation failed:', response.error);
      return null;
    }
  }

  /** Create workflow from natural language */
  async function createWorkflowFromNaturalLanguage(
    request: string,
    sessionId: string,
    requireApproval: boolean = true
  ): Promise<string | null> {
    loading.value = true;
    error.value = null;

    const response = await apiClient.createWorkflowFromChat(
      request,
      sessionId,
      !requireApproval,
      requireApproval
    );

    loading.value = false;

    if (response.success && response.data?.workflow_id) {
      if (response.data.plan) {
        pendingApproval.value = response.data.plan;
      }
      await loadActiveWorkflows();
      return response.data.workflow_id;
    } else {
      error.value = response.error || response.data?.message || 'Failed to create workflow';
      logger.error('Workflow creation from chat failed:', response.error);
      return null;
    }
  }

  /** Start workflow execution */
  async function startWorkflow(workflowId: string): Promise<boolean> {
    executingWorkflow.value = true;
    error.value = null;

    const response = await apiClient.startWorkflow(workflowId);
    executingWorkflow.value = false;

    if (response.success) {
      logger.info('Workflow started:', workflowId);
      await getWorkflowStatus(workflowId);
      return true;
    } else {
      error.value = response.error || 'Failed to start workflow';
      logger.error('Workflow start failed:', response.error);
      return false;
    }
  }

  /** Pause workflow */
  async function pauseWorkflow(workflowId: string): Promise<boolean> {
    const response = await apiClient.controlWorkflow(workflowId, 'pause');
    if (response.success) {
      logger.info('Workflow paused:', workflowId);
      await getWorkflowStatus(workflowId);
      return true;
    }
    return false;
  }

  /** Resume workflow */
  async function resumeWorkflow(workflowId: string): Promise<boolean> {
    const response = await apiClient.controlWorkflow(workflowId, 'resume');
    if (response.success) {
      logger.info('Workflow resumed:', workflowId);
      await getWorkflowStatus(workflowId);
      return true;
    }
    return false;
  }

  /** Cancel workflow */
  async function cancelWorkflow(workflowId: string): Promise<boolean> {
    const response = await apiClient.controlWorkflow(workflowId, 'cancel');
    if (response.success) {
      logger.info('Workflow cancelled:', workflowId);
      await loadActiveWorkflows();
      return true;
    }
    return false;
  }

  /** Approve workflow step */
  async function approveStep(workflowId: string, stepId: string): Promise<boolean> {
    const response = await apiClient.controlWorkflow(workflowId, 'approve_step', stepId);
    if (response.success) {
      logger.info('Step approved:', { workflowId, stepId });
      await getWorkflowStatus(workflowId);
      return true;
    }
    return false;
  }

  /** Skip workflow step */
  async function skipStep(workflowId: string, stepId: string): Promise<boolean> {
    const response = await apiClient.controlWorkflow(workflowId, 'skip_step', stepId);
    if (response.success) {
      logger.info('Step skipped:', { workflowId, stepId });
      await getWorkflowStatus(workflowId);
      return true;
    }
    return false;
  }

  /** Approve plan */
  async function approvePlan(workflowId: string): Promise<boolean> {
    const response = await apiClient.approvePlan(workflowId, true);
    if (response.success) {
      pendingApproval.value = null;
      logger.info('Plan approved:', workflowId);
      return true;
    }
    return false;
  }

  /** Reject plan */
  async function rejectPlan(workflowId: string, reason?: string): Promise<boolean> {
    const response = await apiClient.approvePlan(workflowId, false, 'full_plan', undefined, reason);
    if (response.success) {
      pendingApproval.value = null;
      logger.info('Plan rejected:', workflowId);
      return true;
    }
    return false;
  }

  // ==================================================================================
  // METHODS - CANVAS OPERATIONS
  // ==================================================================================

  /** Add node to canvas */
  function addNode(node: WorkflowNode): void {
    workflowNodes.value.push(node);
    logger.debug('Node added:', node);
  }

  /** Remove node from canvas */
  function removeNode(nodeId: string): void {
    workflowNodes.value = workflowNodes.value.filter((n) => n.id !== nodeId);
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = null;
    }
    logger.debug('Node removed:', nodeId);
  }

  /** Update node position */
  function updateNodePosition(nodeId: string, position: { x: number; y: number }): void {
    const node = workflowNodes.value.find((n) => n.id === nodeId);
    if (node) {
      node.position = position;
    }
  }

  /** Connect two nodes */
  function connectNodes(sourceId: string, targetId: string): void {
    const sourceNode = workflowNodes.value.find((n) => n.id === sourceId);
    if (sourceNode && !sourceNode.connections.includes(targetId)) {
      sourceNode.connections.push(targetId);
      logger.debug('Nodes connected:', { sourceId, targetId });
    }
  }

  /** Disconnect nodes */
  function disconnectNodes(sourceId: string, targetId: string): void {
    const sourceNode = workflowNodes.value.find((n) => n.id === sourceId);
    if (sourceNode) {
      sourceNode.connections = sourceNode.connections.filter((id) => id !== targetId);
    }
  }

  /** Clear canvas */
  function clearCanvas(): void {
    workflowNodes.value = [];
    selectedNodeId.value = null;
    logger.debug('Canvas cleared');
  }

  /** Export canvas to workflow steps */
  function exportCanvasToSteps(): WorkflowStep[] {
    return workflowNodes.value
      .filter((n) => n.type === 'step')
      .map((n, index) => ({
        step_id: n.id,
        ...(n.data as Omit<WorkflowStep, 'step_id'>),
        status: 'pending' as WorkflowStepStatus,
      }));
  }

  // ==================================================================================
  // METHODS - WEBSOCKET
  // ==================================================================================

  /** Connect to workflow WebSocket */
  function connectWebSocket(sessionId: string): void {
    if (wsConnection) {
      wsConnection.close();
    }

    const wsUrl = `${getBackendUrl().replace('http', 'ws')}/api/workflow_automation/workflow_ws/${sessionId}`;
    wsConnection = new WebSocket(wsUrl);

    wsConnection.onopen = () => {
      wsConnected.value = true;
      logger.info('WebSocket connected');
    };

    wsConnection.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (e) {
        logger.error('Failed to parse WebSocket message:', e);
      }
    };

    wsConnection.onerror = (event) => {
      logger.error('WebSocket error:', event);
    };

    wsConnection.onclose = () => {
      wsConnected.value = false;
      logger.info('WebSocket disconnected');
    };
  }

  /** Handle WebSocket messages */
  function handleWebSocketMessage(data: Record<string, unknown>): void {
    const messageType = data.type as string;

    switch (messageType) {
      case 'workflow_status_update':
        if (data.workflow) {
          currentWorkflow.value = data.workflow as ActiveWorkflow;
        }
        break;
      case 'step_completed':
        loadActiveWorkflows();
        break;
      case 'workflow_completed':
        loadActiveWorkflows();
        break;
      case 'approval_required':
        pendingApproval.value = data.approval as PlanApprovalRequest;
        break;
      default:
        logger.debug('Unhandled WebSocket message:', data);
    }
  }

  /** Disconnect WebSocket */
  function disconnectWebSocket(): void {
    if (wsConnection) {
      wsConnection.close();
      wsConnection = null;
    }
    wsConnected.value = false;
  }

  // ==================================================================================
  // LIFECYCLE
  // ==================================================================================

  onUnmounted(() => {
    disconnectWebSocket();
  });

  // ==================================================================================
  // RETURN
  // ==================================================================================

  return {
    // State
    loading,
    executingWorkflow,
    loadingStrategies,
    loadingCapabilities,
    loadingExamples,
    loadingApiTemplates,
    error,
    apiTemplatesError,
    activeWorkflows,
    currentWorkflow,
    workflowPlan,
    pendingApproval,
    orchestrationStatus,
    executionStrategies,
    agentCapabilities,
    agentPerformance,
    exampleWorkflows,
    workflowNodes,
    selectedNodeId,
    wsConnected,
    templates,
    builtInTemplates,

    // Computed
    hasActiveWorkflows,
    isWorkflowPaused,
    currentStepIndex,
    totalSteps,
    progress,
    selectedNode,

    // Orchestration methods
    loadOrchestrationStatus,
    loadExecutionStrategies,
    loadAgentCapabilities,
    loadAgentPerformance,
    loadExampleWorkflows,
    executeOrchestrationWorkflow,
    createPlan,

    // Template methods (Issue #778)
    loadTemplates,
    createFromApiTemplate,
    executeApiTemplate,

    // Workflow automation methods
    loadActiveWorkflows,
    getWorkflowStatus,
    createWorkflowFromTemplate,
    createWorkflowFromNaturalLanguage,
    startWorkflow,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    approveStep,
    skipStep,
    approvePlan,
    rejectPlan,

    // Canvas methods
    addNode,
    removeNode,
    updateNodePosition,
    connectNodes,
    disconnectNodes,
    clearCanvas,
    exportCanvasToSteps,

    // WebSocket methods
    connectWebSocket,
    disconnectWebSocket,
  };
}

export default useWorkflowBuilder;
