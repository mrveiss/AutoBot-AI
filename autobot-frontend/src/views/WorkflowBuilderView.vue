<template>
  <div class="workflow-builder-view">
    <!-- Sidebar Navigation - Issue #901: Technical Precision Design -->
    <aside class="workflow-sidebar">
      <div class="sidebar-header">
        <h3>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path>
          </svg>
          Workflow Builder
        </h3>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav" aria-label="Workflow builder navigation">
        <button
          class="category-item"
          :class="{ active: activeSection === 'overview' }"
          @click="activeSection = 'overview'"
          role="button"
          aria-label="View workflow overview"
          tabindex="0"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path>
          </svg>
          <span>Overview</span>
        </button>

        <div class="category-divider">
          <span>Build</span>
        </div>

        <button
          class="category-item"
          :class="{ active: activeSection === 'canvas' }"
          @click="activeSection = 'canvas'"
          role="button"
          aria-label="Open visual workflow builder"
          tabindex="0"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 12a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1v-7z"></path>
          </svg>
          <span>Visual Builder</span>
        </button>

        <button
          class="category-item"
          :class="{ active: activeSection === 'templates' }"
          @click="activeSection = 'templates'"
          role="button"
          aria-label="Browse workflow templates"
          tabindex="0"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
          </svg>
          <span>Templates</span>
          <span class="count" aria-label="{{ templates.length }} templates">{{ templates.length }}</span>
        </button>

        <button
          class="category-item"
          :class="{ active: activeSection === 'natural-language' }"
          @click="activeSection = 'natural-language'"
          role="button"
          aria-label="Natural language workflow builder"
          tabindex="0"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
          </svg>
          <span>Natural Language</span>
        </button>

        <div class="category-divider">
          <span>Execute</span>
        </div>

        <button
          class="category-item"
          :class="{ active: activeSection === 'runner' }"
          @click="activeSection = 'runner'"
          role="button"
          aria-label="Workflow runner"
          tabindex="0"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>Runner</span>
          <span class="count active-badge" v-if="hasActiveWorkflows" :aria-label="`${activeWorkflows.length} active workflows`">
            {{ activeWorkflows.length }}
          </span>
        </button>

        <div
          class="category-item"
          :class="{ active: activeSection === 'history' }"
          @click="activeSection = 'history'"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>History</span>
        </div>

        <button
          class="category-item"
          :class="{ active: activeSection === 'gui-automation' }"
          @click="activeSection = 'gui-automation'"
          role="button"
          aria-label="GUI automation from screen capture"
          tabindex="0"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          <span>GUI Automation</span>
        </button>

        <div class="category-divider">
          <span>Orchestration</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'orchestration' }"
          @click="activeSection = 'orchestration'"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
          </svg>
          <span>Visualizer</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'agents' }"
          @click="activeSection = 'agents'"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
          </svg>
          <span>Agents</span>
        </div>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="refreshAll" class="btn-refresh" :disabled="loading">
          <svg class="refresh-icon" :class="{ 'spinning': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
          </svg>
          Refresh
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="workflow-content">
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ sectionTitle }}</h2>
          <span class="subtitle">{{ sectionDescription }}</span>
        </div>
        <div class="header-actions">
          <div class="status-badge" :class="systemStatusClass">
            <i :class="statusIcon"></i>
            <span>{{ statusLabel }}</span>
          </div>
        </div>
      </header>

      <!-- Loading State -->
      <div v-if="loading && !hasData" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>Loading workflow services...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-container">
        <div class="error-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <h3>Failed to Load Data</h3>
        <p>{{ error }}</p>
        <button @click="refreshAll" class="btn-primary">
          <i class="fas fa-redo"></i> Retry
        </button>
      </div>

      <!-- Content Sections -->
      <div v-else class="content-body">
        <!-- Overview Section -->
        <section v-if="activeSection === 'overview'" class="section-overview">
          <div class="stats-grid">
            <div class="stat-card" :class="{ active: orchestrationHealthy }">
              <div class="stat-icon" :class="orchestrationHealthy ? 'healthy' : 'unhealthy'">
                <i class="fas fa-cogs"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ orchestrationHealthy ? 'Ready' : 'Offline' }}</span>
                <span class="stat-label">Orchestration</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-tasks"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ activeWorkflows.length }}</span>
                <span class="stat-label">Active Workflows</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-users"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ totalAgents }}</span>
                <span class="stat-label">Available Agents</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-layer-group"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ Object.keys(executionStrategies).length }}</span>
                <span class="stat-label">Strategies</span>
              </div>
            </div>
          </div>

          <div class="overview-sections">
            <!-- Quick Actions Card -->
            <div class="overview-card">
              <h4><i class="fas fa-bolt"></i> Quick Actions</h4>
              <div class="quick-actions-grid">
                <button class="quick-action" @click="activeSection = 'canvas'">
                  <i class="fas fa-plus-circle"></i>
                  <span>New Workflow</span>
                </button>
                <button class="quick-action" @click="activeSection = 'templates'">
                  <i class="fas fa-clone"></i>
                  <span>Use Template</span>
                </button>
                <button class="quick-action" @click="activeSection = 'natural-language'">
                  <i class="fas fa-magic"></i>
                  <span>Natural Language</span>
                </button>
                <button class="quick-action" @click="activeSection = 'runner'">
                  <i class="fas fa-play"></i>
                  <span>View Runner</span>
                </button>
              </div>
            </div>

            <!-- Strategies Card -->
            <div class="overview-card" v-if="Object.keys(executionStrategies).length > 0">
              <h4><i class="fas fa-chess"></i> Execution Strategies</h4>
              <div class="strategies-grid">
                <div
                  v-for="(strategy, key) in executionStrategies"
                  :key="key"
                  class="strategy-item"
                >
                  <div class="strategy-header">
                    <i :class="getStrategyIcon(key)"></i>
                    <span class="strategy-name">{{ strategy.name }}</span>
                  </div>
                  <p class="strategy-description">{{ strategy.description }}</p>
                  <span class="strategy-best-for">{{ strategy.best_for }}</span>
                </div>
              </div>
            </div>

            <!-- Recent Examples Card -->
            <div class="overview-card" v-if="Object.keys(exampleWorkflows).length > 0">
              <h4><i class="fas fa-lightbulb"></i> Example Workflows</h4>
              <div class="examples-list">
                <div
                  v-for="(example, key) in exampleWorkflows"
                  :key="key"
                  class="example-item"
                  @click="runExampleWorkflow(example)"
                >
                  <div class="example-header">
                    <span class="example-name">{{ key.replace(/_/g, ' ') }}</span>
                    <span class="example-strategy">{{ example.strategy }}</span>
                  </div>
                  <p class="example-description">{{ example.description }}</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Visual Builder Section -->
        <section v-if="activeSection === 'canvas'" class="section-canvas">
          <WorkflowCanvas
            :nodes="workflowNodes"
            :selected-node-id="selectedNodeId"
            @node-added="handleNodeAdded"
            @node-removed="handleNodeRemoved"
            @node-moved="handleNodeMoved"
            @node-selected="handleNodeSelected"
            @nodes-connected="handleNodesConnected"
            @save-workflow="handleSaveWorkflow"
          />
        </section>

        <!-- Templates Section -->
        <section v-if="activeSection === 'templates'" class="section-templates">
          <WorkflowTemplateGallery
            :templates="templates"
            :loading="loading"
            @select-template="handleTemplateSelected"
            @run-template="handleRunTemplate"
          />
        </section>

        <!-- Natural Language Section -->
        <section v-if="activeSection === 'natural-language'" class="section-natural-language">
          <div class="nl-container">
            <div class="nl-header">
              <h3><i class="fas fa-magic"></i> Create Workflow from Description</h3>
              <p>Describe what you want to accomplish and we'll create a workflow for you.</p>
            </div>

            <div class="nl-input-area">
              <textarea
                v-model="naturalLanguageInput"
                placeholder="Example: Update my system, install Docker, and deploy a test container"
                rows="4"
                :disabled="executingWorkflow"
              ></textarea>

              <div class="nl-options">
                <label class="checkbox-option">
                  <input type="checkbox" v-model="requireApprovalBeforeRun" />
                  <span>Review plan before execution</span>
                </label>

                <select v-model="selectedStrategy" class="strategy-select">
                  <option value="">Auto-select strategy</option>
                  <option v-for="(strategy, key) in executionStrategies" :key="key" :value="key">
                    {{ strategy.name }}
                  </option>
                </select>
              </div>

              <div class="nl-actions">
                <button
                  class="btn-primary"
                  @click="createFromNaturalLanguage"
                  :disabled="!naturalLanguageInput.trim() || executingWorkflow"
                >
                  <i class="fas fa-wand-magic-sparkles"></i>
                  {{ executingWorkflow ? 'Creating...' : 'Create Workflow' }}
                </button>
              </div>
            </div>

            <!-- Pending Approval -->
            <div v-if="pendingApproval" class="approval-panel">
              <div class="approval-header">
                <i class="fas fa-clipboard-check"></i>
                <h4>Plan Awaiting Approval</h4>
              </div>

              <div class="approval-summary">
                <p>{{ pendingApproval.plan_summary }}</p>
                <div class="approval-meta">
                  <span><i class="fas fa-list-ol"></i> {{ pendingApproval.total_steps }} steps</span>
                  <span><i class="fas fa-clock"></i> ~{{ Math.round(pendingApproval.estimated_total_duration / 60) }} min</span>
                </div>
              </div>

              <div class="approval-steps">
                <div
                  v-for="step in pendingApproval.steps"
                  :key="step.step_id"
                  class="approval-step"
                  :class="{ 'high-risk': step.risk_level === 'high' || step.risk_level === 'critical' }"
                >
                  <div class="step-header">
                    <span class="step-description">{{ step.description }}</span>
                    <span class="risk-badge" :class="step.risk_level">{{ step.risk_level }}</span>
                  </div>
                  <code class="step-command">{{ step.command }}</code>
                </div>
              </div>

              <div class="approval-actions">
                <button class="btn-success" @click="handleApprovePlan">
                  <i class="fas fa-check"></i> Approve & Run
                </button>
                <button class="btn-danger" @click="handleRejectPlan">
                  <i class="fas fa-times"></i> Reject
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- Runner Section -->
        <section v-if="activeSection === 'runner'" class="section-runner">
          <WorkflowRunner
            :workflows="activeWorkflows"
            :current-workflow="currentWorkflow"
            :loading="executingWorkflow"
            @start-workflow="handleStartWorkflow"
            @pause-workflow="handlePauseWorkflow"
            @resume-workflow="handleResumeWorkflow"
            @cancel-workflow="handleCancelWorkflow"
            @approve-step="handleApproveStep"
            @skip-step="handleSkipStep"
            @refresh="loadActiveWorkflows"
          />
        </section>

        <!-- History Section -->
        <section v-if="activeSection === 'history'" class="section-history">
          <WorkflowHistory
            :workflows="activeWorkflows"
            @view-workflow="handleViewWorkflow"
            @re-run="handleReRunWorkflow"
          />
        </section>

        <!-- Orchestration Visualizer Section -->
        <section v-if="activeSection === 'orchestration'" class="section-orchestration">
          <OrchestrationVisualizer
            :status="orchestrationStatus"
            :strategies="executionStrategies"
            :current-workflow="currentWorkflow"
            :loading="loading"
          />
        </section>

        <!-- GUI Automation Section -->
        <section v-if="activeSection === 'gui-automation'" class="section-gui-automation">
          <VisionAutomationPage />
        </section>

        <!-- Agents Section -->
        <section v-if="activeSection === 'agents'" class="section-agents">
          <div class="agents-container">
            <div class="agents-header">
              <h3><i class="fas fa-users-cog"></i> Agent Capabilities & Performance</h3>
              <button @click="loadAgentCapabilities" class="btn-refresh-sm" :disabled="loadingCapabilities">
                <i class="fas fa-sync-alt" :class="{ 'fa-spin': loadingCapabilities }"></i>
              </button>
            </div>

            <div v-if="loadingCapabilities" class="loading-inline">
              <LoadingSpinner size="sm" />
              <span>Loading agent data...</span>
            </div>

            <div v-else class="agents-grid">
              <div
                v-for="(agent, name) in agentCapabilities"
                :key="name"
                class="agent-card"
              >
                <div class="agent-header">
                  <i class="fas fa-robot"></i>
                  <span class="agent-name">{{ name }}</span>
                </div>

                <div class="agent-capabilities">
                  <span
                    v-for="cap in agent.capabilities"
                    :key="cap"
                    class="capability-tag"
                  >
                    {{ cap }}
                  </span>
                </div>

                <div class="agent-performance">
                  <div class="perf-item">
                    <span class="label">Reliability</span>
                    <div class="progress-bar">
                      <div
                        class="progress-fill"
                        :style="{ width: `${agent.performance.reliability * 100}%` }"
                      ></div>
                    </div>
                    <span class="value">{{ Math.round(agent.performance.reliability * 100) }}%</span>
                  </div>
                  <div class="perf-item">
                    <span class="label">Total Tasks</span>
                    <span class="value">{{ agent.performance.total_tasks }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useToast } from '@/composables/useToast';
