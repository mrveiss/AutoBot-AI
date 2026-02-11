<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="knowledge-graph-view">
    <!-- Sidebar -->
    <aside class="graph-sidebar">
      <div class="sidebar-header">
        <h3><i class="fas fa-project-diagram"></i> Knowledge Graph</h3>
      </div>

      <!-- Quick Stats -->
      <div class="quick-stats">
        <div class="stat-row">
          <i class="fas fa-circle"></i>
          <span class="stat-label">Entities</span>
          <span class="stat-value">{{ stats.entityCount }}</span>
        </div>
        <div class="stat-row">
          <i class="fas fa-clock"></i>
          <span class="stat-label">Events</span>
          <span class="stat-value">{{ stats.eventCount }}</span>
        </div>
        <div class="stat-row">
          <i class="fas fa-layer-group"></i>
          <span class="stat-label">Summaries</span>
          <span class="stat-value">{{ stats.summaryCount }}</span>
        </div>
      </div>

      <!-- Tab Navigation -->
      <nav class="graph-nav">
        <router-link
          v-for="tab in tabs"
          :key="tab.route"
          :to="tab.route"
          class="nav-item"
          :class="{ active: isActiveTab(tab.route) }"
        >
          <i :class="tab.icon"></i>
          <span>{{ tab.label }}</span>
        </router-link>
      </nav>

      <!-- Back Link -->
      <div class="sidebar-footer">
        <router-link to="/knowledge" class="back-link">
          <i class="fas fa-arrow-left"></i>
          Back to Knowledge Base
        </router-link>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="graph-content">
      <router-view />

      <!-- Default Content (when no child route is active) -->
      <div
        v-if="isRootRoute"
        class="default-content"
      >
        <div class="welcome-card">
          <h2>
            <i class="fas fa-project-diagram"></i>
            Knowledge Graph Pipeline
          </h2>
          <p>
            Extract entities, relationships, and temporal events from
            documents. Generate hierarchical summaries with drill-down
            capability.
          </p>

          <div class="feature-grid">
            <div
              v-for="tab in tabs"
              :key="tab.route"
              class="feature-card"
              @click="navigateTo(tab.route)"
            >
              <i :class="tab.icon" class="feature-icon"></i>
              <h4>{{ tab.label }}</h4>
              <p>{{ tab.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useKnowledgeGraph } from '@/composables/useKnowledgeGraph'

const route = useRoute()
const router = useRouter()
const { stats } = useKnowledgeGraph()

const tabs = [
  {
    route: '/knowledge/graph/pipeline',
    label: 'Pipeline',
    icon: 'fas fa-play-circle',
    description: 'Run document processing pipelines to extract knowledge',
  },
  {
    route: '/knowledge/graph/entities',
    label: 'Entities',
    icon: 'fas fa-project-diagram',
    description: 'Search and explore entities and their relationships',
  },
  {
    route: '/knowledge/graph/timeline',
    label: 'Timeline',
    icon: 'fas fa-stream',
    description: 'View temporal events and causal chains',
  },
  {
    route: '/knowledge/graph/summaries',
    label: 'Summaries',
    icon: 'fas fa-layer-group',
    description: 'Browse hierarchical document summaries',
  },
]

const isRootRoute = computed(() => {
  return route.path === '/knowledge/graph' ||
    route.path === '/knowledge/graph/'
})

function isActiveTab(tabRoute: string): boolean {
  return route.path.startsWith(tabRoute)
}

function navigateTo(path: string): void {
  router.push(path)
}
</script>

<style scoped>
.knowledge-graph-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.graph-sidebar {
  width: 240px;
  min-width: 240px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--border-color);
}

.sidebar-header h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.sidebar-header h3 i {
  color: var(--color-primary);
}

/* Quick Stats */
.quick-stats {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.stat-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
}

.stat-row i {
  color: var(--color-primary);
  width: 16px;
  text-align: center;
  font-size: var(--text-xs);
}

.stat-row .stat-label {
  flex: 1;
  color: var(--text-secondary);
}

.stat-row .stat-value {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

/* Navigation */
.graph-nav {
  flex: 1;
  padding: var(--spacing-sm) 0;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all 0.15s;
}

.nav-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(13, 148, 136, 0.1);
  color: var(--color-primary);
  border-left: 3px solid var(--color-primary);
}

.nav-item i {
  width: 18px;
  text-align: center;
  font-size: var(--text-sm);
}

/* Footer */
.sidebar-footer {
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--border-color);
}

.back-link {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--text-tertiary);
  text-decoration: none;
  font-size: var(--text-sm);
  transition: color 0.15s;
}

.back-link:hover {
  color: var(--color-primary);
}

/* Main Content */
.graph-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  min-width: 0;
}

/* Default Content */
.default-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg);
}

.welcome-card {
  max-width: 700px;
  text-align: center;
}

.welcome-card h2 {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-sm) 0;
}

.welcome-card h2 i {
  color: var(--color-primary);
}

.welcome-card > p {
  font-size: var(--text-base);
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 var(--spacing-xl) 0;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
}

.feature-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  text-align: left;
  cursor: pointer;
  transition: all var(--duration-200);
}

.feature-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.feature-icon {
  font-size: var(--text-xl);
  color: var(--color-primary);
  margin-bottom: var(--spacing-sm);
}

.feature-card h4 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.feature-card p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

/* Responsive */
@media (max-width: 768px) {
  .knowledge-graph-view {
    flex-direction: column;
  }

  .graph-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
  }

  .quick-stats {
    display: none;
  }

  .graph-nav {
    display: flex;
    flex-direction: row;
    overflow-x: auto;
    padding: var(--spacing-xs);
  }

  .nav-item {
    white-space: nowrap;
    padding: var(--spacing-xs) var(--spacing-md);
  }

  .nav-item.active {
    border-left: none;
    border-bottom: 2px solid var(--color-primary);
  }

  .sidebar-footer {
    display: none;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
