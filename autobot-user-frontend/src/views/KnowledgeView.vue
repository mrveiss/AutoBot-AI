<template>
  <div class="knowledge-view">
    <!-- Sidebar Navigation - Issue #901: Technical Precision Design -->
    <aside class="knowledge-sidebar">
      <div class="sidebar-header">
        <h3>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"></path>
          </svg>
          Knowledge Base
        </h3>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav">
        <div class="category-divider">
          <span>Browse</span>
        </div>

        <router-link
          to="/knowledge/search"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-search' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
          <span>Search</span>
        </router-link>

        <router-link
          to="/knowledge/categories"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-categories' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
          </svg>
          <span>Categories</span>
        </router-link>

        <router-link
          to="/knowledge/graph"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-graph' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path>
          </svg>
          <span>Graph</span>
        </router-link>

        <div class="category-divider">
          <span>Manage</span>
        </div>

        <router-link
          to="/knowledge/manage"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-manage' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
          </svg>
          <span>Manage</span>
        </router-link>

        <router-link
          to="/knowledge/entities"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-entities' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
          </svg>
          <span>Entities</span>
        </router-link>

        <router-link
          to="/knowledge/maintenance"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-maintenance' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
          </svg>
          <span>Maintenance</span>
        </router-link>

        <div class="category-divider">
          <span>Analytics</span>
        </div>

        <router-link
          to="/knowledge/stats"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-stats' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
          </svg>
          <span>Statistics</span>
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
// View-level component for knowledge base layout
// Issue #901: Technical Precision sidebar design with electric blue accents
</script>

<style scoped>
/* Issue #901: Technical Precision Knowledge View Design */

/* ============================================
 * LAYOUT - Flexbox sidebar + content
 * ============================================ */

.knowledge-view {
  display: flex;
  height: 100%;
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

/* ============================================
 * NAVIGATION
 * ============================================ */

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
  font-size: 14px;
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
 * RESPONSIVE - Mobile
 * ============================================ */

@media (max-width: 768px) {
  .knowledge-view {
    flex-direction: column;
  }

  .knowledge-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
    border-right: none;
    border-bottom: 1px solid var(--border-default);
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
    padding: 8px 16px;
  }

  .category-item span {
    font-size: 13px;
  }

  .category-divider {
    padding: 10px 16px 6px;
  }
}
</style>
