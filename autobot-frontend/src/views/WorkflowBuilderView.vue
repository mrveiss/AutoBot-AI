<template>
  <div class="workflow-builder-view">
    <!-- Sidebar Navigation - Issue #901: Technical Precision Design -->
    <aside class="workflow-sidebar">
      <div class="sidebar-header">
        <h3>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path>
          </svg>
          {{ $t('workflow.views.title') }}
        </h3>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav" :aria-label="$t('workflow.views.navAriaLabel')">
        <router-link
          to="/automation/overview"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.overviewAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path>
          </svg>
          <span>{{ $t('workflow.views.overview') }}</span>
        </router-link>

        <div class="category-divider">
          <span>{{ $t('workflow.views.build') }}</span>
        </div>

        <router-link
          to="/automation/canvas"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.visualBuilderAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 12a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1v-7z"></path>
          </svg>
          <span>{{ $t('workflow.views.visualBuilder') }}</span>
        </router-link>

        <router-link
          to="/automation/templates"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.templatesAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
          </svg>
          <span>{{ $t('workflow.views.templates') }}</span>
          <span class="count" :aria-label="`${templates.length} templates`">{{ templates.length }}</span>
        </router-link>

        <router-link
          to="/automation/natural-language"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.naturalLanguageAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
          </svg>
          <span>{{ $t('workflow.views.naturalLanguage') }}</span>
        </router-link>

        <div class="category-divider">
          <span>{{ $t('workflow.views.execute') }}</span>
        </div>

        <router-link
          to="/automation/runner"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.runnerAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>{{ $t('workflow.views.runner') }}</span>
          <span class="count active-badge" v-if="hasActiveWorkflows" :aria-label="`${activeWorkflows.length} active workflows`">
            {{ activeWorkflows.length }}
          </span>
        </router-link>

        <router-link
          to="/automation/history"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.historyAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>{{ $t('workflow.views.history') }}</span>
        </router-link>

        <!-- Issue #3139: Per-workflow notification configuration -->
        <router-link
          to="/automation/notifications"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.notifications.sidebarLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          <span>{{ $t('workflow.notifications.sidebarLabel') }}</span>
        </router-link>

        <router-link
          to="/automation/gui-automation"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.guiAutomationAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          <span>{{ $t('workflow.views.guiAutomation') }}</span>
        </router-link>

        <router-link
          to="/automation/browser-automation"
          class="category-item"
          :class="{ active: $route.name === 'browser-automation' }"
          :aria-label="$t('nav.browserAutomation')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.083 9h1.946c.089-1.546.383-2.97.837-4.118A6.004 6.004 0 004.083 9zM10 2a8 8 0 100 16 8 8 0 000-16zm0 2c-.076 0-.232.032-.465.262-.238.234-.497.623-.737 1.182-.389.907-.673 2.142-.766 3.556h3.936c-.093-1.414-.377-2.649-.766-3.556-.24-.56-.5-.948-.737-1.182C10.232 4.032 10.076 4 10 4zm3.971 5c-.089-1.546-.383-2.97-.837-4.118A6.004 6.004 0 0115.917 9h-1.946zm-2.003 2H8.032c.093 1.414.377 2.649.766 3.556.24.56.5.948.737 1.182.233.23.389.262.465.262.076 0 .232-.032.465-.262.238-.234.497-.623.737-1.182.389-.907.673-2.142.766-3.556zm1.166 4.118c.454-1.147.748-2.572.837-4.118h1.946a6.004 6.004 0 01-2.783 4.118zm-6.268 0C6.412 13.97 6.118 12.546 6.03 11H4.083a6.004 6.004 0 002.783 4.118z" />
          </svg>
          <span>{{ $t('nav.browserAutomation') }}</span>
        </router-link>

        <div class="category-divider category-divider--with-status">
          <span>{{ $t('workflow.views.vision') }}</span>
          <span class="health-indicator" :class="visionHealthStatus">
            {{ visionHealthStatus }}
          </span>
        </div>

        <router-link
          to="/automation/screen-analysis"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.screenAnalysisAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <span>{{ $t('workflow.views.screenAnalysis') }}</span>
        </router-link>

        <router-link
          to="/automation/video-processing"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.videoProcessingAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <span>{{ $t('workflow.views.videoProcessing') }}</span>
        </router-link>

        <router-link
          to="/automation/media-gallery"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.mediaGalleryAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span>{{ $t('workflow.views.mediaGallery') }}</span>
        </router-link>

        <div class="category-divider">
          <span>{{ $t('workflow.views.orchestration') }}</span>
        </div>

        <!-- Issue #2155: Live Execution Dashboard -->
        <router-link
          to="/automation/live-dashboard"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.liveDashboardAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
          </svg>
          <span>{{ $t('workflow.views.liveDashboard') }}</span>
        </router-link>

        <router-link
          to="/automation/orchestration"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.visualizerAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
          </svg>
          <span>{{ $t('workflow.views.visualizer') }}</span>
        </router-link>

        <router-link
          to="/automation/agents"
          active-class="active"
          class="category-item"
          :aria-label="$t('workflow.views.agentsAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
          </svg>
          <span>{{ $t('workflow.views.agents') }}</span>
        </router-link>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="refreshAll" class="btn-refresh" :disabled="loading">
          <svg class="refresh-icon" :class="{ 'spinning': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
          </svg>
          {{ $t('workflow.views.refresh') }}
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="workflow-content">
      <!-- Child route content (#2368) -->
      <router-view v-if="isChildRoute" />

      <!-- Workflow Builder own content -->
      <template v-else>
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ sectionTitle }}</h2>
          <span class="subtitle">{{ sectionDescription }}</span>
        </div>
        <div class="header-actions">
          <div class="status-badge" :class="systemStatusClass">
            <Icon :name="statusIcon" />
            <span>{{ statusLabel }}</span>
          </div>
        </div>
      </header>

      <!-- Loading State -->
      <div v-if="loading && !hasData" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>{{ $t('workflow.views.loadingServices') }}</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-container">
        <div class="error-icon">
          <Icon name="exclamation-triangle" />
        </div>
        <h3>{{ $t('workflow.views.failedToLoad') }}</h3>
        <p>{{ error }}</p>
        <button @click="refreshAll" class="btn-primary">
          <Icon name="redo" /> {{ $t('workflow.views.retry') }}
        </button>
      </div>

      <!-- Content Sections -->
      <div v-else class="content-body">
        <!-- Overview Section -->
        <section v-if="activeSection === 'overview'" class="section-overview">
          <div class="stats-grid">
            <div class="stat-card" :class="{ active: orchestrationHealthy }">
              <div class="stat-icon" :class="orchestrationHealthy ? 'healthy' : 'unhealthy'">
                <Icon name="cogs" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ orchestrationHealthy ? $t('workflow.views.ready') : $t('workflow.views.offline') }}</span>
                <span class="stat-label">{{ $t('workflow.views.orchestrationLabel') }}</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="tasks" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ activeWorkflows.length }}</span>
                <span class="stat-label">{{ $t('workflow.views.activeWorkflows') }}</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="users" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ totalAgents }}</span>
                <span class="stat-label">{{ $t('workflow.views.availableAgents') }}</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="layer-group" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ Object.keys(executionStrategies).length }}</span>
                <span class="stat-label">{{ $t('workflow.views.strategies') }}</span>
              </div>
            </div>
          </div>

          <div class="overview-sections">
            <!-- Quick Actions Card -->
            <div class="overview-card">
              <h4><Icon name="bolt" /> {{ $t('workflow.views.quickActions') }}</h4>
              <div class="quick-actions-grid">
                <button class="quick-action" @click="navigateTo('canvas')">
                  <Icon name="plus-circle" />
                  <span>{{ $t('workflow.views.newWorkflow') }}</span>
                </button>
                <button class="quick-action" @click="navigateTo('templates')">
                  <Icon name="clone" />
                  <span>{{ $t('workflow.views.useTemplate') }}</span>
                </button>
                <button class="quick-action" @click="navigateTo('natural-language')">
                  <Icon name="magic" />
                  <span>{{ $t('workflow.views.naturalLanguage') }}</span>
                </button>
                <button class="quick-action" @click="navigateTo('runner')">
                  <Icon name="play" />
                  <span>{{ $t('workflow.views.viewRunner') }}</span>
                </button>
              </div>
            </div>

            <!-- Strategies Card -->
            <div class="overview-card" v-if="Object.keys(executionStrategies).length > 0">
              <h4><Icon name="chess" /> {{ $t('workflow.views.executionStrategies') }}</h4>
              <div class="strategies-grid">
                <div
                  v-for="(strategy, key) in executionStrategies"
                  :key="key"
                  class="strategy-item"
                >
                  <div class="strategy-header">
                    <Icon :name="getStrategyIcon(key)" />
                    <span class="strategy-name">{{ strategy.name }}</span>
                  </div>
                  <p class="strategy-description">{{ strategy.description }}</p>
                  <span class="strategy-best-for">{{ strategy.best_for }}</span>
                </div>
              </div>
            </div>

            <!-- Recent Examples Card -->
            <div class="overview-card" v-if="Object.keys(exampleWorkflows).length > 0">
              <h4><Icon name="lightbulb" /> {{ $t('workflow.views.exampleWorkflows') }}</h4>
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
              <h3><Icon name="magic" /> {{ $t('workflow.views.createFromDescription') }}</h3>
              <p>{{ $t('workflow.views.createFromDescriptionHelp') }}</p>
            </div>

            <div class="nl-input-area">
              <textarea
                v-model="naturalLanguageInput"
                :placeholder="$t('workflow.views.naturalLanguagePlaceholder')"
                rows="4"
                :disabled="executingWorkflow"
              ></textarea>

              <div class="nl-options">
                <label class="checkbox-option">
                  <input type="checkbox" v-model="requireApprovalBeforeRun" />
                  <span>{{ $t('workflow.views.reviewPlanBeforeExecution') }}</span>
                </label>

                <select v-model="selectedStrategy" class="strategy-select">
                  <option value="">{{ $t('workflow.views.autoSelectStrategy') }}</option>
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
                  <Icon name="wand-magic-sparkles" />
                  {{ executingWorkflow ? $t('workflow.views.creating') : $t('workflow.views.createWorkflow') }}
                </button>
              </div>
            </div>

            <!-- Pending Approval -->
            <div v-if="pendingApproval" class="approval-panel">
              <div class="approval-header">
                <Icon name="clipboard-check" />
                <h4>{{ $t('workflow.views.planAwaitingApproval') }}</h4>
              </div>

              <div class="approval-summary">
                <p>{{ pendingApproval.plan_summary }}</p>
                <div class="approval-meta">
                  <span><Icon name="list-ol" /> {{ $t('workflow.views.stepsCount', { count: pendingApproval.total_steps }) }}</span>
                  <span><Icon name="clock" /> ~{{ Math.round(pendingApproval.estimated_total_duration / 60) }} {{ $t('workflow.views.min') }}</span>
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
                  <Icon name="check" /> {{ $t('workflow.views.approveAndRun') }}
                </button>
                <button class="btn-danger" @click="handleRejectPlan">
                  <Icon name="times" /> {{ $t('workflow.views.reject') }}
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
            :completed-workflows="completedWorkflows"
            @view-workflow="handleViewWorkflow"
            @re-run="handleReRunWorkflow"
          />
        </section>

        <!-- Issue #3139: Per-Workflow Notification Configuration -->
        <section v-if="activeSection === 'notifications'" class="section-notifications">
          <WorkflowNotificationConfig
            :workflows="allWorkflowsForNotificationPicker"
            @saved="handleNotificationConfigSaved"
          />
        </section>

        <!-- Live Dashboard Section (#2155) -->
        <section v-if="activeSection === 'live-dashboard'" class="section-live-dashboard">
          <WorkflowLiveDashboard
            :active-workflows="activeWorkflows"
            :agent-performance="agentPerformance"
            :agent-capabilities="agentCapabilities"
            :loading="loading"
            :loading-capabilities="loadingCapabilities"
            @refresh="refreshAll"
            @refresh-agents="handleRefreshAgents"
            @select-workflow="handleViewWorkflow"
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

        <!-- GUI Automation Section (#1242) -->
        <section v-if="activeSection === 'gui-automation'" class="section-gui-automation">
          <GUIAutomationControls
            :opportunities="guiAutomationOpportunities"
            :loading="guiAutomationLoading"
            @refresh="loadGuiAutomationOpportunities"
          />
        </section>

        <!-- Screen Analysis Section (#2373) -->
        <section v-if="activeSection === 'screen-analysis'" class="section-screen-analysis">
          <ScreenCaptureViewer />
        </section>

        <!-- Video Processing Section (#2373) -->
        <section v-if="activeSection === 'video-processing'" class="section-video-processing">
          <VideoProcessor />
        </section>

        <!-- Media Gallery Section (#2373) -->
        <section v-if="activeSection === 'media-gallery'" class="section-media-gallery">
          <MediaGallery :items="galleryItems" />
        </section>

        <!-- Agents Section -->
        <section v-if="activeSection === 'agents'" class="section-agents">
          <div class="agents-container">
            <div class="agents-header">
              <h3><Icon name="users-cog" /> {{ $t('workflow.views.agentCapabilities') }}</h3>
              <button
                @click="loadAgentCapabilities"
                class="btn-refresh-sm"
                :disabled="loadingCapabilities"
                :aria-label="$t('common.refresh')"
                :title="$t('common.refresh')"
                type="button"
              >
                <Icon name="sync-alt" :spin="loadingCapabilities" />
              </button>
            </div>

            <div v-if="loadingCapabilities" class="loading-inline">
              <LoadingSpinner size="sm" />
              <span>{{ $t('workflow.views.loadingAgentData') }}</span>
            </div>

            <div v-else class="agents-grid">
              <div
                v-for="(agent, name) in agentCapabilities"
                :key="name"
                class="agent-card"
              >
                <div class="agent-header">
                  <Icon name="robot" />
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
                    <span class="label">{{ $t('workflow.views.reliability') }}</span>
                    <div class="progress-bar">
                      <div
                        class="progress-fill"
                        :style="{ width: `${agent.performance.reliability * 100}%` }"
                      ></div>
                    </div>
                    <span class="value">{{ Math.round(agent.performance.reliability * 100) }}%</span>
                  </div>
                  <div class="perf-item">
                    <span class="label">{{ $t('workflow.views.totalTasks') }}</span>
                    <span class="value">{{ agent.performance.total_tasks }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { useNotificationBus } from '@/composables/useNotificationBus';
import {
  useWorkflowBuilder,
  type WorkflowNode,
  type WorkflowTemplate,
  type ExecutionStrategy,
} from '@/composables/useWorkflowBuilder';
import type { WorkflowTemplateSummary } from '@/types/workflowTemplates';
import { useWorkflowTemplates } from '@/composables/useWorkflowTemplates';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import Icon from '@/components/ui/Icon.vue';
import type { IconName } from '@/components/ui/Icon.vue';
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue';
import WorkflowTemplateGallery from '@/components/workflow/WorkflowTemplateGallery.vue';
import WorkflowRunner from '@/components/workflow/WorkflowRunner.vue';
import WorkflowHistory from '@/components/workflow/WorkflowHistory.vue';
import WorkflowNotificationConfig from '@/components/workflow/WorkflowNotificationConfig.vue';
import OrchestrationVisualizer from '@/components/workflow/OrchestrationVisualizer.vue';
import WorkflowLiveDashboard from '@/components/workflow/WorkflowLiveDashboard.vue';
import GUIAutomationControls from '@/components/vision/GUIAutomationControls.vue';
import ScreenCaptureViewer from '@/components/vision/ScreenCaptureViewer.vue';
import VideoProcessor from '@/components/vision/VideoProcessor.vue';
import MediaGallery from '@/components/vision/MediaGallery.vue';
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
} from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('WorkflowBuilderView');
const { t } = useI18n();
const route = useRoute();
const router = useRouter();

/** True when a non-section child route (e.g. /automation/browser-automation) is active (#2368) */
const isChildRoute = computed(() => route.matched.length > 1 && !route.meta.sectionRoute);

function navigateTo(section: SectionType): void {
  router.push(`/automation/${section}`);
}
const { showToast } = useNotificationBus();

// Section Types
type SectionType =
  | 'overview'
  | 'canvas'
  | 'templates'
  | 'natural-language'
  | 'runner'
  | 'history'
  | 'notifications'
  | 'gui-automation'
  | 'screen-analysis'
  | 'video-processing'
  | 'media-gallery'
  | 'orchestration'
  | 'agents'
  | 'live-dashboard';

// Composable
const {
  loading,
  executingWorkflow,
  loadingCapabilities,
  error,
  activeWorkflows,
  completedWorkflows,
  currentWorkflow,
  pendingApproval,
  orchestrationStatus,
  executionStrategies,
  agentCapabilities,
  agentPerformance,
  exampleWorkflows,
  workflowNodes,
  selectedNodeId,
  templates,
  hasActiveWorkflows,
  loadOrchestrationStatus,
  loadExecutionStrategies,
  loadAgentCapabilities,
  loadAgentPerformance,
  loadExampleWorkflows,
  loadActiveWorkflows,
  loadCompletedWorkflows,
  createWorkflowFromTemplate,
  createWorkflowFromNaturalLanguage,
  executeApiTemplate,
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
  clearCanvas,
  exportCanvasToSteps,
  getWorkflowStatus,
  connectWebSocket,
  disconnectWebSocket,
} = useWorkflowBuilder();

// Issue #1367: Fetch full template detail when summary lacks steps
const { fetchTemplateDetail } = useWorkflowTemplates();

// GH#8750: Section derived from URL so back/forward and bookmarks work
const activeSection = computed<SectionType>(
  () => (route.params.section as SectionType) || 'overview'
);
const naturalLanguageInput = ref('');
const requireApprovalBeforeRun = ref(true);
const selectedStrategy = ref<string>('');
const sessionId = ref(`session_${Date.now()}`);

// GUI Automation state (#1242)
const guiAutomationOpportunities = ref<AutomationOpportunity[]>([]);
const guiAutomationLoading = ref(false);

// Media Gallery state
const galleryItems = ref([]);

// Vision service health (#2373)
const visionHealthStatus = ref<'healthy' | 'degraded' | 'offline'>('offline');

async function checkVisionHealth(): Promise<void> {
  try {
    const res = await visionMultimodalApiClient.getVisionHealth();
    if (res.success && res.data) {
      visionHealthStatus.value = res.data.status === 'healthy' ? 'healthy' : 'degraded';
    } else {
      visionHealthStatus.value = 'offline';
    }
  } catch {
    visionHealthStatus.value = 'offline';
  }
}

async function loadGuiAutomationOpportunities(): Promise<void> {
  guiAutomationLoading.value = true;
  try {
    const res = await visionMultimodalApiClient.getAutomationOpportunities();
    if (res.success && res.data) {
      guiAutomationOpportunities.value = res.data.opportunities || [];
    }
  } catch (e) {
    logger.warn('Failed to load automation opportunities:', e);
  } finally {
    guiAutomationLoading.value = false;
  }
}

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

const statusIcon = computed((): IconName => {
  const icons: Record<string, IconName> = {
    healthy: 'check-circle',
    degraded: 'exclamation-triangle',
    unhealthy: 'times-circle',
  };
  return icons[systemStatusClass.value] || 'question-circle';
});

const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    healthy: t('workflow.views.systemOperational'),
    degraded: t('workflow.views.partialAvailability'),
    unhealthy: t('workflow.views.servicesOffline'),
  };
  return labels[systemStatusClass.value] || t('workflow.views.unknown');
});

const sectionTitle = computed(() => {
  const titles: Record<SectionType, string> = {
    overview: t('workflow.views.sectionTitleOverview'),
    canvas: t('workflow.views.sectionTitleCanvas'),
    templates: t('workflow.views.sectionTitleTemplates'),
    'natural-language': t('workflow.views.sectionTitleNaturalLanguage'),
    runner: t('workflow.views.sectionTitleRunner'),
    history: t('workflow.views.sectionTitleHistory'),
    notifications: t('workflow.notifications.sectionTitle'),
    'live-dashboard': t('workflow.views.sectionTitleLiveDashboard'),
    orchestration: t('workflow.views.sectionTitleOrchestration'),
    agents: t('workflow.views.sectionTitleAgents'),
    'gui-automation': t('workflow.views.sectionTitleGuiAutomation'),
    'screen-analysis': t('workflow.views.sectionTitleScreenAnalysis'),
    'video-processing': t('workflow.views.sectionTitleVideoProcessing'),
    'media-gallery': t('workflow.views.sectionTitleMediaGallery'),
  };
  return titles[activeSection.value] || t('workflow.views.title');
});

const sectionDescription = computed(() => {
  const descriptions: Record<SectionType, string> = {
    overview: t('workflow.views.sectionDescOverview'),
    canvas: t('workflow.views.sectionDescCanvas'),
    templates: t('workflow.views.sectionDescTemplates'),
    'natural-language': t('workflow.views.sectionDescNaturalLanguage'),
    runner: t('workflow.views.sectionDescRunner'),
    history: t('workflow.views.sectionDescHistory'),
    notifications: t('workflow.notifications.sectionDesc'),
    'live-dashboard': t('workflow.views.sectionDescLiveDashboard'),
    orchestration: t('workflow.views.sectionDescOrchestration'),
    agents: t('workflow.views.sectionDescAgents'),
    'gui-automation': t('workflow.views.sectionDescGuiAutomation'),
    'screen-analysis': t('workflow.views.sectionDescScreenAnalysis'),
    'video-processing': t('workflow.views.sectionDescVideoProcessing'),
    'media-gallery': t('workflow.views.sectionDescMediaGallery'),
  };
  return descriptions[activeSection.value] || '';
});

/** Combine active + completed workflows for the notification config picker (#3139). */
const allWorkflowsForNotificationPicker = computed(() => {
  const combined = [
    ...activeWorkflows.value,
    ...completedWorkflows.value,
  ];
  // Deduplicate by workflow_id
  const seen = new Set<string>();
  return combined.filter((wf) => {
    if (seen.has(wf.workflow_id)) return false;
    seen.add(wf.workflow_id);
    return true;
  });
});

// Methods
function getStrategyIcon(strategy: string): IconName {
  const icons: Record<string, IconName> = {
    sequential: 'arrow-right',
    parallel: 'columns',
    pipeline: 'stream',
    collaborative: 'users',
    adaptive: 'random',
  };
  return icons[strategy] || 'cog';
}

/** Refresh agent performance and capabilities (#2155). */
async function handleRefreshAgents(): Promise<void> {
  await Promise.all([loadAgentPerformance(), loadAgentCapabilities()]);
}

async function refreshAll(): Promise<void> {
  await Promise.all([
    loadOrchestrationStatus(),
    loadExecutionStrategies(),
    loadActiveWorkflows(),
    loadCompletedWorkflows(),
    loadExampleWorkflows(),
    checkVisionHealth(),
  ]);
}

async function runExampleWorkflow(example: { goal: string; strategy: string }): Promise<void> {
  naturalLanguageInput.value = example.goal;
  selectedStrategy.value = example.strategy;
  navigateTo('natural-language');
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
      navigateTo('runner');
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
    navigateTo('runner');
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
  // #2182: Warn when unsupported node types will be dropped on save
  const unsupportedNodes = workflowNodes.value.filter(
    (n) => n.type !== 'step',
  );
  if (unsupportedNodes.length > 0) {
    const types = [...new Set(unsupportedNodes.map((n) => n.type))];
    showToast(
      `${types.join(', ')} nodes are not yet supported and will be excluded. See #2140.`,
      'warning',
    );
  }
  const steps = exportCanvasToSteps();
  if (steps.length === 0) {
    showToast('Add at least one step before saving', 'warning');
    return;
  }
  const template: WorkflowTemplate = {
    id: `canvas_${Date.now()}`,
    name,
    description,
    category: 'custom',
    icon: 'project-diagram' as IconName,
    steps,
  };
  const workflowId = await createWorkflowFromTemplate(template, sessionId.value);
  if (workflowId) {
    showToast(`Workflow "${name}" saved`, 'success');
    navigateTo('runner');
  } else {
    showToast('Failed to save workflow', 'error');
  }
}

async function handleTemplateSelected(template: WorkflowTemplate | WorkflowTemplateSummary): Promise<void> {
  let full = template as WorkflowTemplate;
  // Issue #1367: API summaries lack steps -- fetch full detail
  if (!full.steps?.length) {
    const detail = await fetchTemplateDetail(template.id);
    if (!detail?.steps?.length) {
      showToast('Template has no steps to load', 'warning');
      return;
    }
    full = { ...template, steps: detail.steps } as unknown as WorkflowTemplate;
  }
  clearCanvas();
  full.steps.forEach((step, index) => {
    const node: WorkflowNode = {
      id: `node_${Date.now()}_${index}`,
      type: 'step',
      position: { x: 100 + (index % 3) * 300, y: 100 + Math.floor(index / 3) * 180 },
      data: { ...step, step_id: '', status: 'pending' as const },
      connections: [],
    };
    addNode(node);
  });
  navigateTo('canvas');
  showToast(`Template "${template.name}" loaded into canvas`, 'success');
}

async function handleRunTemplate(template: WorkflowTemplate | WorkflowTemplateSummary): Promise<void> {
  const result = await executeApiTemplate(template.id);
  if (result?.success) {
    showToast(`Workflow "${template.name}" started`, 'success');
    navigateTo('runner');
    await loadActiveWorkflows();
  } else {
    showToast(result?.error || `Failed to run "${template.name}"`, 'error');
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

async function handleViewWorkflow(workflowId: string): Promise<void> {
  // Issue #1367: Load the selected workflow before switching to runner
  navigateTo('runner');
  const local = activeWorkflows.value.find(
    (wf) => wf.workflow_id === workflowId,
  );
  if (local) {
    currentWorkflow.value = local;
  } else {
    await getWorkflowStatus(workflowId);
  }
}

async function handleReRunWorkflow(workflowId: string): Promise<void> {
  const existing =
    activeWorkflows.value.find((wf) => wf.workflow_id === workflowId) ??
    (await getWorkflowStatus(workflowId));
  if (!existing) {
    showToast('Could not find workflow to re-run', 'error');
    return;
  }
  const template: WorkflowTemplate = {
    id: existing.workflow_id,
    name: existing.name,
    description: existing.description,
    category: 'custom',
    icon: 'redo' as IconName,
    steps: existing.steps.map(({ command, description, explanation, requires_confirmation, risk_level, estimated_duration, dependencies }) => ({
      command,
      description,
      explanation,
      requires_confirmation,
      risk_level,
      estimated_duration,
      dependencies,
    })),
  };
  const newId = await createWorkflowFromTemplate(template, `session_${Date.now()}`);
  if (newId) {
    await startWorkflow(newId);
    showToast(`Re-running "${existing.name}"`, 'success');
    navigateTo('runner');
  } else {
    showToast('Failed to re-run workflow', 'error');
  }
}

/** Handle notification config saved event (#3139). */
function handleNotificationConfigSaved(workflowId: string): void {
  showToast('Notification settings saved', 'success');
  logger.info('Notification config saved for workflow %s', workflowId);
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
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
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
  padding: var(--spacing-3) var(--spacing-0);
}

.category-divider {
  padding: var(--spacing-3) var(--spacing-5) var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-tertiary);
  font-family: var(--font-sans);
}

.category-divider--with-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.health-indicator {
  font-size: 0.65rem;
  padding: var(--spacing-px) var(--spacing-1-5);
  border-radius: var(--radius-lg);
  text-transform: uppercase;
  font-weight: 600;
}

.health-indicator.healthy {
  color: var(--color-success);
  background: rgba(16, 185, 129, 0.1);
}

.health-indicator.degraded {
  color: var(--color-warning);
  background: rgba(245, 158, 11, 0.1);
}

.health-indicator.offline {
  color: #6b7280;
  background: rgba(107, 114, 128, 0.1);
}

.category-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-5);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
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
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: var(--font-sans);
}

.category-item .count {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xl);
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
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.btn-refresh {
  width: 100%;
  height: 36px;
  padding: var(--spacing-0) var(--spacing-3);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-150) var(--ease-in-out);
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
  padding: var(--spacing-5) var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: var(--spacing-0);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3-5);
  border-radius: var(--radius-2xl);
  font-size: var(--text-sm);
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
  gap: var(--spacing-4);
  color: var(--text-tertiary);
  padding: var(--spacing-10);
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
  margin: var(--spacing-0);
  color: var(--text-primary);
}

