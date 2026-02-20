<template>
  <div class="not-found-view view-container-centered">
    <div class="not-found-content">
      <div class="not-found-inner">
        <!-- 404 Icon -->
        <div class="error-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>

        <!-- Error Message -->
        <h1 class="error-title">Page Not Found</h1>
        <p class="error-description">
          The page you're looking for doesn't exist or has been moved.
        </p>

        <!-- Navigation Options -->
        <div class="action-buttons">
          <router-link to="/chat" class="btn-action-primary">
            <i class="fas fa-home"></i>
            <span>Go to Chat</span>
          </router-link>
          <button @click="$router.go(-1)" class="btn-action-secondary">
            <i class="fas fa-arrow-left"></i>
            <span>Go Back</span>
          </button>
        </div>

        <!-- Helpful Links -->
        <div class="quick-links-section">
          <h3 class="quick-links-title">Quick Links</h3>
          <div class="quick-links-grid">
            <router-link to="/chat" class="quick-link-card">
              <i class="fas fa-comments"></i>
              <span>AI Assistant</span>
            </router-link>
            <router-link to="/knowledge" class="quick-link-card">
              <i class="fas fa-database"></i>
              <span>Knowledge Base</span>
            </router-link>
            <router-link to="/automation" class="quick-link-card">
              <i class="fas fa-bolt"></i>
              <span>Automation</span>
            </router-link>
            <router-link to="/analytics" class="quick-link-card">
              <i class="fas fa-chart-line"></i>
              <span>Analytics</span>
            </router-link>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for 404 error page
// Issue #753: Design token usage instead of Tailwind utilities
</script>

<style scoped>
/* ============================================
 * NOT FOUND VIEW - Using Design Tokens
 * ============================================ */

.not-found-content {
  width: 100%;
  padding: var(--spacing-xl) var(--spacing-md);
}

.not-found-inner {
  text-align: center;
  max-width: 800px;
  margin: 0 auto;
}

/* ============================================
 * ERROR ICON
 * ============================================ */

.error-icon {
  margin-bottom: var(--spacing-2xl);
}

.error-icon i {
  font-size: var(--text-6xl);
  color: var(--text-muted);
}

/* ============================================
 * ERROR MESSAGING
 * ============================================ */

.error-title {
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.error-description {
  font-size: var(--text-xl);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2xl);
}

/* ============================================
 * ACTION BUTTONS
 * ============================================ */

.action-buttons {
  display: flex;
  gap: var(--spacing-md);
  justify-content: center;
  flex-wrap: wrap;
  margin-bottom: var(--spacing-2xl);
}

/* Override action button sizing for 404 page */
.action-buttons .btn-action-primary,
.action-buttons .btn-action-secondary {
  padding: var(--spacing-sm) var(--spacing-lg);
  font-size: var(--text-base);
  text-decoration: none;
}

.action-buttons .btn-action-primary:hover,
.action-buttons .btn-action-secondary:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* ============================================
 * QUICK LINKS
 * ============================================ */

.quick-links-section {
  margin-top: var(--spacing-2xl);
  padding-top: var(--spacing-2xl);
  border-top: 1px solid var(--border-default);
}

.quick-links-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-lg);
}

.quick-links-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-md);
  max-width: 600px;
  margin: 0 auto;
}

.quick-link-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-200) var(--ease-in-out);
  text-decoration: none;
  border: 1px solid var(--border-default);
}

.quick-link-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-4px);
  border-color: var(--color-primary);
}

.quick-link-card i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

.quick-link-card span {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 768px) {
  .error-icon i {
    font-size: var(--text-5xl);
  }

  .error-title {
    font-size: var(--text-2xl);
  }

  .error-description {
    font-size: var(--text-base);
  }

  .action-buttons {
    flex-direction: column;
    align-items: stretch;
  }

  .action-buttons .btn-action-primary,
  .action-buttons .btn-action-secondary {
    justify-content: center;
  }

  .quick-links-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
