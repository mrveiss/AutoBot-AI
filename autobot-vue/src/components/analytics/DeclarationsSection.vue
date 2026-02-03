<template>
  <div class="declarations-section analytics-section">
    <h3>
      <i class="fas fa-code"></i> Code Declarations
      <span v-if="declarations && declarations.length > 0" class="total-count">
        ({{ declarations.length.toLocaleString() }} total)
      </span>
    </h3>
    <div v-if="declarations && declarations.length > 0" class="section-content">
      <!-- Type Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ declarations.length.toLocaleString() }}</div>
          <div class="summary-label">Total</div>
        </div>
        <div
          v-for="(typeData, type) in declarationsByType"
          :key="type"
          class="summary-card"
          :class="getDeclarationTypeClass(String(type))"
        >
          <div class="summary-value">{{ typeData.declarations.length.toLocaleString() }}</div>
          <div class="summary-label">{{ formatDeclarationType(String(type)) }}</div>
        </div>
      </div>

      <!-- Grouped by Type (Accordion) -->
      <div class="accordion-groups">
        <div
          v-for="(typeData, type) in declarationsByType"
          :key="type"
          class="accordion-group"
        >
          <div
            class="accordion-header"
            @click="toggleDeclarationType(String(type))"
          >
            <div class="header-info">
              <i :class="expandedDeclarationTypes[type] ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">{{ formatDeclarationType(String(type)) }}</span>
              <span class="header-count">({{ typeData.declarations.length.toLocaleString() }})</span>
            </div>
            <div class="header-badges">
              <span v-if="typeData.exportedCount > 0" class="export-badge">
                {{ typeData.exportedCount }} exported
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expandedDeclarationTypes[type]" class="accordion-items">
              <div
                v-for="(declaration, index) in typeData.declarations.slice(0, 30)"
                :key="index"
                class="list-item"
                :class="{ 'item-exported': declaration.is_exported }"
              >
                <div class="item-header">
                  <span class="item-name">{{ declaration.name }}</span>
                  <span v-if="declaration.is_exported" class="export-badge small">exported</span>
                </div>
                <div class="item-location">{{ declaration.file_path }}:{{ declaration.line_number }}</div>
              </div>
              <div v-if="typeData.declarations.length > 30" class="show-more">
                <span class="muted">Showing 30 of {{ typeData.declarations.length.toLocaleString() }} {{ formatDeclarationType(String(type)).toLowerCase() }}s</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else
      icon="fas fa-code"
      message="No code declarations found or analysis not run yet."
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Declarations Section Component
 *
 * Displays code declarations grouped by type.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #704: Migrated to design tokens
 */

import { ref, computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface Declaration {
  name: string
  file_path: string
  line_number: number
  is_exported: boolean
  declaration_type?: string
}

interface Props {
  declarations: Declaration[]
}

const props = defineProps<Props>()

const expandedDeclarationTypes = ref<Record<string, boolean>>({})

const declarationsByType = computed(() => {
  const groups: Record<string, { declarations: Declaration[], exportedCount: number }> = {}
  props.declarations.forEach(d => {
    const type = d.declaration_type || 'unknown'
    if (!groups[type]) {
      groups[type] = { declarations: [], exportedCount: 0 }
    }
    groups[type].declarations.push(d)
    if (d.is_exported) groups[type].exportedCount++
  })
  return groups
})

const toggleDeclarationType = (type: string) => {
  expandedDeclarationTypes.value[type] = !expandedDeclarationTypes.value[type]
}

const formatDeclarationType = (type: string): string => {
  const labels: Record<string, string> = {
    function: 'Functions',
    class: 'Classes',
    method: 'Methods',
    variable: 'Variables',
    constant: 'Constants',
    interface: 'Interfaces',
    type: 'Types',
    unknown: 'Other'
  }
  return labels[type] || type.charAt(0).toUpperCase() + type.slice(1)
}

const getDeclarationTypeClass = (type: string): string => {
  const classes: Record<string, string> = {
    function: 'type-function',
    class: 'type-class',
    method: 'type-method',
    variable: 'type-variable',
    constant: 'type-constant',
    interface: 'type-interface',
    type: 'type-type'
  }
  return classes[type] || 'type-other'
}
</script>

<style scoped>
.declarations-section {
  margin-bottom: var(--spacing-6);
}

.declarations-section h3 {
  color: var(--color-info);
  margin-bottom: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.total-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.section-content {
  background: var(--bg-active);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.summary-cards {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-5);
}

.summary-card {
  padding: var(--spacing-3) var(--spacing-5);
  border-radius: var(--radius-lg);
  text-align: center;
  min-width: 80px;
}

.summary-card.total { background: var(--bg-active); }
.summary-card.type-function { background: var(--chart-green-bg); }
.summary-card.type-class { background: var(--chart-purple-bg); }
.summary-card.type-method { background: var(--chart-blue-bg); }
.summary-card.type-variable { background: var(--chart-orange-bg); }
.summary-card.type-constant { background: var(--chart-red-bg); }
.summary-card.type-interface { background: var(--color-info-bg); }
.summary-card.type-type { background: var(--color-primary-bg); }
.summary-card.type-other { background: var(--bg-hover); }

.summary-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.accordion-group {
  background: var(--bg-hover);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-in-out);
}

.accordion-header:hover {
  background: var(--bg-active);
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-name {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.header-count {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.export-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  background: var(--color-info-bg);
  color: var(--color-info);
}

.export-badge.small {
  font-size: 10px;
  padding: var(--spacing-px) var(--spacing-1-5);
}

.accordion-items {
  padding: 0 var(--spacing-4) var(--spacing-4);
}

.list-item {
  background: var(--bg-active);
  border-radius: var(--radius-md);
  padding: var(--spacing-2-5) var(--spacing-3);
  margin-bottom: var(--spacing-1-5);
  border-left: 3px solid var(--border-default);
}

.list-item.item-exported {
  border-left-color: var(--color-info);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-1);
}

.item-name {
  color: var(--text-primary);
  font-weight: var(--font-medium);
  font-family: var(--font-mono);
}

.item-location {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.show-more {
  text-align: center;
  padding: var(--spacing-2);
}

.muted {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.accordion-enter-active,
.accordion-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
