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
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path>
            </svg>
            <span>{{ $t('analytics.views.tabs.codebase') }}</span>
          </router-link>
          <router-link
            to="/analytics/code-quality"
            class="nav-tab"
            :class="{ 'nav-tab-active': isCodeQualityActive }"
            role="tab"
            :aria-selected="isCodeQualityActive"
            :aria-label="$t('analytics.views.tabs.codeQualityAria')"
          >
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <span>{{ $t('analytics.views.tabs.codeQuality') }}</span>
          </router-link>
          <router-link
            to="/analytics/code-review"
            class="nav-tab"
            :class="{ 'nav-tab-active': isCodeReviewActive }"
            role="tab"
            :aria-selected="isCodeReviewActive"
            :aria-label="$t('analytics.views.tabs.codeReviewAria')"
          >
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
            </svg>
            <span>{{ $t('analytics.views.tabs.codeReview') }}</span>
          </router-link>
          <router-link
            to="/analytics/code-generation"
            class="nav-tab"
            :class="{ 'nav-tab-active': isCodeGenerationActive }"
            role="tab"
            :aria-selected="isCodeGenerationActive"
            :aria-label="$t('analytics.views.tabs.codeGenerationAria')"
          >
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
            </svg>
            <span>{{ $t('analytics.views.tabs.codeGeneration') }}</span>
          </router-link>
          <router-link
            to="/analytics/evolution"
            class="nav-tab"
            :class="{ 'nav-tab-active': isEvolutionActive }"
            role="tab"
            :aria-selected="isEvolutionActive"
            :aria-label="$t('analytics.views.tabs.evolutionAria')"
          >
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path>
            </svg>
            <span>{{ $t('analytics.views.tabs.evolution') }}</span>
          </router-link>
          <router-link
            to="/analytics/bi"
            class="nav-tab"
            :class="{ 'nav-tab-active': isBIActive }"
            role="tab"
            :aria-selected="isBIActive"
            :aria-label="$t('analytics.views.tabs.businessIntelligenceAria')"
          >
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
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
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
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
            <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"></path>
            </svg>
            <span>{{ $t('analytics.views.tabs.audit') }}</span>
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

const isCodeQualityActive = computed(() => {
  return route.path === '/analytics/code-quality' || route.path.startsWith('/analytics/code-quality/')
})

const isCodeReviewActive = computed(() => {
  return route.path === '/analytics/code-review' || route.path.startsWith('/analytics/code-review/')
})

const isCodeGenerationActive = computed(() => {
  return route.path === '/analytics/code-generation' || route.path.startsWith('/analytics/code-generation/')
})

const isEvolutionActive = computed(() => {
  return route.path === '/analytics/evolution' || route.path.startsWith('/analytics/evolution/')
})

const isBIActive = computed(() => {
  return route.path === '/analytics/bi' || route.path.startsWith('/analytics/bi/')
})

const isSecurityActive = computed(() => {
  return route.path === '/analytics/security' || route.path.startsWith('/analytics/security/')
})

const isAuditActive = computed(() => {
  return route.path === '/analytics/audit' || route.path.startsWith('/analytics/audit/')
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
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  line-height: 1.3;
}

.page-subtitle {
  margin: 6px 0 0 0;
  font-size: 14px;
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
  font-size: 14px;
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
    font-size: 20px;
  }

  .page-subtitle {
    font-size: 13px;
  }

  .nav-tabs {
    padding: 0 16px;
    gap: 0;
  }

  .nav-tab {
    padding: 10px 12px;
    font-size: 13px;
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
