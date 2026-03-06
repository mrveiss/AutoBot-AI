<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #1401 - Per-Agent Cost Tracking Panel -->

<template>
  <div class="agent-cost-panel">
    <div class="section-header">
      <h3><i class="fas fa-robot"></i> {{ $t('analytics.bi.agentCosts.title') }}</h3>
      <BaseButton variant="outline" size="sm" @click="fetchAgentCosts">
        <i class="fas fa-refresh"></i> {{ $t('analytics.bi.refresh') }}
      </BaseButton>
    </div>

    <!-- Summary Cards -->
    <div class="cost-summary-row" v-if="agents.length > 0">
      <div class="summary-card">
        <i class="fas fa-dollar-sign"></i>
        <div class="summary-content">
          <div class="summary-value">${{ totalCost.toFixed(2) }}</div>
          <div class="summary-label">{{ $t('analytics.bi.agentCosts.totalSpend') }}</div>
        </div>
      </div>
      <div class="summary-card">
        <i class="fas fa-robot"></i>
        <div class="summary-content">
          <div class="summary-value">{{ agents.length }}</div>
          <div class="summary-label">{{ $t('analytics.bi.agentCosts.activeAgents') }}</div>
        </div>
      </div>
      <div class="summary-card">
        <i class="fas fa-exchange-alt"></i>
        <div class="summary-content">
          <div class="summary-value">{{ formatNumber(totalCalls) }}</div>
          <div class="summary-label">{{ $t('analytics.bi.agentCosts.totalCalls') }}</div>
        </div>
      </div>
      <div class="summary-card">
        <i class="fas fa-exclamation-triangle"></i>
        <div class="summary-content">
          <div class="summary-value" :class="{ 'text-error': exceededCount > 0 }">
            {{ exceededCount }}
          </div>
          <div class="summary-label">{{ $t('analytics.bi.agentCosts.overBudget') }}</div>
        </div>
      </div>
    </div>

    <!-- Agent Cost Table -->
    <div class="agent-cost-table" v-if="agents.length > 0">
      <table>
        <thead>
          <tr>
            <th>{{ $t('analytics.bi.agentCosts.agent') }}</th>
            <th class="text-right">{{ $t('analytics.bi.agentCosts.cost') }}</th>
            <th class="text-right">{{ $t('analytics.bi.agentCosts.calls') }}</th>
            <th class="text-right">{{ $t('analytics.bi.agentCosts.inputTokens') }}</th>
            <th class="text-right">{{ $t('analytics.bi.agentCosts.outputTokens') }}</th>
            <th>{{ $t('analytics.bi.agentCosts.budget') }}</th>
            <th class="text-right">{{ $t('analytics.bi.agentCosts.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="agent in agents" :key="agent.agent_id">
            <td class="agent-name">
              <i class="fas fa-robot agent-icon"></i>
              {{ agent.agent_id }}
            </td>
            <td class="text-right cost-cell">
              ${{ agent.cost_usd.toFixed(4) }}
            </td>
            <td class="text-right">{{ formatNumber(agent.call_count) }}</td>
            <td class="text-right">{{ formatNumber(agent.input_tokens) }}</td>
            <td class="text-right">{{ formatNumber(agent.output_tokens) }}</td>
            <td>
              <div class="budget-bar-container" v-if="agent.budget_monthly_usd > 0">
                <div class="budget-bar">
                  <div
                    class="budget-fill"
                    :class="{
                      'exceeded': agent.exceeded,
                      'warning': agent.utilization_percent >= 75 && !agent.exceeded,
                    }"
                    :style="{ width: Math.min(agent.utilization_percent, 100) + '%' }"
                  ></div>
                </div>
                <span class="budget-text" :class="{ 'text-error': agent.exceeded }">
                  {{ agent.utilization_percent.toFixed(0) }}%
                  (${{ agent.budget_monthly_usd.toFixed(2) }})
                </span>
              </div>
              <span v-else class="no-budget">{{ $t('analytics.bi.agentCosts.noBudget') }}</span>
            </td>
            <td class="text-right">
              <BaseButton
                variant="ghost"
                size="xs"
                @click="openBudgetDialog(agent.agent_id)"
                :title="$t('analytics.bi.agentCosts.setBudget')"
              >
                <i class="fas fa-edit"></i>
              </BaseButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <EmptyState
      v-else-if="!loading"
      icon="fas fa-chart-bar"
      :message="$t('analytics.bi.agentCosts.noData')"
    />

    <!-- Budget Dialog -->
    <div v-if="budgetDialog.visible" class="budget-dialog-overlay" @click.self="closeBudgetDialog">
      <div class="budget-dialog">
        <h4>{{ $t('analytics.bi.agentCosts.setBudgetFor') }} {{ budgetDialog.agentId }}</h4>
        <div class="budget-input-group">
          <label>{{ $t('analytics.bi.agentCosts.monthlyBudget') }} (USD)</label>
          <input
            v-model.number="budgetDialog.amount"
            type="number"
            min="0"
            step="0.01"
            class="budget-input"
          />
        </div>
        <div class="budget-dialog-actions">
          <BaseButton variant="secondary" size="sm" @click="closeBudgetDialog">
            {{ $t('analytics.bi.agentCosts.cancel') }}
          </BaseButton>
          <BaseButton variant="primary" size="sm" @click="saveBudget" :loading="budgetDialog.saving">
            {{ $t('analytics.bi.agentCosts.save') }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AgentCostPanel')
const { t } = useI18n()

interface AgentCost {
  agent_id: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
  call_count: number
  budget_monthly_usd: number
  utilization_percent: number
  exceeded: boolean
}

const loading = ref(false)
const agents = ref<AgentCost[]>([])
const budgetDialog = ref({
  visible: false,
  agentId: '',
  amount: 0,
  saving: false,
})

const totalCost = computed(() =>
  agents.value.reduce((sum, a) => sum + a.cost_usd, 0)
)
const totalCalls = computed(() =>
  agents.value.reduce((sum, a) => sum + a.call_count, 0)
)
const exceededCount = computed(() =>
  agents.value.filter((a) => a.exceeded).length
)

const formatNumber = (num: number): string => {
  if (!num) return '0'
  return num.toLocaleString()
}

const fetchAgentCosts = async () => {
  loading.value = true
  try {
    const res = await api.get<{ data: { agents: AgentCost[] } }>('/api/cost/by-agent')
    agents.value = res.data?.agents || []
  } catch (error) {
    logger.error('Failed to fetch agent costs:', error)
  } finally {
    loading.value = false
  }
}

const openBudgetDialog = (agentId: string) => {
  const existing = agents.value.find((a) => a.agent_id === agentId)
  budgetDialog.value = {
    visible: true,
    agentId,
    amount: existing?.budget_monthly_usd || 10,
    saving: false,
  }
}

const closeBudgetDialog = () => {
  budgetDialog.value.visible = false
}

const saveBudget = async () => {
  budgetDialog.value.saving = true
  try {
    await api.put(
      `/api/cost/by-agent/${budgetDialog.value.agentId}/budget`,
      { budget_monthly_usd: budgetDialog.value.amount }
    )
    closeBudgetDialog()
    await fetchAgentCosts()
  } catch (error) {
    logger.error('Failed to save budget:', error)
  } finally {
    budgetDialog.value.saving = false
  }
}

onMounted(() => {
  fetchAgentCosts()
})

defineExpose({ fetchAgentCosts })
</script>

<style scoped>
.agent-cost-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.section-header h3 i {
  margin-right: var(--spacing-2);
  color: var(--color-primary);
}

.cost-summary-row {
  display: flex;
  gap: var(--spacing-4);
}

.summary-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.summary-card > i {
  font-size: var(--text-xl);
  color: var(--color-primary);
  opacity: 0.8;
}

.summary-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.text-error {
  color: var(--color-error);
}

.agent-cost-table {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: auto;
}

.agent-cost-table table {
  width: 100%;
  border-collapse: collapse;
}

.agent-cost-table th,
.agent-cost-table td {
  padding: var(--spacing-3) var(--spacing-4);
  text-align: left;
  border-bottom: 1px solid var(--border-default);
  font-size: var(--text-sm);
}

.agent-cost-table th {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-weight: var(--font-semibold);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.agent-cost-table tbody tr:hover {
  background: var(--bg-tertiary);
}

.text-right {
  text-align: right;
}

.agent-name {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.agent-icon {
  color: var(--color-primary);
  opacity: 0.7;
}

.cost-cell {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.budget-bar-container {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.budget-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
  min-width: 60px;
}

.budget-fill {
  height: 100%;
  border-radius: var(--radius-full);
  background: var(--color-success);
  transition: width var(--duration-300) var(--ease-in-out);
}

.budget-fill.warning {
  background: var(--color-warning);
}

.budget-fill.exceeded {
  background: var(--color-error);
}

.budget-text {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: nowrap;
}

.no-budget {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.budget-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.budget-dialog {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  min-width: 360px;
}

.budget-dialog h4 {
  margin: 0 0 var(--spacing-4);
  color: var(--text-primary);
}

.budget-input-group {
  margin-bottom: var(--spacing-4);
}

.budget-input-group label {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.budget-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.budget-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.budget-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

@media (max-width: 768px) {
  .cost-summary-row {
    flex-wrap: wrap;
  }
  .summary-card {
    min-width: calc(50% - var(--spacing-2));
  }
}
</style>