import {
  useWorkflowBuilder,
  type WorkflowNode,
  type WorkflowTemplate,
  type ExecutionStrategy,
} from '@/composables/useWorkflowBuilder';
import type { WorkflowTemplateSummary } from '@/types/workflowTemplates';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue';
import WorkflowTemplateGallery from '@/components/workflow/WorkflowTemplateGallery.vue';
import WorkflowRunner from '@/components/workflow/WorkflowRunner.vue';
import WorkflowHistory from '@/components/workflow/WorkflowHistory.vue';
import OrchestrationVisualizer from '@/components/workflow/OrchestrationVisualizer.vue';
import VisionAutomationPage from '@/components/vision/VisionAutomationPage.vue';

const logger = createLogger('WorkflowBuilderView');
const { showToast } = useToast();

// Section Types
type SectionType =
  | 'overview'
  | 'canvas'
  | 'templates'
  | 'natural-language'
  | 'runner'
  | 'history'
  | 'orchestration'
  | 'agents'
  | 'gui-automation';

// Composable
const {
  loading,
  executingWorkflow,
  loadingCapabilities,
  error,
  activeWorkflows,
  currentWorkflow,
  pendingApproval,
  orchestrationStatus,
  executionStrategies,
  agentCapabilities,
  exampleWorkflows,
  workflowNodes,
  selectedNodeId,
  templates,
  hasActiveWorkflows,
  loadOrchestrationStatus,
  loadExecutionStrategies,
  loadAgentCapabilities,
  loadExampleWorkflows,
  loadActiveWorkflows,
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
  addNode,
  removeNode,
  updateNodePosition,
  connectNodes,
  connectWebSocket,
  disconnectWebSocket,
} = useWorkflowBuilder();

