<template>
  <div class="knowledge-view">
    <!-- Sidebar Navigation -->
    <aside class="knowledge-sidebar">
      <div class="sidebar-header">
        <h3><i class="fas fa-database"></i> Knowledge Base</h3>
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
          <i class="fas fa-search"></i>
          <span>Search</span>
        </router-link>

        <router-link
          to="/knowledge/categories"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-categories' }"
        >
          <i class="fas fa-folder"></i>
          <span>Categories</span>
        </router-link>

        <router-link
          to="/knowledge/graph"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-graph' }"
        >
          <i class="fas fa-project-diagram"></i>
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
          <i class="fas fa-edit"></i>
          <span>Manage</span>
        </router-link>

        <router-link
          to="/knowledge/entities"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-entities' }"
        >
          <i class="fas fa-sitemap"></i>
          <span>Entities</span>
        </router-link>

        <router-link
          to="/knowledge/maintenance"
          class="category-item"
          :class="{ active: $route.name === 'knowledge-maintenance' }"
        >
          <i class="fas fa-tools"></i>
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
          <i class="fas fa-chart-bar"></i>
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
// Issue #548: Sidebar layout matching automation/workflow style
</script>

<style scoped>
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
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-header i {
  color: var(--color-primary);
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
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-secondary);
  text-decoration: none;
  border: none;
  background: transparent;
}

.category-item:hover {
  background: var(--bg-tertiary);
}

.category-item.active {
  background: rgba(13, 148, 136, 0.1);
  color: var(--color-primary);
  border-left: 3px solid var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: 14px;
}

.category-item span {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
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
    border-bottom: 1px solid var(--border-color);
  }
}
</style>
