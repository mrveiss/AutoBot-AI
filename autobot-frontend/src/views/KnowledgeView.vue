<template>
  <div class="knowledge-view">
    <!-- Mobile overlay backdrop -->
    <div
      v-if="showMobileSidebar"
      class="mobile-overlay"
      aria-hidden="true"
      @click="showMobileSidebar = false"
    />

    <!-- Sidebar Navigation - Issue #901: Technical Precision Design -->
    <aside
      class="knowledge-sidebar"
      :class="{ 'mobile-open': showMobileSidebar }"
    >
      <div class="sidebar-header">
        <h3>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"></path>
          </svg>
          {{ $t('knowledge.views.title') }}
        </h3>
        <button
          class="mobile-toggle"
          :aria-label="showMobileSidebar ? $t('knowledge.views.closeSidebar') : $t('knowledge.views.openSidebar')"
          :aria-expanded="showMobileSidebar"
          @click="toggleMobileSidebar"
        >
          <svg v-if="showMobileSidebar" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          <svg v-else fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav" :aria-label="$t('knowledge.views.navAriaLabel')" @click="onNavClick">
        <div class="category-divider">
          <span>{{ $t('knowledge.views.browse') }}</span>
        </div>

        <router-link
          to="/knowledge/search"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-search' }"
          :aria-label="$t('knowledge.views.searchAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
          <span>{{ $t('knowledge.views.search') }}</span>
        </router-link>

        <!-- TASK 1a: AI Documents — migrated from top nav into the Knowledge sidebar -->
        <router-link
          to="/knowledge/documents"
          class="category-item"
          :class="{ active: $route.path.startsWith('/knowledge/documents') }"
          aria-label="View and edit AI documents"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
          </svg>
          <span>AI Documents</span>
        </router-link>

        <!-- TASK 1b: Transcriber — migrated from top nav into the Knowledge sidebar -->
        <router-link
          to="/knowledge/transcriber"
          class="category-item"
          :class="{ active: $route.path.startsWith('/knowledge/transcriber') }"
          aria-label="Audio and video transcription"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"></path>
          </svg>
          <span>Transcriber</span>
        </router-link>

        <!-- Issue #1256: Observable Research Panel -->
        <router-link
          to="/knowledge/research"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-research' }"
          :aria-label="$t('knowledge.views.researchAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3
                 m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547
                 A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531
                 c0-.895-.356-1.754-.988-2.386l-.548-.547z">
            </path>
          </svg>
          <span>{{ $t('knowledge.views.research') }}</span>
        </router-link>

        <!-- MVA-2167: MCP Resources -->
        <router-link
          to="/knowledge/mcp-resources"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-mcp-resources' }"
          aria-label="Browse MCP Resources"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
            </path>
          </svg>
          <span>MCP Resources</span>
        </router-link>

        <!-- #8999: ChromaDB / vector-store explorer -->
        <router-link
          to="/knowledge/vector-store"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-vector-store' }"
          aria-label="Browse the vector store"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75">
            </path>
          </svg>
          <span>Vector Store</span>
        </router-link>

        <router-link
          to="/knowledge/categories"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-categories' }"
          :aria-label="$t('knowledge.views.categoriesAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
          </svg>
          <span>{{ $t('knowledge.views.categories') }}</span>
        </router-link>

        <router-link
          to="/knowledge/graph"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-graph' }"
          :aria-label="$t('knowledge.views.graphAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path>
          </svg>
          <span>{{ $t('knowledge.views.graph') }}</span>
        </router-link>

        <div class="category-divider">
          <span>{{ $t('knowledge.views.manage') }}</span>
        </div>

        <router-link
          to="/knowledge/manage"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-manage' }"
          :aria-label="$t('knowledge.views.manageAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
          </svg>
          <span>{{ $t('knowledge.views.manage') }}</span>
        </router-link>

        <router-link
          to="/knowledge/verification"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-verification' }"
          :aria-label="$t('knowledge.views.verificationAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
          </svg>
          <span>{{ $t('knowledge.views.verification') }}</span>
        </router-link>

        <router-link
          to="/knowledge/connectors"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-connectors' }"
          :aria-label="$t('knowledge.views.connectorsAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path>
          </svg>
          <span>{{ $t('knowledge.views.connectors') }}</span>
        </router-link>

        <router-link
          to="/knowledge/entities"
          class="category-item"
          :aria-label="$t('knowledge.views.entitiesAriaLabel')"
          :class="{ active: $route.name === 'knowledge-entities' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
          </svg>
          <span>{{ $t('knowledge.views.entities') }}</span>
        </router-link>

        <router-link
          to="/knowledge/maintenance"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-maintenance' }"
          :aria-label="$t('knowledge.views.maintenanceAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
          </svg>
          <span>{{ $t('knowledge.views.maintenance') }}</span>
        </router-link>

        <div class="category-divider">
          <span>Automation</span>
        </div>

        <router-link
          to="/knowledge/watch-folders"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-watch-folders' }"
          aria-label="Watch Folders"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
          </svg>
          <span>Watch Folders</span>
        </router-link>

        <div class="category-divider">
          <span>{{ $t('knowledge.views.analytics') }}</span>
        </div>

        <router-link
          to="/knowledge/stats"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-stats' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
          </svg>
          <span>{{ $t('knowledge.views.statistics') }}</span>
        </router-link>

        <div class="category-divider">
          <span>Research</span>
        </div>

        <!-- MVA-344: 4-tab web research panel -->
        <router-link
          to="/knowledge/web-research"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-web-research' }"
          :aria-label="$t('knowledge.webResearch.navAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <span>{{ $t('knowledge.webResearch.navLabel') }}</span>
        </router-link>

        <router-link
          to="/knowledge/web-research-settings"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-web-research-settings' }"
          :aria-label="$t('knowledge.webResearch.settingsNavAriaLabel')"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span>{{ $t('knowledge.webResearch.settingsNavLabel') }}</span>
        </router-link>
      </nav>
    </aside>

    <!-- Main Content -->
    <main class="knowledge-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const STORAGE_KEY = 'knowledge-sidebar-mobile-open'