// Local State
const activeSection = ref<SectionType>('overview');
const naturalLanguageInput = ref('');
const requireApprovalBeforeRun = ref(true);
const selectedStrategy = ref<string>('');
const sessionId = ref(`session_${Date.now()}`);

// Computed
const hasData = computed(
  () => orchestrationStatus.value !== null || activeWorkflows.value.length > 0
);

const orchestrationHealthy = computed(
  () => orchestrationStatus.value?.status === 'operational'
);

const totalAgents = computed(
  () => orchestrationStatus.value?.total_agents ?? Object.keys(agentCapabilities.value).length
);

const systemStatusClass = computed(() => {
  if (orchestrationHealthy.value) return 'healthy';
  if (orchestrationStatus.value) return 'degraded';
  return 'unhealthy';
});

const statusIcon = computed(() => {
  const icons: Record<string, string> = {
    healthy: 'fas fa-check-circle',
    degraded: 'fas fa-exclamation-triangle',
    unhealthy: 'fas fa-times-circle',
  };
  return icons[systemStatusClass.value] || 'fas fa-question';
});

const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    healthy: 'System Operational',
    degraded: 'Partial Availability',
    unhealthy: 'Services Offline',
  };
  return labels[systemStatusClass.value] || 'Unknown';
});

const sectionTitle = computed(() => {
  const titles: Record<SectionType, string> = {
    overview: 'Workflow Builder Overview',
    canvas: 'Visual Workflow Builder',
    templates: 'Workflow Templates',
    'natural-language': 'Natural Language Builder',
    runner: 'Workflow Runner',
    history: 'Execution History',
    orchestration: 'Orchestration Visualizer',
    agents: 'Agent Management',
    'gui-automation': 'GUI Automation',
  };
  return titles[activeSection.value] || 'Workflow Builder';
});

