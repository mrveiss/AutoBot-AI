<template>
  <div class="showcase-container">
    <div class="showcase-header">
      <h1 class="showcase-title">Technical Precision Components</h1>
      <p class="showcase-subtitle">Issue #901 - Professional, data-focused component library</p>
    </div>

    <div class="showcase-grid">
      <!-- Buttons Section -->
      <BaseCard title="Buttons" subtitle="Professional button variants">
        <div class="component-section">
          <h4 class="section-heading">Variants</h4>
          <div class="button-group">
            <BaseButton variant="primary">Primary</BaseButton>
            <BaseButton variant="secondary">Secondary</BaseButton>
            <BaseButton variant="success">Success</BaseButton>
            <BaseButton variant="danger">Danger</BaseButton>
            <BaseButton variant="warning">Warning</BaseButton>
            <BaseButton variant="ghost">Ghost</BaseButton>
            <BaseButton variant="link">Link</BaseButton>
          </div>

          <h4 class="section-heading">Sizes</h4>
          <div class="button-group">
            <BaseButton size="xs">Extra Small</BaseButton>
            <BaseButton size="sm">Small</BaseButton>
            <BaseButton size="md">Medium</BaseButton>
            <BaseButton size="lg">Large</BaseButton>
            <BaseButton size="xl">Extra Large</BaseButton>
          </div>

          <h4 class="section-heading">States</h4>
          <div class="button-group">
            <BaseButton>Normal</BaseButton>
            <BaseButton disabled>Disabled</BaseButton>
            <BaseButton loading>Loading</BaseButton>
          </div>
        </div>
      </BaseCard>

      <!-- Inputs Section -->
      <BaseCard title="Inputs" subtitle="Form input components">
        <div class="component-section">
          <h4 class="section-heading">Text Input</h4>
          <BaseInput
            v-model="sampleText"
            label="Username"
            placeholder="Enter your username"
            helper-text="Choose a unique username"
          />

          <h4 class="section-heading">With Error</h4>
          <BaseInput
            v-model="sampleEmail"
            type="email"
            label="Email"
            placeholder="user@example.com"
            error="Invalid email format"
          />

          <h4 class="section-heading">Sizes</h4>
          <div class="input-stack">
            <BaseInput v-model="sampleText" size="sm" placeholder="Small input" />
            <BaseInput v-model="sampleText" size="md" placeholder="Medium input" />
            <BaseInput v-model="sampleText" size="lg" placeholder="Large input" />
          </div>

          <h4 class="section-heading">Clearable</h4>
          <BaseInput
            v-model="clearableText"
            placeholder="Type something..."
            clearable
          />
        </div>
      </BaseCard>

      <!-- Badges Section -->
      <BaseCard title="Badges" subtitle="Status indicators and labels">
        <div class="component-section">
          <h4 class="section-heading">Variants</h4>
          <div class="badge-group">
            <BaseBadge variant="default">Default</BaseBadge>
            <BaseBadge variant="primary">Primary</BaseBadge>
            <BaseBadge variant="success">Success</BaseBadge>
            <BaseBadge variant="warning">Warning</BaseBadge>
            <BaseBadge variant="error">Error</BaseBadge>
            <BaseBadge variant="info">Info</BaseBadge>
          </div>

          <h4 class="section-heading">Outline Style</h4>
          <div class="badge-group">
            <BaseBadge variant="primary" outline>Primary</BaseBadge>
            <BaseBadge variant="success" outline>Success</BaseBadge>
            <BaseBadge variant="warning" outline>Warning</BaseBadge>
            <BaseBadge variant="error" outline>Error</BaseBadge>
          </div>

          <h4 class="section-heading">Monospace (Technical Data)</h4>
          <div class="badge-group">
            <BaseBadge monospace :rounded="false">v2.1.0</BaseBadge>
            <BaseBadge monospace :rounded="false" variant="primary">main</BaseBadge>
            <BaseBadge monospace :rounded="false" variant="success">+142ms</BaseBadge>
            <BaseBadge monospace :rounded="false">SHA:a3f4c2</BaseBadge>
          </div>

          <h4 class="section-heading">Sizes</h4>
          <div class="badge-group">
            <BaseBadge size="xs">Extra Small</BaseBadge>
            <BaseBadge size="sm">Small</BaseBadge>
            <BaseBadge size="md">Medium</BaseBadge>
            <BaseBadge size="lg">Large</BaseBadge>
          </div>

          <h4 class="section-heading">Removable</h4>
          <div class="badge-group">
            <BaseBadge variant="primary" removable @remove="handleRemove">Tag 1</BaseBadge>
            <BaseBadge variant="success" removable @remove="handleRemove">Tag 2</BaseBadge>
            <BaseBadge variant="warning" removable @remove="handleRemove">Tag 3</BaseBadge>
          </div>
        </div>
      </BaseCard>

      <!-- Cards Section -->
      <BaseCard title="Cards" subtitle="Container components">
        <div class="component-section">
          <h4 class="section-heading">Variants</h4>
          <div class="card-stack">
            <BaseCard variant="default" size="sm">
              <template #header>
                <h4 style="margin: 0; font-size: 14px;">Default Card</h4>
              </template>
              <p style="margin: 0; font-size: 13px;">Standard card with border</p>
            </BaseCard>

            <BaseCard variant="bordered" size="sm">
              <template #header>
                <h4 style="margin: 0; font-size: 14px;">Bordered Card</h4>
              </template>
              <p style="margin: 0; font-size: 13px;">Thicker border for emphasis</p>
            </BaseCard>

            <BaseCard variant="elevated" size="sm">
              <template #header>
                <h4 style="margin: 0; font-size: 14px;">Elevated Card</h4>
              </template>
              <p style="margin: 0; font-size: 13px;">Shadow for depth</p>
            </BaseCard>
          </div>

          <h4 class="section-heading">With Footer</h4>
          <BaseCard variant="default" size="sm">
            <template #header>
              <h4 style="margin: 0; font-size: 14px;">Card with Footer</h4>
            </template>
            <p style="margin: 0; font-size: 13px;">Card content goes here</p>
            <template #footer>
              <BaseButton size="sm" variant="ghost">Cancel</BaseButton>
              <BaseButton size="sm" variant="primary">Save</BaseButton>
            </template>
          </BaseCard>
        </div>
      </BaseCard>

      <!-- Table Section (Full Width) -->
      <div class="showcase-full-width">
        <BaseCard title="Table" subtitle="Dense, scannable data presentation">
          <BaseTable
            :columns="tableColumns"
            :data="tableData"
            :selectable="true"
            :zebra="true"
            size="comfortable"
          >
            <template #controls>
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <BaseInput
                  v-model="tableSearch"
                  placeholder="Search..."
                  size="sm"
                  style="max-width: 300px;"
                />
                <BaseButton size="sm" variant="primary">Export</BaseButton>
              </div>
            </template>

            <template #cell-status="{ value }">
              <BaseBadge
                :variant="value === 'active' ? 'success' : value === 'pending' ? 'warning' : 'default'"
                size="sm"
              >
                {{ value }}
              </BaseBadge>
            </template>

            <template #actions="{ row }">
              <div style="display: flex; gap: 8px; justify-content: flex-end;">
                <BaseButton size="xs" variant="ghost">Edit</BaseButton>
                <BaseButton size="xs" variant="ghost">Delete</BaseButton>
              </div>
            </template>

            <template #footer>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; color: var(--text-secondary);">
                  Showing 1-5 of 5 entries
                </span>
                <div style="display: flex; gap: 4px;">
                  <BaseButton size="sm" variant="ghost" disabled>Previous</BaseButton>
                  <BaseButton size="sm" variant="ghost">Next</BaseButton>
                </div>
              </div>
            </template>
          </BaseTable>
        </BaseCard>
      </div>

      <!-- Color Palette -->
      <BaseCard title="Color Palette" subtitle="Professional slate + electric blue">
        <div class="component-section">
          <h4 class="section-heading">Electric Blue (Primary)</h4>
          <div class="color-swatches">
            <div class="color-swatch" style="background-color: #3b82f6;">
              <span class="swatch-label">Primary</span>
              <span class="swatch-hex">#3b82f6</span>
            </div>
            <div class="color-swatch" style="background-color: #2563eb;">
              <span class="swatch-label">Hover</span>
              <span class="swatch-hex">#2563eb</span>
            </div>
            <div class="color-swatch" style="background-color: #1d4ed8;">
              <span class="swatch-label">Active</span>
              <span class="swatch-hex">#1d4ed8</span>
            </div>
          </div>

          <h4 class="section-heading">Status Colors</h4>
          <div class="color-swatches">
            <div class="color-swatch" style="background-color: #10b981;">
              <span class="swatch-label">Success</span>
              <span class="swatch-hex">#10b981</span>
            </div>
            <div class="color-swatch" style="background-color: #f59e0b;">
              <span class="swatch-label">Warning</span>
              <span class="swatch-hex">#f59e0b</span>
            </div>
            <div class="color-swatch" style="background-color: #ef4444;">
              <span class="swatch-label">Error</span>
              <span class="swatch-hex">#ef4444</span>
            </div>
            <div class="color-swatch" style="background-color: #06b6d4;">
              <span class="swatch-label">Info</span>
              <span class="swatch-hex">#06b6d4</span>
            </div>
          </div>
        </div>
      </BaseCard>

      <!-- Typography -->
      <BaseCard title="Typography" subtitle="IBM Plex Sans + JetBrains Mono">
        <div class="component-section">
          <h4 class="section-heading">UI Font: IBM Plex Sans</h4>
          <div class="type-samples">
            <p style="font-size: 28px; font-weight: 600; margin: 0;">Dashboard Heading</p>
            <p style="font-size: 18px; font-weight: 600; margin: 8px 0 0 0;">Section Title</p>
            <p style="font-size: 14px; margin: 8px 0 0 0;">Body text for reading. Professional and clear.</p>
            <p style="font-size: 13px; color: var(--text-secondary); margin: 4px 0 0 0;">Secondary text and labels</p>
          </div>

          <h4 class="section-heading">Data Font: JetBrains Mono</h4>
          <div class="type-samples" style="font-family: var(--font-mono);">
            <p style="font-size: 13px; margin: 0;">192.168.1.100</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">2026-02-16T14:30:45Z</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">user_id: 1234567890</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">SHA: a3f4c2e1b7d</p>
          </div>

          <h4 class="section-heading">Numeric Font: IBM Plex Mono (Tabular)</h4>
          <div class="type-samples" style="font-family: var(--font-numeric); font-variant-numeric: tabular-nums;">
            <p style="font-size: 13px; margin: 0;">1,234.56</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">9,876.54</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">  123.00</p>
          </div>
        </div>
      </BaseCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseTable from '@/components/base/BaseTable.vue'

