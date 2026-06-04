/**
 * AutoBot - Theming Pattern Example Component
 * Copyright (c) 2025 mrveiss
 * 
 * Issue #7453: Tech-debt(frontend/css) — Canonical theming pattern audit
 * 
 * This component demonstrates the canonical CSS theming pattern:
 * 1. Use Tailwind utilities for layout (flex, grid, p-4, etc.)
 * 2. Use CSS design tokens for all colors, spacing, typography
 * 3. Use scoped styles for component-specific behavior only
 * 
 * DO NOT USE THIS COMPONENT IN PRODUCTION
 * This is a documentation/reference component only.
 */

<template>
  <div class="theming-example">
    <!-- Section 1: Card with proper token usage -->
    <section class="example-section">
      <h2 class="section-title">Canonical Theming Pattern</h2>
      <p class="section-subtitle">All values come from CSS design tokens</p>

      <!-- Example: Card Component -->
      <div class="card">
        <header class="card-header">
          <h3>Card Example</h3>
          <p class="card-meta">Using design tokens correctly</p>
        </header>
        <div class="card-body">
          <p>
            This card demonstrates the recommended pattern:
          </p>
          <ul class="token-list">
            <li>
              <code>padding: var(--spacing-4)</code> — spacing from tokens
            </li>
            <li>
              <code>background: var(--bg-card)</code> — colors from tokens
            </li>
            <li>
              <code>border-radius: var(--radius-lg)</code> — radius from tokens
            </li>
            <li>
              <code>color: var(--text-primary)</code> — typography from tokens
            </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- Section 2: Button Examples -->
    <section class="example-section">
      <h2 class="section-title">Button Patterns</h2>

      <div class="button-group">
        <button class="btn btn-primary">
          Primary Action
        </button>
        <button class="btn btn-secondary">
          Secondary Action
        </button>
        <button class="btn btn-danger">
          Danger Action
        </button>
        <button class="btn btn-success">
          Success Action
        </button>
      </div>

      <div class="button-group">
        <button class="btn btn-primary" disabled>
          Disabled Primary
        </button>
        <button class="btn btn-danger" disabled>
          Disabled Danger
        </button>
      </div>
    </section>

    <!-- Section 3: Color Palette -->
    <section class="example-section">
      <h2 class="section-title">Semantic Color Tokens</h2>

      <div class="color-grid">
        <div class="color-swatch">
          <div class="swatch-box" style="background: var(--color-primary)"></div>
          <p class="swatch-label">Primary</p>
          <code>var(--color-primary)</code>
        </div>
        <div class="color-swatch">
          <div class="swatch-box" style="background: var(--color-success)"></div>
          <p class="swatch-label">Success</p>
          <code>var(--color-success)</code>
        </div>
        <div class="color-swatch">
          <div class="swatch-box" style="background: var(--color-warning)"></div>
          <p class="swatch-label">Warning</p>
          <code>var(--color-warning)</code>
        </div>
        <div class="color-swatch">
          <div class="swatch-box" style="background: var(--color-error)"></div>
          <p class="swatch-label">Error</p>
          <code>var(--color-error)</code>
        </div>
      </div>
    </section>

    <!-- Section 4: Spacing Scale -->
    <section class="example-section">
      <h2 class="section-title">Spacing Scale</h2>

      <div class="spacing-demo">
        <div class="spacing-item">
          <div class="spacing-box" style="width: var(--spacing-sm)"></div>
          <p>xs (4px)</p>
        </div>
        <div class="spacing-item">
          <div class="spacing-box" style="width: var(--spacing-md)"></div>
          <p>md (16px)</p>
        </div>
        <div class="spacing-item">
          <div class="spacing-box" style="width: var(--spacing-lg)"></div>
          <p>lg (24px)</p>
        </div>
        <div class="spacing-item">
          <div class="spacing-box" style="width: var(--spacing-xl)"></div>
          <p>xl (32px)</p>
        </div>
      </div>
    </section>

    <!-- Section 5: Status Indicators -->
    <section class="example-section">
      <h2 class="section-title">Status Indicators</h2>

      <div class="status-list">
        <div class="status-item">
          <span class="status-badge status-online">●</span>
          <span class="status-label">Online</span>
        </div>
        <div class="status-item">
          <span class="status-badge status-warning">●</span>
          <span class="status-label">Degraded</span>
        </div>
        <div class="status-item">
          <span class="status-badge status-error">●</span>
          <span class="status-label">Offline</span>
        </div>
        <div class="status-item">
          <span class="status-badge status-muted">●</span>
          <span class="status-label">Unknown</span>
        </div>
      </div>
    </section>

    <!-- Section 6: Typography -->
    <section class="example-section">
      <h2 class="section-title">Typography Scale</h2>

      <p class="text-example" style="font-size: var(--text-xs)">
        Extra small (12px) — var(--text-xs)
      </p>
      <p class="text-example" style="font-size: var(--text-sm)">
        Small (14px) — var(--text-sm)
      </p>
      <p class="text-example" style="font-size: var(--text-base)">
        Base (16px) — var(--text-base)
      </p>
      <p class="text-example" style="font-size: var(--text-lg)">
        Large (18px) — var(--text-lg)
      </p>
      <p class="text-example" style="font-size: var(--text-xl)">
        X-Large (20px) — var(--text-xl)
      </p>
    </section>

    <!-- Section 7: Form Elements -->
    <section class="example-section">
      <h2 class="section-title">Form Elements</h2>

      <div class="form-group">
        <label class="form-label" for="example-input">Text Input</label>
        <input
          id="example-input"
          type="text"
          class="form-input"
          placeholder="Type something..."
        />
      </div>

      <div class="form-group">
        <label class="form-label" for="example-select">Select</label>
        <select id="example-select" class="form-input">
          <option>Option 1</option>
          <option>Option 2</option>
          <option>Option 3</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="example-textarea">Textarea</label>
        <textarea
          id="example-textarea"
          class="form-input"
          rows="4"
          placeholder="Enter longer text..."
        ></textarea>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ============================================
 * CONTAINER
 * ============================================ */