const sectionDescription = computed(() => {
  const descriptions: Record<SectionType, string> = {
    overview: 'Monitor workflows and system status',
    canvas: 'Build workflows visually with drag-and-drop',
    templates: 'Start from pre-built workflow templates',
    'natural-language': 'Describe your task and we create the workflow',
    runner: 'Execute and monitor active workflows',
    history: 'View past workflow executions and results',
    orchestration: 'Visualize multi-agent orchestration chains',
    agents: 'View agent capabilities and performance metrics',
    'gui-automation': 'Detect and execute GUI automation opportunities from screen capture',
  };
  return descriptions[activeSection.value] || '';
});

// Methods
function getStrategyIcon(strategy: string): string {
  const icons: Record<string, string> = {
    sequential: 'fas fa-arrow-right',
    parallel: 'fas fa-columns',
    pipeline: 'fas fa-stream',
    collaborative: 'fas fa-users',
    adaptive: 'fas fa-random',
  };
  return icons[strategy] || 'fas fa-cog';
}

async function refreshAll(): Promise<void> {
  await Promise.all([
    loadOrchestrationStatus(),
    loadExecutionStrategies(),
    loadActiveWorkflows(),
    loadExampleWorkflows(),
  ]);
}

async function runExampleWorkflow(example: { goal: string; strategy: string }): Promise<void> {
  naturalLanguageInput.value = example.goal;
  selectedStrategy.value = example.strategy;
  activeSection.value = 'natural-language';
}