const logger = createLogger('ComponentShowcase')

// Sample data
const sampleText = ref('john_doe')
const sampleEmail = ref('invalid-email')
const clearableText = ref('')
const tableSearch = ref('')

const tableColumns = [
  { key: 'id', label: 'ID', sortable: true, width: '80px', monospace: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'email', label: 'Email', monospace: true },
  { key: 'count', label: 'Count', sortable: true, numeric: true, align: 'right' as const },
  { key: 'timestamp', label: 'Last Seen', sortable: true, monospace: true },
  { key: 'status', label: 'Status', sortable: true }
]

const tableData = [
  { id: 'USR-001', name: 'Alice Johnson', email: 'alice@example.com', count: 142, timestamp: '2026-02-16 14:23', status: 'active' },
  { id: 'USR-002', name: 'Bob Smith', email: 'bob@example.com', count: 89, timestamp: '2026-02-16 13:45', status: 'active' },
  { id: 'USR-003', name: 'Carol White', email: 'carol@example.com', count: 256, timestamp: '2026-02-15 18:12', status: 'pending' },
  { id: 'USR-004', name: 'David Brown', email: 'david@example.com', count: 37, timestamp: '2026-02-14 09:33', status: 'inactive' },
  { id: 'USR-005', name: 'Eve Davis', email: 'eve@example.com', count: 412, timestamp: '2026-02-16 11:58', status: 'active' }
]

const handleRemove = () => {
  logger.debug('Badge removed')
}
</script>

<style scoped>
.showcase-container {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  background-color: var(--bg-primary);
  min-height: 100vh;
}

.showcase-header {
  margin-bottom: 32px;
}

.showcase-title {
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
  font-family: var(--font-sans);
}

.showcase-subtitle {
  font-size: 16px;
  color: var(--text-secondary);
  margin: 0;
}

.showcase-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 24px;
}

.showcase-full-width {
  grid-column: 1 / -1;
}

.component-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-heading {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.button-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.input-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.badge-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.card-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.color-swatches {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.color-swatch {
  aspect-ratio: 1;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px;
  box-shadow: var(--shadow-md);
}

.swatch-label {
  font-size: 11px;
  font-weight: 600;
  color: white;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.swatch-hex {
  font-size: 10px;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.8);
}

.type-samples {
  padding: 16px;
  background-color: var(--bg-secondary);
  border-radius: 4px;
  border: 1px solid var(--border-default);
}

@media (max-width: 768px) {
  .showcase-grid {
    grid-template-columns: 1fr;
  }

  .showcase-container {
    padding: 16px;
  }
}
</style>
