<!-- Issue #1359: i18n string extraction -->
<template>
  <div class="showcase-container">
    <div class="showcase-header">
      <h1 class="showcase-title">{{ $t('views.componentShowcase.title') }}</h1>
      <p class="showcase-subtitle">{{ $t('views.componentShowcase.subtitle') }}</p>
    </div>

    <div class="showcase-grid">
      <!-- Buttons Section -->
      <BaseCard :title="$t('views.componentShowcase.buttons')" :subtitle="$t('views.componentShowcase.buttonsSubtitle')">
        <div class="component-section">
          <h4 class="section-heading">{{ $t('views.componentShowcase.variants') }}</h4>
          <div class="button-group">
            <BaseButton variant="primary">{{ $t('views.componentShowcase.primary') }}</BaseButton>
            <BaseButton variant="secondary">{{ $t('views.componentShowcase.secondary') }}</BaseButton>
            <BaseButton variant="success">{{ $t('views.componentShowcase.success') }}</BaseButton>
            <BaseButton variant="danger">{{ $t('views.componentShowcase.danger') }}</BaseButton>
            <BaseButton variant="warning">{{ $t('views.componentShowcase.warning') }}</BaseButton>
            <BaseButton variant="ghost">{{ $t('views.componentShowcase.ghost') }}</BaseButton>
            <BaseButton variant="link">{{ $t('views.componentShowcase.link') }}</BaseButton>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.sizes') }}</h4>
          <div class="button-group">
            <BaseButton size="xs">{{ $t('views.componentShowcase.extraSmall') }}</BaseButton>
            <BaseButton size="sm">{{ $t('views.componentShowcase.small') }}</BaseButton>
            <BaseButton size="md">{{ $t('views.componentShowcase.medium') }}</BaseButton>
            <BaseButton size="lg">{{ $t('views.componentShowcase.large') }}</BaseButton>
            <BaseButton size="xl">{{ $t('views.componentShowcase.extraLarge') }}</BaseButton>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.states') }}</h4>
          <div class="button-group">
            <BaseButton>{{ $t('views.componentShowcase.normal') }}</BaseButton>
            <BaseButton disabled>{{ $t('views.componentShowcase.disabled') }}</BaseButton>
            <BaseButton loading>{{ $t('views.componentShowcase.loading') }}</BaseButton>
          </div>
        </div>
      </BaseCard>

      <!-- Inputs Section -->
      <BaseCard :title="$t('views.componentShowcase.inputs')" :subtitle="$t('views.componentShowcase.inputsSubtitle')">
        <div class="component-section">
          <h4 class="section-heading">{{ $t('views.componentShowcase.textInput') }}</h4>
          <BaseInput
            v-model="sampleText"
            :label="$t('views.componentShowcase.username')"
            :placeholder="$t('views.componentShowcase.usernamePlaceholder')"
            :helper-text="$t('views.componentShowcase.usernameHelper')"
          />

          <h4 class="section-heading">{{ $t('views.componentShowcase.withError') }}</h4>
          <BaseInput
            v-model="sampleEmail"
            type="email"
            :label="$t('views.componentShowcase.email')"
            placeholder="user@example.com"
            :error="$t('views.componentShowcase.emailError')"
          />

          <h4 class="section-heading">{{ $t('views.componentShowcase.sizes') }}</h4>
          <div class="input-stack">
            <BaseInput v-model="sampleText" size="sm" :placeholder="$t('views.componentShowcase.smallInput')" />
            <BaseInput v-model="sampleText" size="md" :placeholder="$t('views.componentShowcase.mediumInput')" />
            <BaseInput v-model="sampleText" size="lg" :placeholder="$t('views.componentShowcase.largeInput')" />
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.clearable') }}</h4>
          <BaseInput
            v-model="clearableText"
            :placeholder="$t('views.componentShowcase.typeSomething')"
            clearable
          />
        </div>
      </BaseCard>

      <!-- Badges Section -->
      <BaseCard :title="$t('views.componentShowcase.badges')" :subtitle="$t('views.componentShowcase.badgesSubtitle')">
        <div class="component-section">
          <h4 class="section-heading">{{ $t('views.componentShowcase.variants') }}</h4>
          <div class="badge-group">
            <BaseBadge variant="default">{{ $t('views.componentShowcase.default') }}</BaseBadge>
            <BaseBadge variant="primary">{{ $t('views.componentShowcase.primary') }}</BaseBadge>
            <BaseBadge variant="success">{{ $t('views.componentShowcase.success') }}</BaseBadge>
            <BaseBadge variant="warning">{{ $t('views.componentShowcase.warning') }}</BaseBadge>
            <BaseBadge variant="error">{{ $t('views.componentShowcase.error') }}</BaseBadge>
            <BaseBadge variant="info">{{ $t('views.componentShowcase.info') }}</BaseBadge>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.outlineStyle') }}</h4>
          <div class="badge-group">
            <BaseBadge variant="primary" outline>{{ $t('views.componentShowcase.primary') }}</BaseBadge>
            <BaseBadge variant="success" outline>{{ $t('views.componentShowcase.success') }}</BaseBadge>
            <BaseBadge variant="warning" outline>{{ $t('views.componentShowcase.warning') }}</BaseBadge>
            <BaseBadge variant="error" outline>{{ $t('views.componentShowcase.error') }}</BaseBadge>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.monospace') }}</h4>
          <div class="badge-group">
            <BaseBadge monospace :rounded="false">v2.1.0</BaseBadge>
            <BaseBadge monospace :rounded="false" variant="primary">main</BaseBadge>
            <BaseBadge monospace :rounded="false" variant="success">+142ms</BaseBadge>
            <BaseBadge monospace :rounded="false">SHA:a3f4c2</BaseBadge>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.sizes') }}</h4>
          <div class="badge-group">
            <BaseBadge size="xs">{{ $t('views.componentShowcase.extraSmall') }}</BaseBadge>
            <BaseBadge size="sm">{{ $t('views.componentShowcase.small') }}</BaseBadge>
            <BaseBadge size="md">{{ $t('views.componentShowcase.medium') }}</BaseBadge>
            <BaseBadge size="lg">{{ $t('views.componentShowcase.large') }}</BaseBadge>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.removable') }}</h4>
          <div class="badge-group">
            <BaseBadge variant="primary" removable @remove="handleRemove">Tag 1</BaseBadge>
            <BaseBadge variant="success" removable @remove="handleRemove">Tag 2</BaseBadge>
            <BaseBadge variant="warning" removable @remove="handleRemove">Tag 3</BaseBadge>
          </div>
        </div>
      </BaseCard>

      <!-- Cards Section -->
      <BaseCard :title="$t('views.componentShowcase.cards')" :subtitle="$t('views.componentShowcase.cardsSubtitle')">
        <div class="component-section">
          <h4 class="section-heading">{{ $t('views.componentShowcase.variants') }}</h4>
          <div class="card-stack">
            <BaseCard variant="default" size="sm">
              <template #header>
                <h4 style="margin: 0; font-size: 14px;">{{ $t('views.componentShowcase.defaultCard') }}</h4>
              </template>
              <p style="margin: 0; font-size: 13px;">{{ $t('views.componentShowcase.defaultCardDesc') }}</p>
            </BaseCard>

            <BaseCard variant="bordered" size="sm">
              <template #header>
                <h4 style="margin: 0; font-size: 14px;">{{ $t('views.componentShowcase.borderedCard') }}</h4>
              </template>
              <p style="margin: 0; font-size: 13px;">{{ $t('views.componentShowcase.borderedCardDesc') }}</p>
            </BaseCard>

            <BaseCard variant="elevated" size="sm">
              <template #header>
                <h4 style="margin: 0; font-size: 14px;">{{ $t('views.componentShowcase.elevatedCard') }}</h4>
              </template>
              <p style="margin: 0; font-size: 13px;">{{ $t('views.componentShowcase.elevatedCardDesc') }}</p>
            </BaseCard>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.withFooter') }}</h4>
          <BaseCard variant="default" size="sm">
            <template #header>
              <h4 style="margin: 0; font-size: 14px;">{{ $t('views.componentShowcase.cardWithFooter') }}</h4>
            </template>
            <p style="margin: 0; font-size: 13px;">{{ $t('views.componentShowcase.cardContent') }}</p>
            <template #footer>
              <BaseButton size="sm" variant="ghost">{{ $t('views.componentShowcase.cancel') }}</BaseButton>
              <BaseButton size="sm" variant="primary">{{ $t('views.componentShowcase.save') }}</BaseButton>
            </template>
          </BaseCard>
        </div>
      </BaseCard>

      <!-- Table Section (Full Width) -->
      <div class="showcase-full-width">
        <BaseCard :title="$t('views.componentShowcase.table')" :subtitle="$t('views.componentShowcase.tableSubtitle')">
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
                  :placeholder="$t('views.componentShowcase.searchPlaceholder')"
                  size="sm"
                  style="max-width: 300px;"
                />
                <BaseButton size="sm" variant="primary">{{ $t('views.componentShowcase.export') }}</BaseButton>
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
                <BaseButton size="xs" variant="ghost">{{ $t('views.componentShowcase.edit') }}</BaseButton>
                <BaseButton size="xs" variant="ghost">{{ $t('views.componentShowcase.deleteAction') }}</BaseButton>
              </div>
            </template>

            <template #footer>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; color: var(--text-secondary);">
                  {{ $t('views.componentShowcase.showingEntries', { from: 1, to: 5, total: 5 }) }}
                </span>
                <div style="display: flex; gap: 4px;">
                  <BaseButton size="sm" variant="ghost" disabled>{{ $t('views.componentShowcase.previous') }}</BaseButton>
                  <BaseButton size="sm" variant="ghost">{{ $t('views.componentShowcase.next') }}</BaseButton>
                </div>
              </div>
            </template>
          </BaseTable>
        </BaseCard>
      </div>

      <!-- Color Palette -->
      <BaseCard :title="$t('views.componentShowcase.colorPalette')" :subtitle="$t('views.componentShowcase.colorPaletteSubtitle')">
        <div class="component-section">
          <h4 class="section-heading">{{ $t('views.componentShowcase.electricBlue') }}</h4>
          <div class="color-swatches">
            <div class="color-swatch" style="background-color: #3b82f6;">
              <span class="swatch-label">{{ $t('views.componentShowcase.primary') }}</span>
              <span class="swatch-hex">#3b82f6</span>
            </div>
            <div class="color-swatch" style="background-color: #2563eb;">
              <span class="swatch-label">{{ $t('views.componentShowcase.hover') }}</span>
              <span class="swatch-hex">#2563eb</span>
            </div>
            <div class="color-swatch" style="background-color: #1d4ed8;">
              <span class="swatch-label">{{ $t('views.componentShowcase.active') }}</span>
              <span class="swatch-hex">#1d4ed8</span>
            </div>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.statusColors') }}</h4>
          <div class="color-swatches">
            <div class="color-swatch" style="background-color: #10b981;">
              <span class="swatch-label">{{ $t('views.componentShowcase.success') }}</span>
              <span class="swatch-hex">#10b981</span>
            </div>
            <div class="color-swatch" style="background-color: #f59e0b;">
              <span class="swatch-label">{{ $t('views.componentShowcase.warning') }}</span>
              <span class="swatch-hex">#f59e0b</span>
            </div>
            <div class="color-swatch" style="background-color: #ef4444;">
              <span class="swatch-label">{{ $t('views.componentShowcase.error') }}</span>
              <span class="swatch-hex">#ef4444</span>
            </div>
            <div class="color-swatch" style="background-color: #06b6d4;">
              <span class="swatch-label">{{ $t('views.componentShowcase.info') }}</span>
              <span class="swatch-hex">#06b6d4</span>
            </div>
          </div>
        </div>
      </BaseCard>

      <!-- Typography -->
      <BaseCard :title="$t('views.componentShowcase.typography')" :subtitle="$t('views.componentShowcase.typographySubtitle')">
        <div class="component-section">
          <h4 class="section-heading">{{ $t('views.componentShowcase.uiFont') }}</h4>
          <div class="type-samples">
            <p style="font-size: 28px; font-weight: 600; margin: 0;">{{ $t('views.componentShowcase.dashboardHeading') }}</p>
            <p style="font-size: 18px; font-weight: 600; margin: 8px 0 0 0;">{{ $t('views.componentShowcase.sectionTitle') }}</p>
            <p style="font-size: 14px; margin: 8px 0 0 0;">{{ $t('views.componentShowcase.bodyText') }}</p>
            <p style="font-size: 13px; color: var(--text-secondary); margin: 4px 0 0 0;">{{ $t('views.componentShowcase.secondaryText') }}</p>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.dataFont') }}</h4>
          <div class="type-samples" style="font-family: var(--font-mono);">
            <p style="font-size: 13px; margin: 0;">192.168.1.100</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">2026-02-16T14:30:45Z</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">user_id: 1234567890</p>
            <p style="font-size: 13px; margin: 4px 0 0 0;">SHA: a3f4c2e1b7d</p>
          </div>

          <h4 class="section-heading">{{ $t('views.componentShowcase.numericFont') }}</h4>
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
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseTable from '@/components/base/BaseTable.vue'

