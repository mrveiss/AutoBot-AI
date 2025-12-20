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
  margin-bottom: 24px;
}

.declarations-section h3 {
  color: #00d4ff;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.total-count {
  font-size: 0.8em;
  color: rgba(255, 255, 255, 0.6);
}

.section-content {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 16px;
}

.summary-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.summary-card {
  padding: 12px 20px;
  border-radius: 8px;
  text-align: center;
  min-width: 80px;
}

.summary-card.total { background: rgba(255, 255, 255, 0.1); }
.summary-card.type-function { background: rgba(76, 175, 80, 0.2); }
.summary-card.type-class { background: rgba(156, 39, 176, 0.2); }
.summary-card.type-method { background: rgba(0, 188, 212, 0.2); }
.summary-card.type-variable { background: rgba(255, 152, 0, 0.2); }
.summary-card.type-constant { background: rgba(233, 30, 99, 0.2); }
.summary-card.type-interface { background: rgba(33, 150, 243, 0.2); }
.summary-card.type-type { background: rgba(103, 58, 183, 0.2); }
.summary-card.type-other { background: rgba(158, 158, 158, 0.2); }

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: white;
}

.summary-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accordion-group {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
}

.accordion-header:hover {
  background: rgba(255, 255, 255, 0.1);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-name {
  font-weight: 600;
  color: white;
}

.header-count {
  color: rgba(255, 255, 255, 0.5);
  font-size: 13px;
}

.export-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(0, 212, 255, 0.2);
  color: #00d4ff;
}

.export-badge.small {
  font-size: 10px;
  padding: 1px 6px;
}

.accordion-items {
  padding: 0 16px 16px;
}

.list-item {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 6px;
  border-left: 3px solid #666;
}

.list-item.item-exported {
  border-left-color: #00d4ff;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.item-name {
  color: white;
  font-weight: 500;
  font-family: monospace;
}

.item-location {
  color: rgba(255, 255, 255, 0.5);
  font-size: 11px;
  font-family: monospace;
}

.show-more {
  text-align: center;
  padding: 8px;
}

.muted {
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
}

.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
