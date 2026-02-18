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
          <router-link to="/chat" class="btn btn-primary">
            <i class="fas fa-home"></i>
            <span>Go to Chat</span>
          </router-link>
          <button @click="$router.go(-1)" class="btn btn-secondary">
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
  font-size: 4rem;
  color: var(--text-muted);
}

/* ============================================
 * ERROR MESSAGING
 * ============================================ */

.error-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.error-description {
  font-size: var(--font-size-xl);
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

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  cursor: pointer;
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-inverse);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--border-color);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-color-dark);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* ============================================
 * QUICK LINKS
 * ============================================ */

.quick-links-section {
  margin-top: var(--spacing-2xl);
  padding-top: var(--spacing-2xl);
  border-top: 1px solid var(--border-color);
}

.quick-links-title {
  font-size: var(--font-size-lg);
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
  transition: all var(--transition-normal);
  text-decoration: none;
  border: 1px solid var(--border-color);
}

.quick-link-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-4px);
  border-color: var(--color-primary);
}

.quick-link-card i {
  font-size: 1.5rem;
  color: var(--color-primary);
}

.quick-link-card span {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 768px) {
  .error-icon i {
    font-size: 3rem;
  }

  .error-title {
    font-size: var(--font-size-2xl);
  }

  .error-description {
    font-size: var(--font-size-base);
  }

  .action-buttons {
    flex-direction: column;
    align-items: stretch;
  }

  .btn {
    justify-content: center;
  }

  .quick-links-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