.theming-example {
  /* Layout from logical flex properties + Tailwind-style */
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
  
  /* Spacing and colors from tokens */
  padding: var(--spacing-6);
  background: var(--bg-primary);
  color: var(--text-primary);
  
  /* Typography from tokens */
  font-family: var(--font-sans);
  line-height: var(--leading-normal);
}

/* ============================================
 * SECTIONS
 * ============================================ */

.example-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  padding: var(--spacing-6);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.section-title {
  /* Typography from tokens */
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin: 0;
}

.section-subtitle {
  /* Typography from tokens */
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

/* ============================================
 * CARD PATTERN (CANONICAL)
 * ============================================ */

.card {
  /* Spacing from tokens */
  padding: var(--card-padding);
  
  /* Colors from tokens */
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--card-radius);
  
  /* Elevation from tokens */
  box-shadow: var(--card-shadow);
}

.card-header {
  /* Spacing and borders from tokens */
  padding-bottom: var(--spacing-4);
  margin-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
  
  /* Typography from tokens */
  color: var(--text-primary);
}

.card-header h3 {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  margin: 0 0 var(--spacing-2) 0;
}

.card-meta {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.card-body {
  /* Spacing and colors from tokens */
  padding: var(--spacing-4);
  color: var(--text-secondary);
}

.token-list {
  list-style: none;
  padding: 0;
  margin: var(--spacing-4) 0 0 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.token-list li {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.token-list code {
  font-family: var(--font-mono);
  color: var(--color-primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

/* ============================================
 * BUTTON PATTERNS
 * ============================================ */

.button-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.btn {
  /* Sizing from tokens */
  height: var(--btn-height-md);
  padding: 0 var(--btn-padding-x-md);
  
  /* Typography from tokens */
  font-size: var(--btn-font-size-md);
  font-weight: var(--font-medium);
  font-family: inherit;
  
  /* Styling from tokens */
  border: none;
  border-radius: var(--btn-radius);
  cursor: pointer;
  
  /* Transitions from tokens */
  transition: var(--transition-colors);
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-primary:active {
  background: var(--color-primary-active);
}

.btn-secondary {
  background: var(--color-secondary);
  color: var(--text-on-primary);
}

.btn-secondary:hover {
  background: var(--color-secondary-hover);
}

.btn-danger {
  background: var(--color-error);
  color: var(--text-on-error);
}

.btn-danger:hover {
  background: var(--color-error-hover);
}

.btn-success {
  background: var(--color-success);
  color: var(--text-on-success);
}

.btn-success:hover {
  background: var(--color-success-hover);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ============================================
 * COLOR GRID
 * ============================================ */

.color-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-4);
}

.color-swatch {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  text-align: center;
}

.swatch-box {
  width: 100%;
  height: 80px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.swatch-label {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin: 0;
  font-weight: var(--font-medium);
}

.color-swatch code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
}

/* ============================================
 * SPACING DEMO
 * ============================================ */

.spacing-demo {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.spacing-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.spacing-box {
  height: 30px;
  background: var(--color-primary);
  border-radius: var(--radius-sm);
}

.spacing-item p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  min-width: 80px;
}

/* ============================================
 * STATUS INDICATORS
 * ============================================ */

.status-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.status-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.status-badge {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
}

.status-online {
  color: var(--color-success);
}

.status-warning {
  color: var(--color-warning);
}

.status-error {
  color: var(--color-error);
}

.status-muted {
  color: var(--text-muted);
}

.status-label {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

/* ============================================
 * TYPOGRAPHY EXAMPLES
 * ============================================ */

.text-example {
  margin: var(--spacing-2) 0;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

/* ============================================
 * FORM ELEMENTS
 * ============================================ */

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.form-label {
  /* Typography from tokens */
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.form-input {
  /* Sizing from tokens */
  height: var(--input-height-md);
  padding: 0 var(--input-padding-x);
  
  /* Colors and borders from tokens */
  background: var(--input-bg);
  color: var(--text-primary);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  
  /* Typography from tokens */
  font-family: inherit;
  font-size: var(--text-base);
  
  /* Transitions from tokens */
  transition: var(--transition-colors);
}

.form-input:focus {
  outline: none;
  border-color: var(--input-border-focus);
  box-shadow: var(--shadow-focus);
}

.form-input::placeholder {
  color: var(--text-muted);
}

/* ============================================
 * RESPONSIVE ADJUSTMENTS
 * ============================================ */

@media (max-width: 768px) {
  .theming-example {
    padding: var(--spacing-4);
    gap: var(--spacing-6);
  }

  .example-section {
    padding: var(--spacing-4);
  }

  .color-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .button-group {
    flex-direction: column;
  }

  .btn {
    width: 100%;
  }
}
</style>
