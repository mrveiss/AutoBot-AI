<template>
  <div class="analytics-view view-container">
    <!-- Load SVG sprite sheet -->
    <svg xmlns="http://www.w3.org/2000/svg" style="display: none;">
      <use href="@/assets/icons/analytics-tabs.svg"></use>
    </svg>

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
            <svg class="tab-icon" aria-hidden="true">
              <use href="#icon-analytics-codebase"></use>
            </svg>
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
            <svg class="tab-icon" aria-hidden="true">
              <use href="#icon-analytics-bi"></use>
            </svg>
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
            <svg class="tab-icon" aria-hidden="true">
              <use href="#icon-analytics-security"></use>
            </svg>
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
            <svg class="tab-icon" aria-hidden="true">
              <use href="#icon-analytics-audit"></use>
            </svg>
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
            <i class="fas fa-bolt tab-icon-fa" aria-hidden="true"></i>
            <span>Dev Tools</span>
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
</script>

<style scoped>
/* Issue #901: Technical Precision Analytics View Design */

.tab-icon-fa {
  font-size: var(--text-base);
  flex-shrink: 0;
}

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
  padding: 24px 32px 20px;
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-primary);
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  line-height: 1.3;
}

.page-subtitle {
  margin: 6px 0 0 0;
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
  gap: 2px;
  padding: 0 32px;
  max-width: 1400px;
  margin: 0 auto;
  overflow-x: auto;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
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
  padding: 24px 32px;
}

/* Responsive Adjustments */
@media (max-width: 768px) {
  .analytics-header {
    padding: 20px 16px 16px;
  }

  .page-title {
    font-size: var(--text-xl);
  }

  .page-subtitle {
    font-size: var(--text-sm);
  }

  .nav-tabs {
    padding: 0 16px;
    gap: 0;
  }

  .nav-tab {
    padding: 10px 12px;
    font-size: var(--text-sm);
    gap: 6px;
  }

  .tab-icon {
    width: 16px;
    height: 16px;
  }

  .analytics-router-view {
    padding: 16px;
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