.error-container p {
  margin: var(--spacing-0);
  color: var(--text-secondary);
}

/* Content Body */
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6);
}

/* Overview Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  transition: all var(--duration-200);
}

.stat-card.active {
  border-color: var(--color-success);
}

.stat-card .stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-xl);
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
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
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Overview Sections */
.overview-sections {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.overview-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
}

.overview-card h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.overview-card h4 svg {
  color: var(--color-primary);
}

/* Quick Actions Grid */
.quick-actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-3);
}

.quick-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200);
  color: var(--text-secondary);
}

.quick-action:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.quick-action svg {
  font-size: var(--text-xl);
  width: 24px;
  height: 24px;
}

.quick-action span {
  font-size: var(--text-sm);
  font-weight: 500;
}

/* Strategies Grid */
.strategies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

.strategy-item {
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.strategy-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-2);
}

.strategy-header svg {
  color: var(--color-primary);
}

.strategy-name {
  font-weight: 600;
  color: var(--text-primary);
}

.strategy-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
}

.strategy-best-for {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-style: italic;
}

/* Examples List */
.examples-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.example-item {
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200);
}

.example-item:hover {
  background: var(--bg-hover);
}

.example-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-1);
}

.example-name {
  font-weight: 500;
  color: var(--text-primary);
  text-transform: capitalize;
}