async function createFromNaturalLanguage(): Promise<void> {
  if (!naturalLanguageInput.value.trim()) return;

  const workflowId = await createWorkflowFromNaturalLanguage(
    naturalLanguageInput.value,
    sessionId.value,
    requireApprovalBeforeRun.value
  );

  if (workflowId) {
    showToast('Workflow created successfully', 'success');
    if (!requireApprovalBeforeRun.value) {
      activeSection.value = 'runner';
    }
  } else {
    showToast(error.value || 'Failed to create workflow', 'error');
  }
}

async function handleApprovePlan(): Promise<void> {
  if (!pendingApproval.value) return;

  const success = await approvePlan(pendingApproval.value.workflow_id);
  if (success) {
    showToast('Plan approved, workflow starting...', 'success');
    naturalLanguageInput.value = '';
    activeSection.value = 'runner';
  } else {
    showToast('Failed to approve plan', 'error');
  }
}

async function handleRejectPlan(): Promise<void> {
  if (!pendingApproval.value) return;

  const success = await rejectPlan(pendingApproval.value.workflow_id, 'User rejected');
  if (success) {
    showToast('Plan rejected', 'info');
  }
}

function handleNodeAdded(node: WorkflowNode): void {
  addNode(node);
}

function handleNodeRemoved(nodeId: string): void {
  removeNode(nodeId);
}

function handleNodeMoved(nodeId: string, position: { x: number; y: number }): void {
  updateNodePosition(nodeId, position);
}

function handleNodeSelected(nodeId: string | null): void {
  selectedNodeId.value = nodeId;
}

function handleNodesConnected(sourceId: string, targetId: string): void {
  connectNodes(sourceId, targetId);
}

async function handleSaveWorkflow(name: string, description: string): Promise<void> {
  // Export canvas nodes to steps and create workflow
  showToast('Workflow saved', 'success');
}

