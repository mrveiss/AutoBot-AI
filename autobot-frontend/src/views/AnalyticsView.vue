<template>
  <div class="analytics-view view-container">
    <div class="analytics-content">
      <!-- Header Section - Issue #901 -->
      <div class="analytics-header">
        <div class="header-content">
          <h1 class="page-title">{{ $t('analytics.views.title') }}</h1>
          <p class="page-subtitle">{{ $t('analytics.views.subtitle') }}</p>
        </div>
      </div>

      <!-- Sub-navigation Tabs - Issue #901: Technical Precision Design -->
      <div class="analytics-nav">
        <nav class="nav-tabs" role="tablist" :aria-label="$t('analytics.views.ariaLabel')">
          <router-link
            to="/analytics/codebase"
            class="nav-tab"
            :class="{ 'nav-tab-active': isCodebaseActive }"
            role="tab"
            :aria-selected="isCodebaseActive"
            :aria-label="$t('analytics.views.tabs.codebaseAria')"
          >
            <Icon name="code" class="tab-icon" />
            <span>{{ $t('analytics.views.tabs.codebase') }}</span>
          </router-link>
          <!-- Issue #3436: code-quality, code-review, code-generation, evolution moved under codebase/:sourceId -->
          <router-link
            to="/analytics/bi"
            class="nav-tab"
            :class="{ 'nav-tab-active': isBIActive }"
            role="tab"
            :aria-selected="isBIActive"
            :aria-label="$t('analytics.views.tabs.businessIntelligenceAria')"
          >
            <Icon name="chart-pie" class="tab-icon" />
            <span>{{ $t('analytics.views.tabs.businessIntelligence') }}</span>
          </router-link>
          <router-link
            to="/analytics/security"
            class="nav-tab"
            :class="{ 'nav-tab-active': isSecurityActive }"
            role="tab"
            :aria-selected="isSecurityActive"
            :aria-label="$t('analytics.views.tabs.securityAria')"
          >
            <Icon name="shield-alt" class="tab-icon" />
            <span>{{ $t('analytics.views.tabs.security') }}</span>
          </router-link>
          <router-link
            to="/analytics/audit"
            class="nav-tab"
            :class="{ 'nav-tab-active': isAuditActive }"
            role="tab"
            :aria-selected="isAuditActive"
            :aria-label="$t('analytics.views.tabs.auditAria')"
          >
            <Icon name="clipboard-check" class="tab-icon" />
            <span>{{ $t('analytics.views.tabs.audit') }}</span>
          </router-link>
          <!-- Issue #902: Dev Tools moved from standalone /dev-speedup into analytics tab -->
          <router-link
            to="/analytics/dev-tools"
            class="nav-tab"
            :class="{ 'nav-tab-active': isDevToolsActive }"
            role="tab"
            :aria-selected="isDevToolsActive"
            aria-label="Dev Tools"
          >
            <Icon name="bolt" class="tab-icon" aria-hidden="true" />
            <span>Dev Tools</span>
          </router-link>
          <!-- Issue #4465: Usage & Costs moved from standalone nav into analytics tab -->
          <router-link
            to="/analytics/usage"
            class="nav-tab"
            :class="{ 'nav-tab-active': isUsageActive }"
            role="tab"
            :aria-selected="isUsageActive"
            :aria-label="$t('analytics.views.tabs.usageAria')"
          >
            <Icon name="chart-bar" class="tab-icon" aria-hidden="true" />
            <span>{{ $t('analytics.views.tabs.usage') }}</span>
          </router-link>
          <!-- Issue #4270: Operations moved from standalone nav into analytics tab -->
          <router-link
            to="/analytics/operations"
            class="nav-tab"
            :class="{ 'nav-tab-active': isOperationsActive }"
            role="tab"
            :aria-selected="isOperationsActive"
            :aria-label="$t('analytics.views.tabs.operationsAria')"
          >
            <Icon name="list-alt" class="tab-icon" aria-hidden="true" />
            <span>{{ $t('analytics.views.tabs.operations') }}</span>
          </router-link>
        </nav>
      </div>

      <!-- Router View for Child Components -->
      <div class="analytics-router-view">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/ui/Icon.vue'

const route = useRoute()

const isCodebaseActive = computed(() => {
  return route.path === '/analytics' || route.path === '/analytics/codebase' || route.path.startsWith('/analytics/codebase/')
})

// Issue #3436: isCodeQualityActive, isCodeReviewActive, isCodeGenerationActive, isEvolutionActive
// removed — these dashboards now live under codebase/:sourceId as child routes.

const isBIActive = computed(() => {
  return route.path === '/analytics/bi' || route.path.startsWith('/analytics/bi/')
})

const isSecurityActive = computed(() => {
  return route.path === '/analytics/security' || route.path.startsWith('/analytics/security/')
})

const isAuditActive = computed(() => {
  return route.path === '/analytics/audit' || route.path.startsWith('/analytics/audit/')
})

const isDevToolsActive = computed(() => {
  return route.path === '/analytics/dev-tools' || route.path.startsWith('/analytics/dev-tools/')
})

const isUsageActive = computed(() => {
  return route.path === '/analytics/usage' || route.path.startsWith('/analytics/usage/')
})

const isOperationsActive = computed(() => {
  return route.path === '/analytics/operations' || route.path.startsWith('/analytics/operations/')
})
</script>

<style scoped>
/* Issue #901: Technical Precision Analytics View Design */

.analytics-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.analytics-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header Section */
.analytics-header {
  padding: var(--spacing-6) var(--spacing-8) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-primary);
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  margin: var(--spacing-0);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  line-height: 1.3;
}

.page-subtitle {
  margin: var(--spacing-1-5) var(--spacing-0) var(--spacing-0) var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

/* Sub-navigation Tabs */
.analytics-nav {
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-primary);
  position: sticky;
  top: 0;
  z-index: 10;
}

.nav-tabs {
  display: flex;
  gap: var(--spacing-0-5);
  padding: var(--spacing-0) var(--spacing-8);
  max-width: 1400px;
  margin: 0 auto;
  overflow-x: auto;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: all var(--duration-150) var(--ease-in-out);
  position: relative;
  top: 1px;
  white-space: nowrap;
}

.nav-tab:hover {
  color: var(--text-primary);
  background-color: var(--bg-secondary);
}

.nav-tab-active {
  color: var(--color-info);
  border-bottom-color: var(--color-info);
  background-color: transparent;
}

.nav-tab-active:hover {
  color: var(--color-info);
  background-color: var(--color-info-bg);
}

.tab-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* Router View Container */
.analytics-router-view {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6) var(--spacing-8);
}

/* Responsive Adjustments */
@media (max-width: 768px) {
  .analytics-header {
    padding: var(--spacing-5) var(--spacing-4) var(--spacing-4);
  }

  .page-title {
    font-size: var(--text-xl);
  }

  .page-subtitle {
    font-size: var(--text-sm);
  }

  .nav-tabs {
    padding: var(--spacing-0) var(--spacing-4);
    gap: var(--spacing-0);
  }

  .nav-tab {
    padding: var(--spacing-2-5) var(--spacing-3);
    font-size: var(--text-sm);
    gap: var(--spacing-1-5);
  }

  .tab-icon {
    width: 16px;
    height: 16px;
  }

  .analytics-router-view {
    padding: var(--spacing-4);
  }
}

@media (max-width: 480px) {
  .nav-tab {
    flex: 1;
    justify-content: center;
  }

  .nav-tab span {
    display: none;
  }

  .tab-icon {
    width: 20px;
    height: 20px;
  }
}
</style>