.example-strategy {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-xl);
}

.example-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
}

/* Natural Language Section */
.nl-container {
  max-width: 800px;
  margin: 0 auto;
}

.nl-header {
  text-align: center;
  margin-bottom: var(--spacing-6);
}

.nl-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2-5);
}

.nl-header h3 svg {
  color: var(--color-primary);
}

.nl-header p {
  margin: var(--spacing-2) var(--spacing-0) var(--spacing-0);
  color: var(--text-secondary);
}

.nl-input-area {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
}

.nl-input-area textarea {
  width: 100%;
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
  resize: vertical;
  font-family: inherit;
}

.nl-input-area textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}
.nl-input-area textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.nl-input-area textarea::placeholder {
  color: var(--text-muted);
}

.nl-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: var(--spacing-4) var(--spacing-0);
}

.checkbox-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.checkbox-option input {
  width: 16px;
  height: 16px;
}

.strategy-select {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.nl-actions {
  display: flex;
  justify-content: flex-end;
}

/* Approval Panel */
.approval-panel {
  margin-top: var(--spacing-6);
  background: var(--bg-secondary);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
}

.approval-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-4);
}

.approval-header svg {
  width: var(--text-xl);
  height: var(--text-xl);
  color: var(--color-warning);
}

.approval-header h4 {
  margin: var(--spacing-0);
  color: var(--text-primary);
}