const { t } = useI18n()
const logger = createLogger('ComponentShowcase')

// Sample data
const sampleText = ref('john_doe')
const sampleEmail = ref('invalid-email')
const clearableText = ref('')
const tableSearch = ref('')

const tableColumns = computed(() => [
  { key: 'id', label: t('views.componentShowcase.colId'), sortable: true, width: '80px', monospace: true },
  { key: 'name', label: t('views.componentShowcase.colName'), sortable: true },
  { key: 'email', label: t('views.componentShowcase.colEmail'), monospace: true },
  { key: 'count', label: t('views.componentShowcase.colCount'), sortable: true, numeric: true, align: 'right' as const },
  { key: 'timestamp', label: t('views.componentShowcase.colLastSeen'), sortable: true, monospace: true },
  { key: 'status', label: t('views.componentShowcase.colStatus'), sortable: true }
])

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
.showcase-container { padding: 24px; max-width: 1400px; margin: 0 auto; background-color: var(--bg-primary); min-height: 100vh; }
.showcase-header { margin-bottom: 32px; }
.showcase-title { font-size: 32px; font-weight: 600; color: var(--text-primary); margin: 0 0 8px 0; font-family: var(--font-sans); }
.showcase-subtitle { font-size: 16px; color: var(--text-secondary); margin: 0; }
.showcase-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 24px; }
.showcase-full-width { grid-column: 1 / -1; }
.component-section { display: flex; flex-direction: column; gap: 20px; }
.section-heading { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0; padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle); }
.button-group { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.input-stack { display: flex; flex-direction: column; gap: 12px; }
.badge-group { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.card-stack { display: flex; flex-direction: column; gap: 16px; }
.color-swatches { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 12px; }
.color-swatch { aspect-ratio: 1; border-radius: 4px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 12px; box-shadow: var(--shadow-md); }
.swatch-label { font-size: 11px; font-weight: 600; color: white; text-transform: uppercase; letter-spacing: 0.05em; }
.swatch-hex { font-size: 10px; font-family: var(--font-mono); color: rgba(255, 255, 255, 0.8); }
.type-samples { padding: 16px; background-color: var(--bg-secondary); border-radius: 4px; border: 1px solid var(--border-default); }
@media (max-width: 768px) {
  .showcase-grid { grid-template-columns: 1fr; }
  .showcase-container { padding: 16px; }
}
</style>
