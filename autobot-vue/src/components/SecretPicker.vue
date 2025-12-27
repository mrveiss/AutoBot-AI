<template>
  <div class="secret-picker">
    <!-- Dropdown trigger -->
    <div class="picker-trigger" @click="toggleDropdown" :class="{ open: isOpen, disabled: disabled }">
      <div class="selected-display">
        <template v-if="selectedSecret">
          <div class="secret-badge" :style="{ backgroundColor: getTypeColor(selectedSecret.type) }">
            <i :class="getTypeIcon(selectedSecret.type)"></i>
          </div>
          <span class="secret-name">{{ selectedSecret.name }}</span>
          <span class="secret-type">({{ getTypeLabel(selectedSecret.type) }})</span>
        </template>
        <template v-else>
          <i class="fas fa-key placeholder-icon"></i>
          <span class="placeholder">{{ placeholder }}</span>
        </template>
      </div>
      <div class="picker-actions">
        <button v-if="selectedSecret && clearable" @click.stop="clearSelection" class="clear-btn" title="Clear selection">
          <i class="fas fa-times"></i>
        </button>
        <i class="fas fa-chevron-down arrow"></i>
      </div>
    </div>

    <!-- Dropdown menu -->
    <Transition name="dropdown">
      <div v-if="isOpen" class="picker-dropdown" ref="dropdownRef">
        <!-- Search -->
        <div class="dropdown-search">
          <i class="fas fa-search"></i>
          <input
            ref="searchInputRef"
            type="text"
            v-model="searchQuery"
            :placeholder="searchPlaceholder"
            @keydown.esc="closeDropdown"
            @keydown.enter="selectFirstMatch"
          />
        </div>

        <!-- Loading state -->
        <div v-if="loading" class="dropdown-loading">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading secrets...</span>
        </div>

        <!-- Empty state -->
        <div v-else-if="filteredSecrets.length === 0" class="dropdown-empty">
          <i class="fas fa-key"></i>
          <span v-if="searchQuery">No secrets match "{{ searchQuery }}"</span>
          <span v-else>No {{ filterType ? getTypeLabel(filterType) : 'secrets' }} available</span>
          <button v-if="showCreateButton" @click="handleCreateNew" class="create-link">
            <i class="fas fa-plus"></i> Create new secret
          </button>
        </div>

        <!-- Secrets list -->
        <div v-else class="dropdown-list">
          <div
            v-for="secret in filteredSecrets"
            :key="secret.id"
            class="dropdown-item"
            :class="{ selected: modelValue === secret.id }"
            @click="selectSecret(secret)"
          >
            <div class="secret-badge" :style="{ backgroundColor: getTypeColor(secret.type) }">
              <i :class="getTypeIcon(secret.type)"></i>
            </div>
            <div class="secret-info">
              <span class="secret-name">{{ secret.name }}</span>
              <span class="secret-meta">
                {{ getTypeLabel(secret.type) }}
                <span class="scope-indicator" :class="secret.scope">
                  <i :class="secret.scope === 'general' ? 'fas fa-globe' : 'fas fa-comment'"></i>
                </span>
              </span>
            </div>
            <i v-if="modelValue === secret.id" class="fas fa-check check-icon"></i>
          </div>
        </div>

        <!-- Footer actions -->
        <div v-if="showCreateButton && !loading && filteredSecrets.length > 0" class="dropdown-footer">
          <button @click="handleCreateNew" class="create-btn">
            <i class="fas fa-plus"></i> Create new secret
          </button>
        </div>
      </div>
    </Transition>

    <!-- Backdrop for mobile -->
    <div v-if="isOpen" class="picker-backdrop" @click="closeDropdown"></div>
  </div>
</template>