.approval-summary p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  color: var(--text-secondary);
}

.approval-meta {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.approval-meta span {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.approval-steps {
  margin: var(--spacing-4) var(--spacing-0);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.approval-step {
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--border-default);
}

.approval-step.high-risk {
  border-left-color: var(--color-error);
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.step-description {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.risk-badge {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xl);
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
  padding: var(--spacing-2);
  background: var(--bg-primary);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow-x: auto;
}

.approval-actions {
  display: flex;
  gap: var(--spacing-3);
  justify-content: flex-end;
}

/* Agents Section */
.agents-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.agents-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
}

.agents-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.agents-header h3 svg {
  color: var(--color-primary);
}

.btn-refresh-sm {
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
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
  gap: var(--spacing-3);
  padding: var(--spacing-5);
  color: var(--text-tertiary);
}

.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-4);
}

.agent-card {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.agent-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-3);
}

.agent-header svg {
  width: var(--text-lg);
  height: var(--text-lg);
  color: var(--color-primary);
}

.agent-name {
  font-weight: 600;
  color: var(--text-primary);
}

.agent-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
  margin-bottom: var(--spacing-3);
}

.capability-tag {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border-radius: var(--radius-xl);
}

.agent-performance {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.agent-performance .perf-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.agent-performance .label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  min-width: 70px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-success);
  border-radius: var(--radius-default);
  transition: width var(--duration-300);
}

.agent-performance .value {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

/* Buttons */
.btn-primary {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-success {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-success);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-success:hover {
  filter: brightness(1.1);
}

.btn-danger {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-error);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
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
