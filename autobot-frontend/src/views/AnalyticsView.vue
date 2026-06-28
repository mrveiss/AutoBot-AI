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

      <!-- Sub-navigation Tabs - Issue #901 / TASK 14: overflow-aware tab bar -->
      <div class="analytics-nav">
        <nav ref="tabsContainer" class="nav-tabs" role="tablist" :aria-label="$t('analytics.views.ariaLabel')">
          <router-link
            v-for="tab in visibleTabs"
            :key="tab.to"
            :to="tab.to"
            data-nav-item
            class="nav-tab"
            :class="{ 'nav-tab-active': isActive(tab) }"
            role="tab"
            :aria-selected="isActive(tab)"
            :aria-label="$t(tab.aria)"
          >
            <Icon :name="tab.icon" class="tab-icon" aria-hidden="true" />
            <span>{{ $t(tab.label) }}</span>
          </router-link>

          <!-- TASK 14: collapsed tabs live in this "More" dropdown; the active
               tab is always kept in the visible row, never hidden here. -->
          <div v-if="hasOverflow" class="more-tabs-wrapper">
            <button
              type="button"
              class="nav-tab more-tab"
              :aria-expanded="showMore"
              aria-haspopup="menu"
              :aria-label="$t('nav.moreItems')"
              @click="showMore = !showMore"
            >
              <span>{{ $t('nav.more') }}</span>
              <Icon name="chevron-down" class="tab-icon" aria-hidden="true" />
            </button>
            <div v-if="showMore" class="more-tabs-backdrop" @click="showMore = false"></div>
            <div v-if="showMore" class="more-tabs-menu" role="menu">
              <router-link
                v-for="tab in overflowTabs"
                :key="tab.to"
                :to="tab.to"
                role="menuitem"
                class="more-tabs-item"
                :class="{ active: isActive(tab) }"
                @click="showMore = false"
              >
                <Icon :name="tab.icon" class="tab-icon" aria-hidden="true" />
                <span>{{ $t(tab.label) }}</span>
              </router-link>
            </div>
          </div>
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
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import { useNavOverflow } from '@/composables/useNavOverflow'

const route = useRoute()

interface AnalyticsTab {
  to: string
  icon: IconName
  label: string
  aria: string
  /** Codebase also matches the bare /analytics root. */
  root?: boolean
}

// Single source of truth for the analytics sub-tabs (TASK 14)
const tabs: AnalyticsTab[] = [
  { to: '/analytics/codebase', icon: 'code', label: 'analytics.views.tabs.codebase', aria: 'analytics.views.tabs.codebaseAria', root: true },
  { to: '/analytics/bi', icon: 'chart-pie', label: 'analytics.views.tabs.businessIntelligence', aria: 'analytics.views.tabs.businessIntelligenceAria' },
  { to: '/analytics/security', icon: 'shield-alt', label: 'analytics.views.tabs.security', aria: 'analytics.views.tabs.securityAria' },
  { to: '/analytics/audit', icon: 'clipboard-check', label: 'analytics.views.tabs.audit', aria: 'analytics.views.tabs.auditAria' },
  { to: '/analytics/dev-tools', icon: 'bolt', label: 'analytics.views.tabs.devTools', aria: 'analytics.views.tabs.devToolsAria' },
  { to: '/analytics/usage', icon: 'chart-bar', label: 'analytics.views.tabs.usage', aria: 'analytics.views.tabs.usageAria' },
  { to: '/analytics/operations', icon: 'list-alt', label: 'analytics.views.tabs.operations', aria: 'analytics.views.tabs.operationsAria' },
  { to: '/analytics/errors', icon: 'exclamation-triangle', label: 'analytics.views.tabs.errors', aria: 'analytics.views.tabs.errorsAria' },
  { to: '/analytics/benchmark', icon: 'chart-bar', label: 'analytics.views.tabs.benchmark', aria: 'analytics.views.tabs.benchmarkAria' },
  { to: '/analytics/diagnostics', icon: 'exclamation-triangle', label: 'analytics.views.tabs.diagnostics', aria: 'analytics.views.tabs.diagnosticsAria' },
]

function isActive(tab: AnalyticsTab): boolean {
  if (tab.root && route.path === '/analytics') return true
  return route.path === tab.to || route.path.startsWith(tab.to + '/')
}

const activeIndex = computed(() => {
  const i = tabs.findIndex(isActive)
  return i < 0 ? 0 : i
})

// Overflow measurement (shared with the main nav rail)
const tabsContainer = ref<HTMLElement | null>(null)
const { visibleCount } = useNavOverflow(tabsContainer, ref(tabs.length))

// Indices rendered in the row. If the active tab would overflow, swap it into
// the last visible slot so it is never hidden inside the "More" menu.
const visibleIndices = computed<number[]>(() => {
  const vc = Math.max(1, Math.min(visibleCount.value, tabs.length))
  const indices = Array.from({ length: vc }, (_, i) => i)
  if (activeIndex.value >= vc) indices[vc - 1] = activeIndex.value
  return indices
})

const visibleTabs = computed(() => visibleIndices.value.map((i) => tabs[i]))
const overflowTabs = computed(() => tabs.filter((_, i) => !visibleIndices.value.includes(i)))
const hasOverflow = computed(() => overflowTabs.value.length > 0)

const showMore = ref(false)
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
  /* TASK 14: overflow is managed via the "More" dropdown, not a scrollbar */
  overflow: visible;
  flex-wrap: nowrap;
}

/* TASK 14: "More" overflow dropdown */
.more-tabs-wrapper {
  position: relative;
  display: inline-flex;
  align-items: stretch;
}

.more-tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-family: inherit;
}

.more-tabs-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20;
}

.more-tabs-menu {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 30;
  min-width: 12rem;
  padding: var(--spacing-1) 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}

.more-tabs-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
}

.more-tabs-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.more-tabs-item.active {
  color: var(--color-info);
  background: var(--color-info-bg);
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