const showMobileSidebar = ref(false)

onMounted(() => {
  const saved = localStorage.getItem(STORAGE_KEY)
  showMobileSidebar.value = saved === 'true'
})

function toggleMobileSidebar() {
  showMobileSidebar.value = !showMobileSidebar.value
  localStorage.setItem(STORAGE_KEY, String(showMobileSidebar.value))
}

function onNavClick(e: Event) {
  if (window.innerWidth <= 768 && showMobileSidebar.value) {
    const target = e.target as HTMLElement
    if (target.closest('a')) {
      showMobileSidebar.value = false
      localStorage.setItem(STORAGE_KEY, 'false')
    }
  }
}
</script>

<style scoped>
/* Issue #901: Technical Precision Knowledge View Design */

/* ============================================
 * LAYOUT - Flexbox sidebar + content
 * ============================================ */

.knowledge-view {
  contain: layout style paint;
  display: flex;
  min-height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* ============================================
 * SIDEBAR
 * ============================================ */

.knowledge-sidebar {
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

/* ============================================
 * NAVIGATION
 * ============================================ */

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

.category-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-5);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
  color: var(--text-secondary);
  text-decoration: none;
  border: none;
  background: transparent;
  border-left: 2px solid transparent;
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

.category-item span {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: var(--font-sans);
}

/* ============================================
 * MAIN CONTENT
 * ============================================ */

.knowledge-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  min-width: 0;
  background: var(--bg-primary);
}

/* ============================================
 * MOBILE TOGGLE BUTTON (hidden on desktop)
 * ============================================ */

.mobile-toggle {
  display: none;
}

/* ============================================
 * MOBILE OVERLAY
 * ============================================ */

.mobile-overlay {
  display: none;
}

/* ============================================
 * RESPONSIVE - Mobile
 * ============================================ */

@media (max-width: 768px) {
  .knowledge-view {
    flex-direction: column;
    position: relative;
  }

  /* Collapsed header strip — no 50vh content, just the header bar */
  .knowledge-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: none;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--border-default);
    overflow: hidden;
    position: relative;
    z-index: 200;
  }

  /* Hide nav in collapsed state */
  .knowledge-sidebar:not(.mobile-open) .category-nav {
    display: none;
  }

  /* Expanded drawer — overlays content, full-height */
  .knowledge-sidebar.mobile-open {
    position: fixed;
    top: 0;
    left: 0;
    width: 80vw;
    max-width: 320px;
    height: 100dvh;
    z-index: 300;
    border-right: 1px solid var(--border-default);
    border-bottom: none;
    overflow-y: auto;
  }

  /* Overlay backdrop */
  .mobile-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 299;
  }

  /* Toggle button visible on mobile */
  .mobile-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: transparent;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md, 6px);
    color: var(--text-secondary);
    cursor: pointer;
    flex-shrink: 0;
    transition: background var(--duration-150) var(--ease-in-out);
  }

  .mobile-toggle:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .mobile-toggle svg {
    width: 18px;
    height: 18px;
  }

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .sidebar-header h3 {
    font-size: 15px;
  }

  .header-icon,
  .item-icon {
    width: 16px;
    height: 16px;
  }

  .category-item {
    padding: var(--spacing-3) var(--spacing-4);
    min-height: 44px;
  }

  .category-item span {
    font-size: var(--text-sm);
  }

  .category-divider {
    padding: var(--spacing-2-5) var(--spacing-4) var(--spacing-1-5);
  }
}
</style>