async function handleTemplateSelected(template: WorkflowTemplate | WorkflowTemplateSummary): Promise<void> {
  // Load template into canvas
  logger.debug('Template selected:', template);
}

async function handleRunTemplate(template: WorkflowTemplate | WorkflowTemplateSummary): Promise<void> {
  const workflowId = await createWorkflowFromTemplate(template as WorkflowTemplate, sessionId.value);
  if (workflowId) {
    showToast(`Workflow "${template.name}" created`, 'success');
    activeSection.value = 'runner';
  }
}

async function handleStartWorkflow(workflowId: string): Promise<void> {
  const success = await startWorkflow(workflowId);
  if (success) {
    showToast('Workflow started', 'success');
  }
}

async function handlePauseWorkflow(workflowId: string): Promise<void> {
  const success = await pauseWorkflow(workflowId);
  if (success) {
    showToast('Workflow paused', 'info');
  }
}

async function handleResumeWorkflow(workflowId: string): Promise<void> {
  const success = await resumeWorkflow(workflowId);
  if (success) {
    showToast('Workflow resumed', 'success');
  }
}

async function handleCancelWorkflow(workflowId: string): Promise<void> {
  const success = await cancelWorkflow(workflowId);
  if (success) {
    showToast('Workflow cancelled', 'info');
  }
}

async function handleApproveStep(workflowId: string, stepId: string): Promise<void> {
  const success = await approveStep(workflowId, stepId);
  if (success) {
    showToast('Step approved', 'success');
  }
}

async function handleSkipStep(workflowId: string, stepId: string): Promise<void> {
  const success = await skipStep(workflowId, stepId);
  if (success) {
    showToast('Step skipped', 'info');
  }
}

function handleViewWorkflow(workflowId: string): void {
  // Switch to runner and load specific workflow
  activeSection.value = 'runner';
}

async function handleReRunWorkflow(workflowId: string): Promise<void> {
  // Re-run a workflow from history
  showToast('Re-running workflow...', 'info');
}

// Lifecycle
onMounted(() => {
  refreshAll();
  loadAgentCapabilities();
  connectWebSocket(sessionId.value);
});

onUnmounted(() => {
  disconnectWebSocket();
});

// Watch for active workflow changes
watch(hasActiveWorkflows, (hasActive) => {
  if (hasActive && activeSection.value === 'overview') {
    // Could auto-switch to runner when workflows become active
  }
});
</script>

<style scoped>
/* Issue #901: Technical Precision Workflow Builder Design */

.workflow-builder-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.workflow-sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  display: flex;
  align-items: center;
  gap: 10px;
  line-height: 1.5;
}

.header-icon {
  width: 18px;
  height: 18px;
  color: var(--color-info);
  flex-shrink: 0;
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.category-divider {
  padding: 12px 20px 8px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-tertiary);
  font-family: var(--font-sans);
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--text-secondary);
  border-left: 2px solid transparent;
  /* Reset button styles */
  background: none;
  border: none;
  border-left: 2px solid transparent;
  text-align: left;
  width: 100%;
  font-family: inherit;
}

.category-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.category-item.active {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-left-color: var(--color-info);
}

.item-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.category-item span:first-of-type:not(.count) {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  font-family: var(--font-sans);
}

.category-item .count {
  font-size: 11px;
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.category-item .count.active-badge {
  background: var(--color-success);
  color: white;
}

.category-item.active .count:not(.active-badge) {
  background: var(--color-info);
  color: white;
}

.sidebar-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-refresh {
  width: 100%;
  height: 36px;
  padding: 0 12px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-icon {
  width: 16px;
  height: 16px;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Main Content */
.workflow-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.status-badge.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge.degraded {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-badge.unhealthy {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Loading & Error States */
.loading-container,
.error-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-tertiary);
  padding: 40px;
}

.error-container .error-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.error-container h3 {
  margin: 0;
  color: var(--text-primary);
}

.error-container p {
  margin: 0;
  color: var(--text-secondary);
}

/* Content Body */
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* Overview Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  transition: all 0.2s;
}

.stat-card.active {
  border-color: var(--color-success);
}

.stat-card .stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--text-secondary);
}

