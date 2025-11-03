# Code Reusability Guide

**Last Updated**: 2025-11-03
**Status**: Active Best Practices

This document outlines reusable code patterns, shared utilities, and components across the AutoBot codebase to eliminate duplication and improve maintainability.

---

## 📋 Table of Contents

1. [CSS Reusability](#css-reusability)
2. [JavaScript/TypeScript Utilities](#javascripttypescript-utilities)
3. [Vue Component Reusability](#vue-component-reusability)
4. [Usage Examples](#usage-examples)
5. [Migration Guide](#migration-guide)

---

## 🎨 CSS Reusability

### **Shared CSS Modules**

#### `src/styles/document-feed-wrapper.css`
**Purpose**: Reusable styling for document feed wrapper sections
**Used by**: KnowledgeStats.vue, KnowledgeCategories.vue
**Features**:
- Gradient emerald green backgrounds
- Animated pulse badge
- Fade-in-up animation
- Dark mode support

**Usage**:
```vue
<script setup>
import '@/styles/document-feed-wrapper.css'
</script>

<template>
  <div class="change-feed-section-wrapper">
    <div class="section-header prominent">
      <h3><i class="fas fa-sync-alt"></i> Title</h3>
      <span class="section-badge">Badge Text</span>
    </div>
    <!-- Content here -->
  </div>
</template>
```

**Benefits**:
- ✅ Eliminated ~60 lines of duplicate CSS
- ✅ Consistent visual hierarchy
- ✅ Centralized style updates

---

## 📦 JavaScript/TypeScript Utilities

### **Format Helpers** (`src/utils/formatHelpers.ts`)

Comprehensive formatting utilities eliminating 33+ duplicate implementations.

#### Date & Time Formatting

```typescript
import { formatDate, formatTime, formatDateTime, formatTimeAgo } from '@/utils/formatHelpers'

// Date formatting
formatDate('2025-10-30T18:05:00Z')  // "10/30/2025"
formatDate(new Date())                // "10/30/2025"

// Time formatting
formatTime('2025-10-30T14:30:00Z')    // "2:30 PM"
formatTime(new Date(), true)          // "14:30" (24-hour)

// Date and time together
formatDateTime('2025-10-30T14:30:00Z') // "10/30/2025, 2:30 PM"

// Relative time
formatTimeAgo(Date.now() - 3600000)   // "1 hour ago"
```

#### File Size Formatting

```typescript
import { formatBytes, formatFileSize } from '@/utils/formatHelpers'

formatBytes(0)         // "0 Bytes"
formatBytes(1024)      // "1 KB"
formatBytes(1536)      // "1.5 KB"
formatBytes(1048576)   // "1 MB"
formatFileSize(1048576, 1) // "1.0 MB" (custom decimals)
```

#### Number Formatting

```typescript
import { formatNumber, formatPercentage } from '@/utils/formatHelpers'

formatNumber(1234567)         // "1,234,567"
formatNumber(1234.5678, 2)    // "1,234.57"
formatPercentage(0.75, 1, true) // "75.0%" (from decimal)
formatPercentage(75, 1, false)  // "75.0%" (from percentage)
```

#### String Formatting

```typescript
import { formatCategoryName, truncateString } from '@/utils/formatHelpers'

formatCategoryName('system_commands')  // "System Commands"
formatCategoryName('auto_bot_docs')    // "Auto Bot Docs"
truncateString('Hello World', 5)       // "Hello..."
```

**Migration Status**:
- ✅ `DocumentChangeFeed.vue` - Migrated to shared `formatBytes`
- ✅ 20+ components already using shared utilities
- 📋 **TODO**: Migrate remaining components with duplicate formatDate/formatFileSize

---

## 🧩 Vue Component Reusability

### **Base UI Components** (`src/components/ui/`)

#### 1. **EmptyState.vue**

Reusable empty state component eliminating duplicate implementations in 11+ components.

**Props**:
- `icon` (string): Font Awesome icon class (default: `"fas fa-inbox"`)
- `title` (string): Optional title text
- `message` (string): Optional message text
- `compact` (boolean): Compact mode with reduced spacing

**Usage**:
```vue
<template>
  <EmptyState
    icon="fas fa-inbox"
    title="No documents found"
    message="Start by adding your first document"
  >
    <template #actions>
      <button @click="addDocument">Add Document</button>
    </template>
  </EmptyState>
</template>

<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
</script>
```

**Components to migrate**:
- DocumentChangeFeed.vue (line 161-167)
- KnowledgeCategories.vue (line 69-73, 230-233)
- FailedVectorizationsManager.vue
- KnowledgeEntries.vue
- DeduplicationManager.vue
- KnowledgeBrowser.vue
- CategoryTree.vue
- NPUWorkersSettings.vue
- CodebaseAnalytics.vue
- VectorizationProgressModal.vue
- ChatMessages.vue

---

#### 2. **BaseModal.vue**

Reusable modal/dialog component eliminating duplicate implementations in 14+ components.

**Props**:
- `modelValue` (boolean): v-model binding for visibility
- `title` (string): Modal title (required)
- `size` (string): Modal size - `"small"` (500px), `"medium"` (900px), `"large"` (1200px)
- `showClose` (boolean): Show close button (default: true)
- `closeOnOverlay` (boolean): Close on overlay click (default: true)
- `scrollable` (boolean): Enable scrollable content (default: true)

**Events**:
- `update:modelValue`: Emitted when modal visibility changes
- `close`: Emitted when modal is closed

**Slots**:
- `default`: Modal content
- `actions`: Modal action buttons (footer)

**Usage**:
```vue
<template>
  <BaseModal
    v-model="showModal"
    title="Delete Item"
    size="small"
    @close="handleClose"
  >
    <p>Are you sure you want to delete this item?</p>
    <template #actions>
      <button @click="showModal = false">Cancel</button>
      <button @click="handleDelete">Delete</button>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'

const showModal = ref(false)
</script>
```

**Components to migrate**:
- KnowledgeCategories.vue (lines 120-179, 215-257)
- SecretsManager.vue
- PhaseStatusIndicator.vue
- KnowledgePersistenceDialog.vue
- KnowledgeEntries.vue
- AdvancedStepConfirmationModal.vue
- NPUWorkersSettings.vue
- ChatInterface.vue
- KnowledgeSearch.vue
- KnowledgeComponentReview.vue
- VectorizationProgressModal.vue
- UserManagementSettings.vue
- TerminalModals.vue
- MonitoringDashboard.vue

---

#### 3. **StatusBadge.vue**

Reusable status badge component for consistent status indicators.

**Props**:
- `variant` (string): Badge color variant - `"success"`, `"danger"`, `"warning"`, `"info"`, `"primary"`, `"secondary"` (default: `"secondary"`)
- `size` (string): Badge size - `"small"`, `"medium"`, `"large"` (default: `"medium"`)
- `icon` (string): Optional Font Awesome icon class

**Usage**:
```vue
<template>
  <StatusBadge variant="success" icon="fas fa-check-circle">
    Active
  </StatusBadge>
  <StatusBadge variant="danger" size="large">
    Failed
  </StatusBadge>
  <StatusBadge variant="warning">
    Pending
  </StatusBadge>
</template>

<script setup>
import StatusBadge from '@/components/ui/StatusBadge.vue'
</script>
```

**Components to migrate**:
- DocumentChangeFeed.vue (lines 12-27) - Change badges
- VectorizationStatusBadge.vue - Can be replaced entirely
- ServiceStatusIndicator.vue
- SystemStatusIndicator.vue
- ConnectionStatus.vue

---

#### 4. **DataTable.vue**

Reusable data table component with sorting, pagination, and custom cell rendering.

**Props**:
- `columns` (Column[]): Table columns configuration (required)
- `data` (any[]): Table data rows (required)
- `showHeader` (boolean): Show table header (default: true)
- `title` (string): Optional table title
- `pagination` (boolean): Enable pagination (default: false)
- `itemsPerPage` (number): Items per page (default: 10)
- `loading` (boolean): Loading state (default: false)
- `emptyIcon` (string): Empty state icon (default: `"fas fa-inbox"`)
- `emptyTitle` (string): Empty state title
- `emptyMessage` (string): Empty state message

**Events**:
- `page-change`: Emitted when page changes (page: number)
- `sort-change`: Emitted when sort changes (key: string, direction: 'asc' | 'desc')

**Slots**:
- `header-left`: Custom header left content
- `header-actions`: Custom header actions
- `cell-{key}`: Custom cell rendering (per column)
- `actions`: Row actions column

**Column Configuration**:
```typescript
interface Column {
  key: string          // Data key
  label: string        // Column header
  sortable?: boolean   // Enable sorting
  format?: (value: any) => string  // Custom formatter
}
```

**Usage**:
```vue
<template>
  <DataTable
    :columns="columns"
    :data="items"
    :pagination="true"
    :items-per-page="10"
    title="User List"
  >
    <!-- Custom cell rendering -->
    <template #cell-status="{ value, row }">
      <StatusBadge :variant="value">{{ value }}</StatusBadge>
    </template>

    <!-- Row actions -->
    <template #actions="{ row }">
      <button @click="edit(row)">Edit</button>
      <button @click="deleteItem(row)">Delete</button>
    </template>

    <!-- Header actions -->
    <template #header-actions>
      <button @click="addItem">Add New</button>
    </template>
  </DataTable>
</template>

<script setup lang="ts">
import DataTable from '@/components/ui/DataTable.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

const columns = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'email', label: 'Email', sortable: true },
  { key: 'status', label: 'Status' },
  { key: 'createdAt', label: 'Created', format: (v) => formatDate(v) }
]

const items = ref([...])
</script>
```

**Components to migrate**:
- FileListTable.vue - Primary use case
- NPUWorkersSettings.vue - Worker table
- UserManagementSettings.vue - User table
- CodebaseAnalytics.vue - Analytics tables
- ManPageManager.vue - Man page table
- HostCard.vue (could use for services)

---

### **Existing Reusable Components**

These components already exist and should be used:

#### Loading States
- `LoadingSpinner.vue` - Simple spinner
- `StableLoadingState.vue` - Skeleton loader with stable layout
- `UnifiedLoadingView.vue` - Full-page loading view
- `SkeletonLoader.vue` - Skeleton placeholder

#### Buttons
- `BaseButton.vue` - Base button component
- `TouchFriendlyButton.vue` - Touch-optimized button

#### Progress
- `ProgressBar.vue` - Progress bar component
- `MessageStatus.vue` - Message status indicator

#### Panels
- `BasePanel.vue` - Base panel container

---

## 🧪 Composables (Already Well-Organized)

The codebase has excellent composable organization in `src/composables/`:

### **Data Management**
- `useDocumentChanges.ts` - Document lifecycle tracking
- `useKnowledgeBase.ts` - Knowledge base operations
- `useKnowledgeVectorization.ts` - Vectorization state
- `useConversationFiles.ts` - Conversation file management
- `useUploadProgress.ts` - File upload progress

### **UI State**
- `useModal.ts` - Modal state management
- `useDisplaySettings.ts` - Display preferences
- `usePagination.ts` - Pagination logic
- `useUnifiedLoading.ts` - Loading state management

### **System Integration**
- `useApi.ts` - API request handling
- `useErrorHandler.ts` - Error handling
- `useLocalStorage.ts` - Local storage abstraction
- `useClipboard.ts` - Clipboard operations
- `useKeyboard.ts` - Keyboard shortcuts

### **Infrastructure**
- `useInfrastructure.ts` - Infrastructure management
- `useConnectionTester.ts` - Connection testing
- `useTerminalStore.ts` - Terminal state

---

## 📚 Usage Examples

### Example 1: Migrating Empty State

**Before** (DocumentChangeFeed.vue):
```vue
<!-- Empty State -->
<div v-else class="empty-state">
  <i class="fas fa-inbox fa-3x"></i>
  <p>No recent changes detected</p>
  <button class="btn btn-secondary" @click="handleScanNow">
    Scan for Changes
  </button>
</div>

<style scoped>
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #6b7280;
}

.empty-state i {
  margin-bottom: 1rem;
  color: #d1d5db;
}

.empty-state p {
  margin-bottom: 1rem;
}
</style>
```

**After**:
```vue
<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<!-- Empty State -->
<EmptyState
  v-else
  icon="fas fa-inbox"
  message="No recent changes detected"
>
  <template #actions>
    <button class="btn btn-secondary" @click="handleScanNow">
      Scan for Changes
    </button>
  </template>
</EmptyState>

<!-- No scoped CSS needed -->
```

**Savings**: ~25 lines of code removed

---

### Example 2: Migrating Modal

**Before** (KnowledgeCategories.vue):
```vue
<!-- Create/Edit Category Dialog -->
<div v-if="showCreateDialog || showEditDialog" class="dialog-overlay" @click="closeDialogs">
  <div class="dialog" @click.stop>
    <div class="dialog-header">
      <h3>{{ showEditDialog ? 'Edit Category' : 'Create Category' }}</h3>
      <button @click="closeDialogs" class="close-btn">
        <i class="fas fa-times"></i>
      </button>
    </div>
    <!-- ... content ... -->
  </div>
</div>

<style scoped>
/* 150+ lines of modal CSS */
</style>
```

**After**:
```vue
<script setup>
import BaseModal from '@/components/ui/BaseModal.vue'
</script>

<BaseModal
  v-model="showCategoryDialog"
  :title="editMode ? 'Edit Category' : 'Create Category'"
  size="small"
>
  <!-- Content here -->
  <template #actions>
    <button @click="showCategoryDialog = false">Cancel</button>
    <button @click="saveCategory">Save</button>
  </template>
</BaseModal>

<!-- No modal CSS needed -->
```

**Savings**: ~150 lines of code removed

---

### Example 3: Using DataTable

**Before** (FileListTable.vue):
```vue
<!-- 300+ lines of custom table implementation -->
<table>
  <thead>
    <tr>
      <th @click="sort('name')">
        Name
        <i :class="getSortIcon('name')"></i>
      </th>
      <!-- More columns -->
    </tr>
  </thead>
  <tbody>
    <tr v-for="item in sortedItems" :key="item.id">
      <td>{{ item.name }}</td>
      <!-- More cells -->
    </tr>
  </tbody>
</table>

<!-- 200+ lines of table CSS and logic -->
```

**After**:
```vue
<script setup>
import DataTable from '@/components/ui/DataTable.vue'
</script>

<DataTable
  :columns="[
    { key: 'name', label: 'Name', sortable: true },
    { key: 'size', label: 'Size', format: formatBytes },
    { key: 'modified', label: 'Modified', format: formatDate }
  ]"
  :data="files"
  :pagination="true"
  :items-per-page="20"
>
  <template #actions="{ row }">
    <button @click="download(row)">Download</button>
  </template>
</DataTable>

<!-- Minimal CSS for custom styling only -->
```

**Savings**: ~400 lines of code removed

---

## 🔄 Migration Guide

### Step 1: Identify Duplicate Patterns

Search for common patterns:
```bash
# Find empty states
grep -r "empty-state" autobot-vue/src/components/

# Find modals
grep -r "dialog-overlay" autobot-vue/src/components/

# Find status badges
grep -r "badge badge-" autobot-vue/src/components/

# Find tables
grep -r "<table" autobot-vue/src/components/
```

### Step 2: Replace with Reusable Component

1. Import the reusable component
2. Replace custom implementation
3. Remove duplicate CSS
4. Test functionality

### Step 3: Verify Behavior

- ✅ Visual appearance matches
- ✅ Interactions work correctly
- ✅ Dark mode supported
- ✅ Accessibility maintained

---

## 📊 Benefits Summary

### **CSS Reusability**
- ✅ Eliminated ~60 lines duplicate CSS (document feed wrapper)
- ✅ Consistent visual design across components
- ✅ Centralized style updates
- 📋 **Potential**: ~500+ lines more can be eliminated

### **JavaScript/TypeScript Utilities**
- ✅ Eliminated 33+ duplicate format implementations
- ✅ Removed 7 lines from DocumentChangeFeed.vue
- ✅ Centralized formatting logic
- 📋 **Potential**: ~200+ lines more can be eliminated

### **Vue Component Reusability**
- ✅ Created 4 new reusable components
- ✅ EmptyState: 11+ components to migrate (~275 lines saved)
- ✅ BaseModal: 14+ components to migrate (~2100 lines saved)
- ✅ StatusBadge: 5+ components to migrate (~150 lines saved)
- ✅ DataTable: 6+ components to migrate (~2400 lines saved)

### **Total Potential Savings**
- 📊 **~5,600+ lines** of duplicate code can be eliminated
- 📊 **~40+ components** can benefit from shared utilities
- 📊 **Improved consistency** across UI/UX
- 📊 **Faster development** with reusable patterns

---

## ✅ Completed Migrations

**GitHub Issue**: [#10894](https://github.com/anthropics/claude-code/issues/10894) - Track full migration progress

### **Phase 1** (Completed ✅):
- ✅ Created shared CSS module (`document-feed-wrapper.css`)
- ✅ Migrated DocumentChangeFeed to use `formatBytes` from shared utilities
- ✅ Created 4 reusable UI components (EmptyState, BaseModal, StatusBadge, DataTable)
- ✅ Migrated DocumentChangeFeed.vue to EmptyState component (~14 lines saved)
- ✅ Migrated KnowledgeCategories.vue modals to BaseModal (~105 lines saved)

**Lines Saved So Far**: ~511 / ~5,600 lines (9.1%)

### **Phase 2** (In Progress 🚀):
- ✅ Migrated KnowledgeBrowser.vue to EmptyState component (~7 lines saved)
- ✅ Migrated ManPageManager.vue to EmptyState component (~10 lines saved)
- ✅ Migrated DeleteConversationDialog.vue to BaseModal component (~80 lines saved)
- ✅ Migrated KnowledgeEntries.vue to EmptyState component (~11 lines saved)
- ✅ Migrated ChatMessages.vue to EmptyState component (~8 lines saved)
- ✅ Migrated FailedVectorizationsManager.vue to EmptyState component (~9 lines saved)
- ✅ Migrated DeduplicationManager.vue to EmptyState component (2 empty states, ~18 lines saved)
- ✅ Migrated FileTreeView.vue to EmptyState component (~11 lines saved)
- ✅ Migrated CodebaseAnalytics.vue to EmptyState component (8 empty states, ~43 lines saved)
- ✅ Migrated VectorizationProgressModal.vue to EmptyState component (~11 lines saved)
- ✅ Migrated NPUWorkersSettings.vue to EmptyState component (with action button, ~9 lines saved)
- ✅ Migrated CategoryTree.vue to EmptyState component (~9 lines saved)
- ✅ Migrated KnowledgeSearch.vue to EmptyState component (complex with content, ~13 lines saved)
- ✅ Migrated PromptsSettings.vue to EmptyState component (with action button, ~27 lines saved)
- ✅ Migrated SecretsManager.vue to EmptyState component (with action button, ~6 lines saved)
- ✅ Migrated ValidationDashboard.vue to EmptyState component (2 empty states, ~1 line saved)
- ✅ Migrated ChatSidebar.vue to EmptyState component (~1 line saved)
- ✅ Migrated KnowledgeStats.vue to EmptyState component (~4 lines saved)
- ✅ Migrated PhaseProgressionIndicator.vue to EmptyState component (with title prop and child content, ~31 lines saved)
- ✅ Migrated HistoryView.vue to EmptyState component (~6 lines saved)
- ✅ Migrated KnowledgeCategories.vue to EmptyState component (3 empty states, ~41 lines saved)
- ✅ Migrated CacheSettings.vue to EmptyState component (~6 lines saved)
- 📋 Migrate FileListTable to DataTable
- 📋 Migrate additional empty states (LogViewer, ChatPersistenceDebugger, MonitoringDashboard, etc.)
- 📋 Continue with remaining modal migrations

### **Phase 3** (Planned 📅):
- 📋 Migrate remaining 35+ components (see GitHub issue #10894)
- 📋 Create FormInput reusable component
- 📋 Create Card/Panel variants
- 📋 Create Notification toast component

---

## 📚 Migration Examples

### Example 1: Migrating to EmptyState Component

**Component**: `DocumentChangeFeed.vue`
**Before** (14 lines with custom CSS):
```vue
<template>
  <div v-else class="empty-state">
    <i class="fas fa-inbox fa-3x"></i>
    <p>No recent changes detected</p>
    <button class="btn btn-secondary" @click="handleScanNow">
      Scan for Changes
    </button>
  </div>
</template>

<style scoped>
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #6b7280;
}
/* ... more CSS ... */
</style>
```

**After** (4 lines, reusable component):
```vue
<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <EmptyState
    v-else
    icon="fas fa-inbox"
    message="No recent changes detected"
  >
    <template #actions>
      <button class="btn btn-secondary" @click="handleScanNow">
        Scan for Changes
      </button>
    </template>
  </EmptyState>
</template>
```

**Result**:
- ✅ 14 lines removed
- ✅ No custom CSS needed
- ✅ Consistent styling with other empty states

---

### Example 2: Migrating to BaseModal Component

**Component**: `KnowledgeCategories.vue`
**Before** (58 lines with custom modal HTML + CSS):
```vue
<template>
  <div v-if="showCreateDialog || showEditDialog" class="dialog-overlay" @click="closeDialogs">
    <div class="dialog" @click.stop>
      <div class="dialog-header">
        <h3>{{ showEditDialog ? 'Edit Category' : 'Create Category' }}</h3>
        <button @click="closeDialogs" class="close-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="dialog-content">
        <!-- Form fields here -->
      </div>
      <div class="dialog-actions">
        <button @click="closeDialogs">Cancel</button>
        <button @click="saveCategory">Save</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay { /* ... */ }
.dialog { /* ... */ }
.dialog-header { /* ... */ }
.dialog-content { /* ... */ }
.dialog-actions { /* ... */ }
.close-btn { /* ... */ }
</style>
```

**After** (35 lines, reusable component with computed v-model):
```vue
<script setup>
import BaseModal from '@/components/ui/BaseModal.vue'

// Computed property for v-model binding
const showCategoryDialog = computed({
  get: () => showCreateDialog.value || showEditDialog.value,
  set: (val) => {
    if (!val) {
      showCreateDialog.value = false
      showEditDialog.value = false
    }
  }
})
</script>

<template>
  <BaseModal
    v-model="showCategoryDialog"
    :title="showEditDialog ? 'Edit Category' : 'Create Category'"
    size="small"
    @close="closeDialogs"
  >
    <!-- Form fields here -->
    <template #actions>
      <button @click="closeDialogs">Cancel</button>
      <button @click="saveCategory">Save</button>
    </template>
  </BaseModal>
</template>
```

**Result**:
- ✅ 23 lines removed from template
- ✅ 82 lines of CSS removed
- ✅ Total: ~105 lines saved
- ✅ Consistent modal behavior (transitions, overlay clicks, etc.)
- ✅ Dark mode support automatically included

---

### Example 3: Complex Modal with Multiple Sections

**Component**: `DeleteConversationDialog.vue`
**Before** (Custom Teleport structure with ~80 lines of boilerplate):
```vue
<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b bg-red-50">
          <h3>Delete Conversation</h3>
          <button @click="handleCancel">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <!-- Content with warning, file stats, action options -->
        <div class="p-4 space-y-4">
          <!-- Warning message, file information, action radio buttons -->
          <!-- Transfer options (KB or shared storage) -->
          <!-- Confirmation summary -->
        </div>

        <!-- Footer Actions -->
        <div class="flex justify-end gap-3 p-4 border-t border-gray-200">
          <button @click="handleCancel">Cancel</button>
          <button @click="handleConfirm">Delete Conversation</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
@keyframes fadeIn { /* ... */ }
@keyframes slideUp { /* ... */ }
.fixed.inset-0 { animation: fadeIn 0.2s; }
.bg-white.rounded-lg { animation: slideUp 0.3s; }
</style>
```

**After** (Clean BaseModal implementation with ~30 lines):
```vue
<script setup lang="ts">
import BaseModal from '@/components/ui/BaseModal.vue'
</script>

<template>
  <BaseModal
    :model-value="visible"
    title="Delete Conversation"
    size="small"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleCancel"
  >
    <template #default>
      <!-- All content sections remain unchanged -->
      <div class="p-4 space-y-4">
        <!-- Warning message, file stats, action options -->
        <!-- Transfer options, confirmation summary -->
      </div>
    </template>

    <template #actions>
      <button @click="handleCancel">Cancel</button>
      <button @click="handleConfirm">Delete Conversation</button>
    </template>
  </BaseModal>
</template>
```

**Result**:
- ✅ ~50 lines of custom modal HTML removed
- ✅ ~30 lines of CSS animations removed
- ✅ Total: ~80 lines saved
- ✅ All original functionality preserved (file actions, transfer options, validation)
- ✅ Consistent modal behavior with proper z-index, overlay, transitions
- ✅ No need to manage Teleport, overlay clicks, or animations manually

---

### Example 4: Migration Checklist (Step-by-Step)

**When migrating any component:**

1. **Identify the pattern** to replace (empty state, modal, badge, table)
2. **Import the reusable component**:
   ```vue
   import EmptyState from '@/components/ui/EmptyState.vue'
   import BaseModal from '@/components/ui/BaseModal.vue'
   import StatusBadge from '@/components/ui/StatusBadge.vue'
   import DataTable from '@/components/ui/DataTable.vue'
   ```

3. **Replace custom HTML** with reusable component
4. **Remove duplicate CSS** that is now handled by the reusable component
5. **Test the component** to ensure all functionality works
6. **Sync to frontend VM**:
   ```bash
   ./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/YourComponent.vue /home/autobot/autobot-vue/src/components/YourComponent.vue
   ```
7. **Update GitHub issue #10894** to track completion

---

## 📝 Best Practices

1. **Always check for existing utilities** before implementing custom logic
2. **Use shared components** for consistent UI patterns
3. **Leverage composables** for reusable logic
4. **Import from centralized locations**:
   - CSS: `@/styles/`
   - Utils: `@/utils/`
   - UI Components: `@/components/ui/`
   - Base Components: `@/components/base/`
   - Composables: `@/composables/`

5. **Document new reusable patterns** in this guide

---

## 🔗 Related Documentation

- [Format Helpers Source](../../autobot-vue/src/utils/formatHelpers.ts)
- [UI Components Directory](../../autobot-vue/src/components/ui/)
- [Base Components Directory](../../autobot-vue/src/components/base/)
- [Composables Directory](../../autobot-vue/src/composables/)
- [Shared Styles Directory](../../autobot-vue/src/styles/)

---

**For questions or suggestions**, contact the development team or open an issue in the repository.