<script setup lang="ts">
/**
 * SecretPicker Component - Issue #211
 *
 * A reusable dropdown component for selecting secrets/credentials
 * in various parts of the AutoBot UI.
 *
 * Features:
 * - Filter by secret type (ssh_key, api_key, etc.)
 * - Filter by chat scope
 * - Search functionality
 * - Create new secret integration
 * - Keyboard navigation
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
// @ts-ignore - JavaScript API client without type declarations
import { secretsApiClient } from '../utils/SecretsApiClient';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('SecretPicker');

// Props
interface Props {
  modelValue?: string | null;
  filterType?: string | null;
  chatId?: string | null;
  includeGeneral?: boolean;
  placeholder?: string;
  disabled?: boolean;
  clearable?: boolean;
  showCreateButton?: boolean;
  searchPlaceholder?: string;
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: null,
  filterType: null,
  chatId: null,
  includeGeneral: true,
  placeholder: 'Select a secret...',
  disabled: false,
  clearable: true,
  showCreateButton: true,
  searchPlaceholder: 'Search secrets...',
});

// Emits
const emit = defineEmits<{
  (e: 'update:modelValue', value: string | null): void;
  (e: 'select', secret: any): void;
  (e: 'create-new'): void;
}>();

// State
const isOpen = ref(false);
const loading = ref(false);
const secrets = ref<any[]>([]);
const searchQuery = ref('');
const dropdownRef = ref<HTMLElement | null>(null);
const searchInputRef = ref<HTMLInputElement | null>(null);

// Credential type mappings
const typeConfig: Record<string, { icon: string; color: string; label: string }> = {
  api_key: { icon: 'fas fa-key', color: '#6366f1', label: 'API Key' },
  token: { icon: 'fas fa-ticket-alt', color: '#8b5cf6', label: 'Token' },
  password: { icon: 'fas fa-lock', color: '#ec4899', label: 'Password' },
  ssh_key: { icon: 'fas fa-terminal', color: '#14b8a6', label: 'SSH Key' },
  database_url: { icon: 'fas fa-database', color: '#f59e0b', label: 'Database' },
  certificate: { icon: 'fas fa-certificate', color: '#10b981', label: 'Certificate' },
  other: { icon: 'fas fa-ellipsis-h', color: '#6b7280', label: 'Other' },
};

// Computed
const filteredSecrets = computed(() => {
  let result = [...secrets.value];

  // Filter by type
  if (props.filterType) {
    result = result.filter((s) => s.type === props.filterType);
  }

  // Filter by scope
  if (props.chatId && !props.includeGeneral) {
    result = result.filter((s) => s.scope === 'chat' && s.chat_id === props.chatId);
  } else if (props.chatId) {
    // Include both chat-scoped for this chat and general
    result = result.filter(
      (s) => s.scope === 'general' || (s.scope === 'chat' && s.chat_id === props.chatId)
    );
  }

  // Search filter
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    result = result.filter(
      (s) =>
        s.name.toLowerCase().includes(query) ||
        s.description?.toLowerCase().includes(query)
    );
  }

  return result;
});

const selectedSecret = computed(() => {
  if (!props.modelValue) return null;
  return secrets.value.find((s) => s.id === props.modelValue) || null;
});

// Methods
function getTypeIcon(type: string): string {
  return typeConfig[type]?.icon || typeConfig.other.icon;
}

function getTypeColor(type: string): string {
  return typeConfig[type]?.color || typeConfig.other.color;
}

function getTypeLabel(type: string): string {
  return typeConfig[type]?.label || type;
}

async function loadSecrets() {
  if (loading.value) return;

  loading.value = true;
  try {
    const response = await secretsApiClient.listSecrets({
      chat_id: props.chatId,
      scope: props.includeGeneral ? undefined : 'chat',
    });
    secrets.value = response.secrets || [];
    logger.debug('Loaded secrets:', secrets.value.length);
  } catch (error) {
    logger.error('Failed to load secrets:', error);
    secrets.value = [];
  } finally {
    loading.value = false;
  }
}

function toggleDropdown() {
  if (props.disabled) return;

  if (isOpen.value) {
    closeDropdown();
  } else {
    openDropdown();
  }
}

function openDropdown() {
  isOpen.value = true;
  searchQuery.value = '';
  loadSecrets();

  // Focus search input
  nextTick(() => {
    searchInputRef.value?.focus();
  });
}

function closeDropdown() {
  isOpen.value = false;
  searchQuery.value = '';
}

function selectSecret(secret: any) {
  emit('update:modelValue', secret.id);
  emit('select', secret);
  closeDropdown();
}

function clearSelection() {
  emit('update:modelValue', null);
  emit('select', null);
}

function selectFirstMatch() {
  if (filteredSecrets.value.length > 0) {
    selectSecret(filteredSecrets.value[0]);
  }
}

function handleCreateNew() {
  closeDropdown();
  emit('create-new');
}

// Click outside handler
function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement;
  if (dropdownRef.value && !dropdownRef.value.contains(target)) {
    closeDropdown();
  }
}

// Lifecycle
onMounted(() => {
  document.addEventListener('click', handleClickOutside);

  // Load initial secrets if there's a selected value
  if (props.modelValue) {
    loadSecrets();
  }
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});

// Watch for chat context changes
watch(
  () => props.chatId,
  () => {
    if (isOpen.value) {
      loadSecrets();
    }
  }
);
</script>

<style scoped>
.secret-picker {
  position: relative;
  width: 100%;
}

.picker-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.625rem 0.875rem;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 2.75rem;
}

.picker-trigger:hover:not(.disabled) {
  border-color: var(--primary-color, #6366f1);
}

.picker-trigger.open {
  border-color: var(--primary-color, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.picker-trigger.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.selected-display {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
}

.secret-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 0.375rem;
  color: white;
  font-size: 0.75rem;
  flex-shrink: 0;
}

.secret-name {
  font-weight: 500;
  color: var(--text-primary, #f1f5f9);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.secret-type {
  color: var(--text-secondary, #94a3b8);
  font-size: 0.875rem;
}

.placeholder-icon {
  color: var(--text-tertiary, #64748b);
  font-size: 0.875rem;
}

.placeholder {
  color: var(--text-tertiary, #64748b);
}

.picker-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border: none;
  background: var(--bg-tertiary, #334155);
  color: var(--text-secondary, #94a3b8);
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s ease;
}

.clear-btn:hover {
  background: var(--danger-color, #ef4444);
  color: white;
}

.arrow {
  color: var(--text-tertiary, #64748b);
  font-size: 0.75rem;
  transition: transform 0.2s ease;
}

.picker-trigger.open .arrow {
  transform: rotate(180deg);
}

/* Dropdown */
.picker-dropdown {
  position: absolute;
  top: calc(100% + 0.375rem);
  left: 0;
  right: 0;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 0.5rem;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  z-index: 1000;
  max-height: 20rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dropdown-search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-bottom: 1px solid var(--border-color, #334155);
}

.dropdown-search i {
  color: var(--text-tertiary, #64748b);
}

.dropdown-search input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary, #f1f5f9);
  font-size: 0.875rem;
  outline: none;
}

.dropdown-search input::placeholder {
  color: var(--text-tertiary, #64748b);
}

.dropdown-loading,
.dropdown-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 2rem;
  color: var(--text-secondary, #94a3b8);
}

.dropdown-loading i,
.dropdown-empty i {
  font-size: 1.5rem;
  opacity: 0.5;
}

.create-link {
  margin-top: 0.5rem;
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: 1px solid var(--primary-color, #6366f1);
  color: var(--primary-color, #6366f1);
  border-radius: 0.375rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.create-link:hover {
  background: var(--primary-color, #6366f1);
  color: white;
}

.dropdown-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.375rem;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: background 0.15s ease;
}

.dropdown-item:hover {
  background: var(--bg-tertiary, #334155);
}

.dropdown-item.selected {
  background: rgba(99, 102, 241, 0.15);
}

.secret-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.secret-info .secret-name {
  font-size: 0.875rem;
}

.secret-meta {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--text-tertiary, #64748b);
}

.scope-indicator {
  font-size: 0.625rem;
}

.scope-indicator.general {
  color: var(--primary-color, #6366f1);
}

.scope-indicator.chat {
  color: var(--success-color, #10b981);
}

.check-icon {
  color: var(--primary-color, #6366f1);
  font-size: 0.75rem;
}

.dropdown-footer {
  padding: 0.5rem;
  border-top: 1px solid var(--border-color, #334155);
}

.create-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  padding: 0.5rem;
  background: transparent;
  border: 1px dashed var(--border-color, #334155);
  color: var(--text-secondary, #94a3b8);
  border-radius: 0.375rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.create-btn:hover {
  border-color: var(--primary-color, #6366f1);
  color: var(--primary-color, #6366f1);
}

.picker-backdrop {
  position: fixed;
  inset: 0;
  z-index: 999;
}

/* Dropdown animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}

/* Dark scrollbar */
.dropdown-list::-webkit-scrollbar {
  width: 0.375rem;
}

.dropdown-list::-webkit-scrollbar-track {
  background: transparent;
}

.dropdown-list::-webkit-scrollbar-thumb {
  background: var(--border-color, #334155);
  border-radius: 0.25rem;
}

.dropdown-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #64748b);
}
</style>