.stat-card .stat-icon.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.stat-card .stat-icon.unhealthy {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Overview Sections */
.overview-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.overview-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.overview-card h4 {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-card h4 i {
  color: var(--color-primary);
}

/* Quick Actions Grid */
.quick-actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.quick-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  color: var(--text-secondary);
}

.quick-action:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.quick-action i {
  font-size: 20px;
}

.quick-action span {
  font-size: 13px;
  font-weight: 500;
}

/* Strategies Grid */
.strategies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
}

.strategy-item {
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.strategy-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.strategy-header i {
  color: var(--color-primary);
}

.strategy-name {
  font-weight: 600;
  color: var(--text-primary);
}

.strategy-description {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.strategy-best-for {
  font-size: 12px;
  color: var(--text-tertiary);
  font-style: italic;
}

/* Examples List */
.examples-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.example-item {
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.example-item:hover {
  background: var(--bg-hover);
}

.example-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.example-name {
  font-weight: 500;
  color: var(--text-primary);
  text-transform: capitalize;
}

.example-strategy {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: 10px;
}

.example-description {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Natural Language Section */
.nl-container {
  max-width: 800px;
  margin: 0 auto;
}

.nl-header {
  text-align: center;
  margin-bottom: 24px;
}

.nl-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.nl-header h3 i {
  color: var(--color-primary);
}

.nl-header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
}

.nl-input-area {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.nl-input-area textarea {
  width: 100%;
  padding: 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}

.nl-input-area textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.nl-input-area textarea::placeholder {
  color: var(--text-muted);
}

.nl-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px 0;
}

.checkbox-option {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 14px;
}

.checkbox-option input {
  width: 16px;
  height: 16px;
}

.strategy-select {
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
}

.nl-actions {
  display: flex;
  justify-content: flex-end;
}

/* Approval Panel */
.approval-panel {
  margin-top: 24px;
  background: var(--bg-secondary);
  border: 1px solid var(--color-warning);
  border-radius: 12px;
  padding: 20px;
}

.approval-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.approval-header i {
  font-size: 20px;
  color: var(--color-warning);
}

.approval-header h4 {
  margin: 0;
  color: var(--text-primary);
}

.approval-summary p {
  margin: 0 0 8px;
  color: var(--text-secondary);
}

.approval-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.approval-meta span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.approval-steps {
  margin: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.approval-step {
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border-left: 3px solid var(--border-default);
}

.approval-step.high-risk {
  border-left-color: var(--color-error);
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.step-description {
  font-size: 14px;
  color: var(--text-primary);
}

.risk-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
}

.risk-badge.low {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.risk-badge.medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.risk-badge.high,
.risk-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.step-command {
  display: block;
  padding: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
}

.approval-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

/* Agents Section */
.agents-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.agents-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.agents-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.agents-header h3 i {
  color: var(--color-primary);
}

.btn-refresh-sm {
  padding: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh-sm:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh-sm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-inline {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  color: var(--text-tertiary);
}

.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.agent-card {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 16px;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.agent-header i {
  font-size: 18px;
  color: var(--color-primary);
}

.agent-name {
  font-weight: 600;
  color: var(--text-primary);
}

.agent-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.capability-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border-radius: 10px;
}

.agent-performance {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-performance .perf-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-performance .label {
  font-size: 12px;
  color: var(--text-tertiary);
  min-width: 70px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-success);
  border-radius: 3px;
  transition: width 0.3s;
}

.agent-performance .value {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

/* Buttons */
.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-success {
  padding: 10px 20px;
  background: var(--color-success);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-success:hover {
  filter: brightness(1.1);
}

.btn-danger {
  padding: 10px 20px;
  background: var(--color-error);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-danger:hover {
  filter: brightness(1.1);
}

/* Responsive */
@media (max-width: 768px) {
  .workflow-builder-view {
    flex-direction: column;
  }

  .workflow-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .strategies-grid {
    grid-template-columns: 1fr;
  }

  .agents-grid {
    grid-template-columns: 1fr;
  }
}
</style>
