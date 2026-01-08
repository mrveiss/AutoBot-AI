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

// Credential type mappings - using design token CSS variable references
const typeConfig: Record<string, { icon: string; color: string; label: string }> = {
  api_key: { icon: 'fas fa-key', color: 'var(--chart-indigo)', label: 'API Key' },
  token: { icon: 'fas fa-ticket-alt', color: 'var(--chart-purple)', label: 'Token' },
  password: { icon: 'fas fa-lock', color: 'var(--chart-pink)', label: 'Password' },
  ssh_key: { icon: 'fas fa-terminal', color: 'var(--chart-teal)', label: 'SSH Key' },
  database_url: { icon: 'fas fa-database', color: 'var(--chart-yellow)', label: 'Database' },
  certificate: { icon: 'fas fa-certificate', color: 'var(--chart-green)', label: 'Certificate' },
  other: { icon: 'fas fa-ellipsis-h', color: 'var(--text-tertiary)', label: 'Other' },
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
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  min-height: 2.75rem;
}

.picker-trigger:hover:not(.disabled) {
  border-color: var(--color-primary);
}

.picker-trigger.open {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.picker-trigger.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.selected-display {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex: 1;
  min-width: 0;
}

.secret-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--radius-md);
  color: var(--text-on-primary);
  font-size: var(--text-xs);
  flex-shrink: 0;
}

.secret-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.secret-type {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.placeholder-icon {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.placeholder {
  color: var(--text-tertiary);
}

.picker-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border: none;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.clear-btn:hover {
  background: var(--color-error);
  color: var(--text-on-error);
}

.arrow {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  transition: transform var(--duration-200) var(--ease-in-out);
}

.picker-trigger.open .arrow {
  transform: rotate(180deg);
}

/* Dropdown */
.picker-dropdown {
  position: absolute;
  top: calc(100% + var(--spacing-1-5));
  left: 0;
  right: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  z-index: var(--z-dropdown);
  max-height: 20rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dropdown-search {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
}

.dropdown-search i {
  color: var(--text-tertiary);
}

.dropdown-search input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.dropdown-search input::placeholder {
  color: var(--text-tertiary);
}

.dropdown-loading,
.dropdown-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.dropdown-loading i,
.dropdown-empty i {
  font-size: var(--text-2xl);
  opacity: 0.5;
}

.create-link {
  margin-top: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.create-link:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.dropdown-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-1-5);
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out);
}

.dropdown-item:hover {
  background: var(--bg-tertiary);
}

.dropdown-item.selected {
  background: var(--color-primary-bg-hover);
}

.secret-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.secret-info .secret-name {
  font-size: var(--text-sm);
}

.secret-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.scope-indicator {
  font-size: 0.625rem;
}

.scope-indicator.general {
  color: var(--color-primary);
}

.scope-indicator.chat {
  color: var(--color-success);
}

.check-icon {
  color: var(--color-primary);
  font-size: var(--text-xs);
}

.dropdown-footer {
  padding: var(--spacing-2);
  border-top: 1px solid var(--border-default);
}

.create-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2);
  background: transparent;
  border: 1px dashed var(--border-default);
  color: var(--text-secondary);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.create-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.picker-backdrop {
  position: fixed;
  inset: 0;
  z-index: calc(var(--z-dropdown) - 1);
}

/* Dropdown animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all var(--duration-200) var(--ease-in-out);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(calc(-1 * var(--spacing-2)));
}

/* Dark scrollbar */
.dropdown-list::-webkit-scrollbar {
  width: var(--spacing-1-5);
}

.dropdown-list::-webkit-scrollbar-track {
  background: transparent;
}

.dropdown-list::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-default);
}

.dropdown-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
</style>
