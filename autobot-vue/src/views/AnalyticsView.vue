<template>
  <div class="analytics-view">
    <!-- Page Header -->
    <div class="page-header">
      <div class="header-content">
        <h1><i class="fas fa-chart-pie"></i> Analytics</h1>
        <p class="subtitle">Codebase analytics and business intelligence</p>
      </div>
    </div>

    <!-- Main Section Navigation -->
    <div class="section-navigation">
      <router-link
        to="/analytics/codebase"
        :class="['section-tab', { active: isCodebaseActive }]"
      >
        <i class="fas fa-code"></i>
        Codebase Analytics
      </router-link>
      <router-link
        to="/analytics/bi"
        :class="['section-tab', { active: isBIActive }]"
      >
        <i class="fas fa-chart-line"></i>
        Business Intelligence
      </router-link>
    </div>

    <!-- Router View for Child Components -->
    <div class="analytics-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const isCodebaseActive = computed(() => {
  return route.path === '/analytics' || route.path === '/analytics/codebase' || route.path.startsWith('/analytics/codebase/')
})

const isBIActive = computed(() => {
  return route.path === '/analytics/bi' || route.path.startsWith('/analytics/bi/')
})
</script>

<style scoped>
.analytics-view {
  padding: 1.5rem;
  max-width: 1600px;
  margin: 0 auto;
  position: relative;
  min-height: 100vh;
}

/* Page Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.header-content h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.75rem;
}

.header-content h1 i {
  margin-right: 0.5rem;
  color: var(--primary-color);
}

.subtitle {
  color: var(--text-secondary);
  margin: 0.25rem 0 0;
}

/* Section Navigation */
.section-navigation {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  border-bottom: 2px solid var(--border-color);
  padding-bottom: 0;
}

.section-tab {
  padding: 0.875rem 1.5rem;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px 8px 0 0;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  font-weight: 500;
  text-decoration: none;
  position: relative;
  bottom: -2px;
  border-bottom: 2px solid transparent;
}

.section-tab:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.section-tab.active {
  background: var(--bg-secondary);
  color: var(--primary-color);
  border-bottom: 2px solid var(--primary-color);
}

.section-tab i {
  font-size: 1rem;
}

/* Analytics Content */
.analytics-content {
  background: var(--bg-secondary);
  border-radius: 0 8px 8px 8px;
  min-height: 500px;
}

/* Responsive */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 1rem;
  }

  .section-navigation {
    overflow-x: auto;
    flex-wrap: nowrap;
  }

  .section-tab {
    white-space: nowrap;
    padding: 0.75rem 1rem;
    font-size: 0.875rem;
  }
}
</style>
