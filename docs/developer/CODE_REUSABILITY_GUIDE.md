# Code Reusability Guide

**Last Updated**: 2025-11-07
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

### **Format Helpers** (`autobot-user-backend/utils/formatHelpers.ts`)

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
grep -r "empty-state" autobot-user-frontend/src/components/

# Find modals
grep -r "dialog-overlay" autobot-user-frontend/src/components/

# Find status badges
grep -r "badge badge-" autobot-user-frontend/src/components/

# Find tables
grep -r "<table" autobot-user-frontend/src/components/
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

**Lines Saved So Far**: ~579 / ~5,600 lines (10.3%)

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
- ✅ Migrated MonitoringDashboard.vue to EmptyState component (3 compact empty states, ~6 lines saved)
- ✅ Migrated FileListTable.vue to EmptyState component (improved semantic structure, ~8 lines saved)
- ✅ Migrated LogViewer.vue to EmptyState component (compact placeholder, ~1 line saved)
- ✅ Migrated WorkflowApproval.vue to EmptyState component (~1 line saved)
- ✅ Migrated AsyncErrorBoundaryDemo.vue to EmptyState component (~14 lines saved)
- ✅ Migrated InfrastructureManager.vue to EmptyState component (with action button, ~15 lines saved)
- ✅ Migrated ChatFilePanel.vue to EmptyState component (compact inline state, ~4 lines saved)
- ✅ Migrated PopoutChromiumBrowser.vue to EmptyState component (2 empty states with action button, ~19 lines saved)

**📊 Batch 12 Deep Dive Assessment** (January 2025):
After exhaustive codebase analysis, the following findings guide our strategy:

**EmptyState Migrations**: ✅ **Near Complete**
- 33 components successfully migrated (~579 lines saved)
- Remaining candidates offer minimal benefit (1-3 lines each)
- Most contextual empty states already use compact inline patterns

**BaseModal Migrations**: ⚠️ **Not Recommended**
Evaluated 8 modal/dialog candidates:
- **ElevationDialog.vue** (604 lines): Security-critical, custom red gradient, password input, risk badges - *intentionally distinctive*
- **AdvancedStepConfirmationModal.vue** (1,670 lines): Workflow management, nested modals, step editing - *highly specialized*
- **KnowledgePersistenceDialog.vue** (910 lines): Complex configuration with multiple tabs/sections
- **VectorizationProgressModal.vue** (561 lines): Real-time progress tracking with logs
- **TerminalModals.vue** (1,057 lines): Multiple terminal-specific modals in one file
- **DeploymentProgressModal.vue**: Progress modal with log streaming
- **CommandPermissionDialog.vue**: Permission workflow with approval logic
- **AddHostModal.vue**: Infrastructure configuration with validation

**Why BaseModal isn't suitable for these**:
1. All have 500-1,600+ lines with extensive custom styling
2. Highly specialized business logic (security, workflows, real-time updates)
3. Custom layouts that don't fit BaseModal's header/content/actions pattern
4. Many have nested modals, tabs, or complex form validation
5. Migration would require massive refactoring with high risk, minimal benefit

**Other Reusability Patterns**: ⚠️ **Mostly Contextual**
- Loading spinners: Inline button states, not standalone components
- Status indicators: Already using ServiceStatusIndicator component
- Form patterns: Vary significantly by use case
- Error messages: Context-dependent styling and placement

**Revised Goal Assessment**:
The initial ~5,600 line estimate was optimistic. Actual duplicate code is closer to ~1,500-2,000 lines across:
- Empty states: ✅ **579 lines saved** (most complete)
- Modals: ❌ **Not viable** (too specialized)
- Other patterns: 🔄 **Future opportunity** (requires new components)

**Recommended Next Steps**:
1. ✅ Mark EmptyState migrations as substantially complete
2. 📋 Focus on creating NEW reusable patterns for remaining duplicates:
   - LoadingState component for full-page loading (not button spinners)
   - FormGroup component for consistent form field layouts
   - ActionButton component for primary/secondary button patterns
   - NotificationToast component for user feedback
3. 📋 Re-estimate target based on actual patterns found (~1,500-2,000 lines realistic)

**📊 Batch 13 Implementation Findings** (January 2025):
Attempted to implement batch 12 recommendations - key learnings:

**UnifiedLoadingView Analysis**: ⚠️ **Not a Drop-In Replacement**
- UnifiedLoadingView already exists and is well-designed
- Only 4 components currently use it (PopoutChromiumBrowser, NoVNCViewer, DesktopInterface, ChatInterface)
- Uses `useUnifiedLoading` composable for centralized loading state management
- **Why not widely adopted**: Requires components to use the unified loading system
  - Example: InfrastructureManager uses `isLoading` from domain-specific `useInfrastructure` composable
  - Migrating would require refactoring entire composable to use unified loading system
  - Most components have domain-specific loading state tied to their data fetching
- **Conclusion**: UnifiedLoadingView is an architectural pattern, not a drop-in component
  - Can't simply replace custom loading UI without changing state management architecture
  - Migration would be highly invasive with uncertain benefit
  - Current approach (domain-specific loading states) is actually more appropriate

**Form Pattern Analysis**: ⚠️ **High Variation**
- 20+ components have form inputs (label + input/textarea/select patterns)
- Forms are highly domain-specific:
  - Infrastructure forms: Host configuration, deployment settings
  - Knowledge forms: Category management, file upload
  - Settings forms: Cache config, NPU workers, secrets
  - Security forms: Permission dialogs, elevation requests
- **Why FormGroup isn't viable**: Each form has unique:
  - Validation logic (inline, server-side, real-time)
  - Layout requirements (horizontal, vertical, grid, inline)
  - Field types and combinations
  - Error display patterns
  - Conditional field visibility
- **Conclusion**: Forms are not good candidates for generic components
  - Too much context-specific logic and styling
  - Forcing generic patterns would reduce flexibility

**Revised Understanding**:
The codebase is actually well-architected. Most "duplicate" code is contextual variation, not true duplication:
- Loading states: Tied to domain-specific data fetching patterns
- Forms: Varied by business requirements
- Modals: Specialized for their use cases
- Empty states: ✅ Successfully abstracted (33 migrations, ~579 lines)

**What We Learned**:
- Not all similar-looking code is duplicate code
- Architecture matters - can't force generic solutions onto domain-specific patterns
- EmptyState worked because it's truly presentational with no logic
- UnifiedLoadingView exists but is an architectural choice, not a migration target
- Forms and modals are inherently contextual

**Actual Remaining Opportunity**: ~200-400 lines
- Focus on truly generic presentational components
- Don't force architectural changes for marginal savings
- Current codebase structure is appropriate for the problem domain

**📊 Batch 14 Utility Consolidation** (January 2025):
Final sweep for duplicate utility functions - concrete savings found:

**DeploymentProgressModal Format Functions**: ✅ **Migrated**
- **Found**: 2 duplicate format functions (formatTimestamp, formatLogTime) - 20 lines
- **Action**: Replaced with shared formatHelpers utilities (formatDateTime, formatTime)
- **After**: 2-line wrappers using shared utilities + 1 import
- **Lines Saved**: ~18 lines
- **Location**: `autobot-user-frontend/src/components/infrastructure/DeploymentProgressModal.vue`

**Other Duration Formatting**: ⚠️ **Not Duplicate**
- **AsyncComponentWrapper.vue**: `formatLoadingTime()` - unique to loading metrics (ms/s display)
- **RumDashboard.vue**: `formatUptime()` - unique to uptime display (h/m/s display)
- **Conclusion**: These are contextual variations, not true duplicates
- Per batch 13 principles: Don't create utilities for single-use patterns

**Batch 14 Summary**:
- ✅ 18 lines saved (DeploymentProgressModal migration)
- ✅ formatHelpers.ts continues to prevent future duplication
- ✅ Validated batch 13 principle: Only consolidate truly duplicate patterns

**📊 Batch 15 StatusBadge Adoptions** (January 2025):
Migrated 3 components to use existing StatusBadge component:

**1. PopoutChromiumBrowser.vue** ✅
- **Before**: Inline "Connected" badge with custom Tailwind classes
- **After**: `<StatusBadge variant="success" size="small">Connected</StatusBadge>`
- **Lines Saved**: ~1 line (improved consistency)
- **Location**: `autobot-user-frontend/src/components/PopoutChromiumBrowser.vue:205`

**2. HostCard.vue** ✅
- **Before**: Inline status badge with 4 conditional color classes (active/pending/error/deploying)
- **After**: `<StatusBadge :variant="statusVariant" size="small">{{ host.status }}</StatusBadge>` + computed variant mapping
- **Lines Saved**: ~11 lines (12 lines inline badge → 1 StatusBadge component)
- **Location**: `autobot-user-frontend/src/components/infrastructure/HostCard.vue:18-20`

**3. ChatFilePanel.vue** ✅
- **Before**: Inline "AI Generated" badge with purple styling
- **After**: `<StatusBadge variant="primary" size="small">AI Generated</StatusBadge>`
- **Lines Saved**: ~2 lines
- **Location**: `autobot-user-frontend/src/components/chat/ChatFilePanel.vue:123-130`

**Batch 15 Summary**:
- ✅ 3 components migrated to StatusBadge
- ✅ ~14 lines saved
- ✅ Increased StatusBadge usage from 2 to 5 components (150% adoption increase)
- ✅ Demonstrates value of leveraging existing components

**📊 Batch 16 StatusBadge Enforcement** (January 2025):
Continued migration to StatusBadge component with more complex components:

**1. RedisServiceControl.vue** ✅
- **Before**: 3 status mapping functions (getStatusBadgeClass, getHealthIndicatorClass, getHealthCheckBadgeClass) with switch statements
- **After**: 3 computed variant mappings (statusVariant, healthVariant, getHealthCheckVariant) + StatusBadge components
- **Functions Removed**:
  - `getStatusBadgeClass()` (~14 lines)
  - `getHealthIndicatorClass()` (~14 lines)
  - `getHealthCheckBadgeClass()` (~14 lines)
- **Lines Saved**: ~42 lines (3 functions removed, replaced with 3 compact variant maps)
- **Location**: `autobot-user-frontend/src/components/services/RedisServiceControl.vue`
- **Note**: Kept `getStatusDotClass()` and `getHealthCheckCardClass()` - still needed for dot animation and card styling

**2. ResearchBrowser.vue** ✅
- **Before**: 2 inline status class mappings (statusClass computed, getResultStatusClass function)
- **After**: 2 variant mapping functions (statusVariant computed, getResultStatusVariant function) + StatusBadge components
- **Functions Replaced**:
  - `statusClass` computed property (9 lines) → `statusVariant` computed (7 lines)
  - `getResultStatusClass` function (9 lines) → `getResultStatusVariant` function (7 lines)
- **CSS Removed**: `.status-badge` class (3 lines)
- **Lines Saved**: ~7 lines
- **Location**: `autobot-user-frontend/src/components/ResearchBrowser.vue`

**Batch 16 Summary**:
- ✅ 2 components migrated to StatusBadge
- ✅ ~49 lines saved
- ✅ Increased StatusBadge usage from 5 to 7 components (40% increase)
- ✅ Demonstrates value even in complex components with multiple status types

**📊 Batch 17 StatusBadge Enforcement** (January 2025):
Migrated MonitoringDashboard.vue with 2 badge patterns:

**MonitoringDashboard.vue** ✅
- **Before**: 2 badge CSS classes with variant styles (priority-badge, severity-badge)
- **After**: 2 variant mapping functions (getPriorityVariant, getSeverityVariant) + StatusBadge components
- **Badges Removed**:
  - `.priority-badge` with 3 variants (high/medium/low) - 9 lines CSS
  - `.severity-badge` with 2 variants (critical/warning) - 6 lines CSS
- **Functions Added**:
  - `getPriorityVariant()` - maps high/medium/low to danger/warning/info
  - `getSeverityVariant()` - maps critical/warning to danger/warning
- **Template Updates**:
  - Line 286: Replaced `<span :class="['priority-badge', rec.priority]">` with StatusBadge
  - Line 321: Replaced `<span :class="['severity-badge', alert.severity]">` with StatusBadge
- **Lines Saved**: ~15 lines (CSS removed)
- **Location**: `autobot-user-frontend/src/components/monitoring/MonitoringDashboard.vue`

**Batch 17 Summary**:
- ✅ 1 component migrated (2 badge patterns)
- ✅ ~15 lines saved
- ✅ Increased StatusBadge usage from 7 to 9 instances (29% increase)
- ✅ Demonstrates CSS consolidation benefit

**📊 Batch 18 StatusBadge Enforcement** (January 2025):
Migrated 4 components with 5 badge patterns total:

**1. SecretsManager.vue** ✅
- **Before**: 2 badge patterns with scope and type variants
- **After**: `getScopeVariant()` and `getTypeVariant()` mapping functions + StatusBadge components
- **Badges Removed**:
  - `.badge` base class + `.badge-chat`, `.badge-general` scope variants - 8 lines CSS
  - `.badge-ssh_key`, `.badge-password`, `.badge-api_key` type variants - 9 lines CSS
- **Template Updates**: Lines 87-90 replaced inline badges with StatusBadge
- **Lines Saved**: ~17 lines
- **Location**: `autobot-user-frontend/src/components/SecretsManager.vue`

**2. CommandPermissionDialog.vue** ✅
- **Before**: Risk level badge with 4 variants (low/medium/high/critical)
- **After**: `getRiskVariant()` mapping function + StatusBadge component
- **Badges Removed**: `.risk-badge` with 4 variants - 28 lines CSS
- **Function Added**: `getRiskVariant()` maps LOW/MEDIUM/HIGH/CRITICAL to success/warning/danger/danger
- **Template Updates**: Line 28 replaced risk-badge with StatusBadge
- **Lines Saved**: ~28 lines
- **Location**: `autobot-user-frontend/src/components/CommandPermissionDialog.vue`

**3. ElevationDialog.vue** ✅
- **Before**: Risk level badge with 4 variants (identical pattern to CommandPermissionDialog)
- **After**: `getRiskVariant()` mapping function + StatusBadge component
- **Badges Removed**: `.risk-badge` with 4 variants - 28 lines CSS
- **Function Added**: Same getRiskVariant() pattern for consistency
- **Template Updates**: Line 28 replaced risk-badge with StatusBadge
- **Lines Saved**: ~28 lines
- **Location**: `autobot-user-frontend/src/components/ElevationDialog.vue`

**4. KnowledgeStats.vue** ✅
- **Before**: Status badge with 2 variants (online/offline)
- **After**: `getStatusVariant()` TypeScript function + StatusBadge component
- **Badges Removed**: `.status-badge` with online/offline variants - 17 lines CSS
- **Function Added**: `getStatusVariant()` maps online/offline/unknown to success/danger/secondary
- **Template Updates**: Line 68 replaced status-badge with StatusBadge
- **Lines Saved**: ~17 lines
- **Location**: `autobot-user-frontend/src/components/knowledge/KnowledgeStats.vue`

**Batch 18 Summary**:
- ✅ 4 components migrated (5 badge patterns total)
- ✅ ~90 lines saved (CSS + template simplification)
- ✅ Increased StatusBadge usage from 9 to 14 instances (56% increase)
- ✅ Demonstrates pattern consistency: Both CommandPermissionDialog and ElevationDialog use identical risk badge mapping
- ✅ Covers diverse contexts: Secrets management, command permissions, elevation dialogs, knowledge stats

**📊 Batch 19 StatusBadge Final Sweep** (January 2025):
Final StatusBadge migration completing the enforcement wave:

**NPUWorkersSettings.vue** ✅
- **Before**: Status badge with 4 variants (online/offline/busy/error)
- **After**: `getStatusVariant()` TypeScript function + StatusBadge component
- **Badges Removed**: `.status-badge` with 4 variants - 29 lines CSS
- **Function Added**: `getStatusVariant()` maps online/offline/busy/error to success/secondary/warning/danger
- **Template Updates**: Line 116 replaced status-badge with StatusBadge (retained status-dot for visual indicator)
- **Lines Saved**: ~29 lines
- **Location**: `autobot-user-frontend/src/components/settings/NPUWorkersSettings.vue`

**Batch 19 Summary**:
- ✅ 1 component migrated (final candidate)
- ✅ ~29 lines saved
- ✅ Increased StatusBadge usage from 14 to 15 instances (7% increase)
- ✅ **StatusBadge enforcement substantially complete** - 650% usage increase from baseline (2 → 15 instances)

---

### **Batch 20: BaseButton Migration (First Wave)** ✅ Completed (Commit: abd34a6)

**Goal**: Begin BaseButton adoption to replace duplicate inline button patterns across components.

**Strategic Context**: Following StatusBadge enforcement completion (batches 15-19), shifted focus to button component consolidation. Discovered TWO unused button components:
- **BaseButton.vue** - 11 variants (primary/secondary/success/danger/warning/info/light/dark/outline/ghost/link), 5 sizes
- **TouchFriendlyButton.vue** - 5 variants with touch optimization features (ripple, haptic feedback, 44px min targets)

**Decision**: Started with BaseButton due to more comprehensive variant support (11 vs 5), deferring TouchFriendlyButton overlap resolution for later.

#### **Components Migrated**:

**1. ErrorBoundary.vue** - Error recovery component
- **Buttons**: 3 (primary: retry, secondary: reload, ghost: toggle details)
- **Lines Saved**: ~47 lines of duplicate button CSS
- **Technical Notes**:
  - Preserved conditional text rendering (`retrying ? 'Retrying...' : 'Try Again'`)
  - Maintained disabled state binding (`:disabled="retrying"`)
  - All click handlers and component logic unchanged
- **Location**: `autobot-user-frontend/src/components/ErrorBoundary.vue`
- **Commit**: abd34a6 (lines 54, 25-43, 274-320 removed)

**2. async/AsyncErrorFallback.vue** - Async component error fallback
- **Buttons**: 4 (primary: retry, secondary: reload, outline: go home, ghost: toggle)
- **Lines Saved**: ~66 lines of duplicate button CSS (kept .fa-spin animation)
- **Technical Notes**:
  - Preserved exponential backoff retry logic
  - Maintained icon animations (`:class="{ 'fa-spin': retrying }"`)
  - Preserved retry count display (`Retry (${retryCount}/${maxRetries})`)
  - Kept service worker cache clearing on reload
- **Location**: `autobot-user-frontend/src/components/async/AsyncErrorFallback.vue`
- **Commit**: abd34a6 (lines 65-67, 27-57, 340-405 removed)

**3. PhaseStatusIndicator.vue** - Project phase status display
- **Buttons**: 3 (primary: refresh, secondary: validate, info: report)
- **Lines Saved**: ~44 lines of duplicate button CSS
- **Technical Notes**:
  - Preserved loading state animations (fa-sync spinning)
  - Maintained disabled states during operations
  - Options API component (required components registration)
- **Location**: `autobot-user-frontend/src/components/PhaseStatusIndicator.vue`
- **Commit**: abd34a6 (lines 124-130, 88-99, 557-600 removed)

**Batch 20 Summary**:
- ✅ 3 components migrated (error recovery, async loading, status display)
- ✅ 10 button elements replaced with BaseButton
- ✅ ~157 lines of duplicate CSS removed (47 + 66 + 44)
- ✅ BaseButton usage increased from 0 to 3 components (new baseline)
- ✅ 5 variants validated: primary, secondary, ghost, outline, info

**Migration Pattern Established**:
```vue
<!-- BEFORE: Inline button with duplicate CSS -->
<button @click="retry" class="btn btn-primary" :disabled="retrying">
  {{ retrying ? 'Retrying...' : 'Try Again' }}
</button>

<style scoped>
.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  /* ...47 more lines... */
}
</style>

<!-- AFTER: BaseButton component -->
<BaseButton variant="primary" @click="retry" :disabled="retrying">
  {{ retrying ? 'Retrying...' : 'Try Again' }}
</BaseButton>
<!-- No duplicate CSS needed -->
```

**Technical Approach**:
- Used BaseButton's 11-variant system for comprehensive coverage
- Preserved all functionality: disabled states, click handlers, conditional content
- Maintained icon animations and loading states
- Zero behavior changes - pure refactor for code reuse
- Both Composition API and Options API components supported

**Next Steps**:
- ~~Continue BaseButton migrations~~ ✅ **IN PROGRESS** - Batch 21 complete (5 total components now using BaseButton)
- ~~Address TouchFriendlyButton vs BaseButton overlap~~ ✅ **RESOLVED** - Touch features integrated into BaseButton
- Document migration guide with before/after examples

---

### **Batch 21: BaseButton Migration (Second Wave)** ✅ Completed (Commit: bc2d72f)

**Goal**: Continue BaseButton adoption across workflow management and knowledge integration components.

#### **Components Migrated**:

**1. WorkflowApproval.vue** - Workflow approval and management interface
- **Buttons**: 4 (success: approve step, danger: deny step + cancel workflow, secondary: refresh)
- **Lines Saved**: ~44 lines of duplicate button CSS
- **Technical Notes**:
  - Workflow approval actions with conditional rendering
  - Preserved disabled states during approval operations
  - Composition API with TypeScript (<script setup lang="ts">)
  - All click handlers and conditional visibility maintained
- **Location**: `autobot-user-frontend/src/components/WorkflowApproval.vue`
- **Commit**: bc2d72f (lines 200, 143-158, 173-188, 677-720 removed)

**2. ManPageManager.vue** - Man page integration management
- **Buttons**: 7 (3× outline sm: refresh/hide, primary: initialize/search, success: integrate, info: test)
- **Lines Saved**: ~43 lines of duplicate button CSS
- **Technical Notes**:
  - **Leveraged BaseButton's built-in `:loading` prop** - Simplified loading state handling
  - Removed manual spinner conditionals (`v-if="!loading"` / `v-else` icon logic)
  - Options API with setup() + components registration
  - Multiple refresh buttons, integration actions, search functionality
  - Preserved all icon animations and disabled states
- **Location**: `autobot-user-frontend/src/components/ManPageManager.vue`
- **Commit**: bc2d72f (lines 323-329, multiple button replacements, 936-978 removed)

**Batch 21 Summary**:
- ✅ 2 components migrated (workflow management, knowledge integration)
- ✅ 11 button elements replaced with BaseButton
- ✅ ~87 lines of duplicate CSS removed (44 + 43)
- ✅ BaseButton usage increased from 3 to 5 components (67% increase)
- ✅ 6 variants validated: primary, secondary, success, danger, info, outline
- ✅ 2 size variants validated: sm, md

**Technical Highlight - Loading State Simplification**:
```vue
<!-- BEFORE: Manual loading spinner logic -->
<button>
  <i class="fas fa-rocket" v-if="!loading?.initialize"></i>
  <i class="fas fa-spinner fa-spin" v-else></i>
  Initialize Machine Knowledge
</button>

<!-- AFTER: BaseButton handles loading automatically -->
<BaseButton :loading="loading?.initialize">
  <i class="fas fa-rocket"></i>
  Initialize Machine Knowledge
</BaseButton>
<!-- BaseButton shows spinner automatically when loading=true -->
```

**Cumulative BaseButton Progress**:
- Batch 20: 3 components, ~157 lines, 10 buttons
- Batch 21: 2 components, ~87 lines, 11 buttons
- **Combined Total**: 5 components, ~244 lines saved, 21 buttons consolidated

---

### **BaseButton Touch Integration** ✅ Completed (Commit: 2c01923)

**Goal**: Resolve TouchFriendlyButton vs BaseButton overlap by extending BaseButton with touch optimization features.

**Strategic Decision**: Extended BaseButton with optional touch features rather than maintaining two separate button components. This approach provides:
- ✅ Single unified button component for all use cases
- ✅ Progressive enhancement - desktop apps use lightweight BaseButton, mobile apps enable touch features
- ✅ Maintains all 11 BaseButton variants + touch capabilities
- ✅ Backward compatible with batch 20 migrations (touchOptimized defaults to false)

#### **Touch Features Added**:

**1. Optional Touch Props**:
```typescript
interface Props {
  // ... existing props ...
  touchOptimized?: boolean      // Enable all touch features (default: false)
  touchFeedback?: boolean        // Visual ripple effect (default: true)
  hapticFeedback?: boolean       // Device vibration (default: true)
}
```

**2. Touch Event Handlers**:
- `@touchstart` - Triggers ripple effect and haptic feedback
- `@touchend` - Resets pressed state
- `@touchcancel` - Handles touch cancellation
- Emits: `touchStart`, `touchEnd` events for parent components

**3. Ripple Effect System**:
- Dynamic ripple creation at touch point coordinates
- 600ms animation with scale and opacity transition
- Automatic cleanup after animation completion
- Respects `touchFeedback` prop (can be disabled)

**4. Haptic Feedback**:
- 10ms vibration on touch start using `navigator.vibrate()`
- Gracefully handles devices without vibration support
- Respects `hapticFeedback` prop (can be disabled)

**5. Touch-Optimized Styling**:
- **44px minimum touch targets** (iOS/Android accessibility standard)
- `-webkit-tap-highlight-color: transparent` (removes default mobile tap highlight)
- `touch-action: manipulation` (improves touch responsiveness)
- `overflow: hidden` (contains ripple effects)
- Touch-specific pressed state with `scale(0.95)` transform
- Media query `@media (hover: none) and (pointer: coarse)` disables desktop hover on touch devices

#### **Usage Examples**:

**Desktop Button (default - no touch features):**
```vue
<BaseButton variant="primary" @click="handleAction">
  Click Me
</BaseButton>
<!-- Lightweight, desktop-optimized -->
```

**Mobile Touch-Optimized Button:**
```vue
<BaseButton
  variant="primary"
  touchOptimized
  @click="handleAction"
  @touchStart="handleTouchStart"
>
  Tap Me
</BaseButton>
<!-- Includes ripple effects, haptic feedback, 44px touch targets -->
```

**Customized Touch Features:**
```vue
<BaseButton
  variant="primary"
  touchOptimized
  :touchFeedback="false"
  :hapticFeedback="true"
>
  Vibrate Only
</BaseButton>
<!-- Haptic feedback enabled, visual ripple disabled -->
```

#### **Technical Implementation**:

**Touch State Management**:
```typescript
const ripple = ref<HTMLElement>()
const isPressed = ref(false)

const handleTouchStart = (event: TouchEvent) => {
  if (disabled || loading || !touchOptimized) return
  isPressed.value = true
  if (touchFeedback) createRipple(event)
  if (hapticFeedback && 'vibrate' in navigator) navigator.vibrate(10)
  emit('touchStart', event)
}
```

**Ripple Effect Calculation**:
```typescript
const createRipple = (event: TouchEvent) => {
  const button = ripple.value.parentElement!
  const rect = button.getBoundingClientRect()
  const touch = event.touches[0]

  const x = touch.clientX - rect.left
  const y = touch.clientY - rect.top

  const rippleElement = document.createElement('div')
  rippleElement.className = 'ripple-effect'
  rippleElement.style.left = `${x - 25}px`
  rippleElement.style.top = `${y - 25}px`

  ripple.value.appendChild(rippleElement)
  setTimeout(() => ripple.value.removeChild(rippleElement), 600)
}
```

**CSS Enhancements**:
```css
.btn-touch-optimized {
  min-height: 44px;
  min-width: 44px;
  overflow: hidden;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}

.ripple-effect {
  animation: ripple-animation 0.6s ease-out;
  /* ... ripple styles ... */
}
```

#### **Component Consolidation Result**:

**Before**: Two separate components
- BaseButton.vue - 11 variants, no touch support
- TouchFriendlyButton.vue - 5 variants, touch optimized (0 usage)

**After**: Single unified component
- BaseButton.vue - 11 variants + optional touch features
- TouchFriendlyButton.vue - Can be deprecated or converted to wrapper
- ✅ Backward compatible - existing batch 20 migrations unchanged
- ✅ Zero breaking changes - touchOptimized defaults to false
- ✅ Future-ready - all buttons can enable touch features as needed

#### **Migration Impact**:

- **Batch 20 components unaffected** - touchOptimized=false by default
- **New mobile components** - Can use touchOptimized=true for enhanced UX
- **Responsive components** - Can conditionally enable based on device detection
- **No duplicate code** - Single button component serves both desktop and mobile

**Files Modified**:
- `autobot-user-frontend/src/components/base/BaseButton.vue` (extended with touch features)

**TouchFriendlyButton.vue Status**: Recommend deprecation or conversion to lightweight wrapper around `<BaseButton touchOptimized>` for backward compatibility.

---

### **Batch 22 - Dialog Buttons Migration** ✅ Completed

**Goal**: Migrate dialog components with permission/elevation workflows to BaseButton.

**Components Migrated**: 2 components, 7 buttons, ~187 lines saved

#### **1. CommandPermissionDialog.vue** (5 buttons, ~145 lines saved)

**Purpose**: Command execution permission dialog with approval/denial/comment actions.

**Buttons Migrated**:
- Comment Actions:
  - `btn btn-secondary` → `<BaseButton variant="secondary">` (Cancel comment)
  - `btn btn-primary` → `<BaseButton variant="primary" :loading="isProcessing">` (Send Feedback)
- Footer Actions:
  - `btn btn-cancel` → `<BaseButton variant="secondary">` (Deny)
  - `btn btn-comment` → `<BaseButton variant="warning">` (Comment)
  - `btn btn-allow` → `<BaseButton variant="success" :loading="isProcessing">` (Allow)

**Loading State Benefit**:
```vue
<!-- BEFORE: Manual loading spinner logic -->
<button class="btn btn-allow" :class="{ processing: isProcessing }">
  <i v-if="isProcessing" class="fas fa-spinner fa-spin"></i>
  <i v-else class="fas fa-check"></i>
  {{ isProcessing ? 'Executing...' : 'Allow' }}
</button>

<!-- AFTER: BaseButton handles loading automatically -->
<BaseButton variant="success" :loading="isProcessing">
  <i class="fas fa-check"></i>
  {{ isProcessing ? 'Executing...' : 'Allow' }}
</BaseButton>
```

**CSS Removed**: ~145 lines (.btn, .btn:disabled, .btn-cancel, .btn-allow, .btn-comment, .btn-secondary, .btn-primary styles)

---

#### **2. ElevationDialog.vue** (2 buttons, ~42 lines saved)

**Purpose**: Administrator privilege elevation dialog with password authentication.

**Buttons Migrated**:
- `btn btn-cancel` → `<BaseButton variant="secondary">` (Cancel)
- `btn btn-approve` → `<BaseButton variant="danger" :loading="isProcessing">` (Authorize)

**Variant Mapping**:
- Custom `btn-approve` with red background (#dc2626) → `variant="danger"` (perfect color match)

**CSS Removed**: ~42 lines (.btn, .btn:disabled, .btn-cancel, .btn-approve styles)

---

**Batch 22 Summary**:
- Components: 2 (CommandPermissionDialog, ElevationDialog)
- Buttons: 7 consolidated
- Lines: ~187 saved
- Variants: 5 (secondary, primary, warning, success, danger)
- **Combined Total**: 7 components, ~431 lines saved, 28 buttons consolidated

---

### **Batch 23 - Browser & Knowledge Buttons Migration** ✅ Completed

**Goal**: Migrate browser automation and knowledge management components to BaseButton.

**Components Migrated**: 2 components, 12 buttons, ~96 lines saved

#### **1. PopoutChromiumBrowser.vue** (5 buttons, ~49 lines saved)

**Purpose**: Chromium browser automation interface with Playwright integration.

**Buttons Migrated**:
- Error Overlay:
  - `btn btn-primary btn-sm` → `<BaseButton variant="primary" size="sm" :loading="isInitializingBrowser">` (Retry Connection)
- Empty State:
  - `btn btn-primary` → `<BaseButton variant="primary" :loading="isInitializingBrowser">` (Launch Browser Session)
- Interaction Overlay:
  - `btn btn-primary` → `<BaseButton variant="primary">` (Wait & Monitor)
  - `btn btn-secondary` → `<BaseButton variant="secondary">` (Take Control)
  - `btn btn-outline` → `<BaseButton variant="outline">` (Dismiss)

**CSS Removed**: ~49 lines (.btn, .btn-sm, .btn-primary, .btn-secondary, .btn-outline styles)

---

#### **2. SystemKnowledgeManager.vue** (7 buttons, ~47 lines saved)

**Purpose**: System knowledge base management with vector operations.

**Buttons Migrated**:
- Primary Actions (vector operations):
  - `btn btn-primary btn-highlight` → `<BaseButton variant="primary" :loading="isVectorizing" class="btn-highlight">` (Generate Vector Embeddings)
  - `btn btn-primary` → `<BaseButton variant="primary" :loading="isInitializing">` (Initialize Machine Knowledge)
  - `btn btn-primary` → `<BaseButton variant="primary" :loading="isReindexing">` (Reindex Documents)
- Secondary Actions (man pages):
  - `btn btn-secondary` → `<BaseButton variant="secondary" :loading="isRefreshing">` (Refresh Man Pages)
  - `btn btn-secondary` → `<BaseButton variant="secondary" :loading="isPopulating">` (Populate Common Commands)
  - `btn btn-secondary` → `<BaseButton variant="secondary" :loading="isDocPopulating">` (Index AutoBot Docs)
- Utility:
  - `btn btn-outline` → `<BaseButton variant="outline">` (Refresh Stats)

**Custom Styling Preserved**:
- Kept `.btn-highlight` class for gradient styling on vector embeddings button
- Applied as additional class: `<BaseButton class="btn-highlight">`

**CSS Removed**: ~47 lines (.btn, .btn:disabled, .btn-primary, .btn-secondary, .btn-outline styles)

---

**Batch 23 Summary**:
- Components: 2 (PopoutChromiumBrowser, SystemKnowledgeManager)
- Buttons: 12 consolidated
- Lines: ~96 saved
- Variants: 4 (primary, secondary, outline, sm size)
- **Combined Total**: 9 components, ~527 lines saved, 40 buttons consolidated

---

### **Batch 24 - Research Browser Migration** ✅ Completed

**Goal**: Migrate ResearchBrowser component with comprehensive browser automation controls to BaseButton.

**Component Migrated**: 1 component, 16 buttons, ~39 lines saved

#### **ResearchBrowser.vue** (16 buttons, ~39 lines saved)

**Purpose**: AI research browser automation with Playwright integration and agent control.

**Buttons Migrated by Category**:

**Header Controls:**
- `btn btn-secondary btn-sm` → `<BaseButton variant="secondary" size="sm" :loading="isRefreshingStatus">` (Refresh status)
- `btn btn-outline btn-xs` → `<BaseButton variant="outline" size="xs">` (Copy URL)

**Interaction Alert:**
- `btn btn-primary btn-sm` → `<BaseButton variant="primary" size="sm" :loading="isWaitingForUser">` (Wait)
- `btn btn-secondary btn-sm` → `<BaseButton variant="secondary" size="sm">` (Open Browser)

**Result Actions:**
- `btn btn-warning btn-sm` → `<BaseButton variant="warning" size="sm">` (Open Browser for Result)

**Session Controls (4 buttons):**
- `btn btn-outline btn-sm` → `<BaseButton variant="outline" size="sm" :loading="isPerformingAction">` (Extract Content, Save MHTML)
- `btn btn-outline btn-sm` → `<BaseButton variant="outline" size="sm" :loading="isNavigating">` (Navigate)
- `btn btn-danger btn-sm` → `<BaseButton variant="danger" size="sm" :loading="isClosingSession">` (Close Session)

**Navigation Input:**
- `btn btn-primary btn-sm` → `<BaseButton variant="primary" size="sm" :disabled="!navigationUrl" :loading="isNavigating">` (Go)
- `btn btn-secondary btn-sm` → `<BaseButton variant="secondary" size="sm">` (Cancel)

**Browser Controls:**
- `btn btn-primary btn-xs` → `<BaseButton variant="primary" size="xs" :loading="isNavigatingBrowser">` (Navigate browser)
- `btn btn-warning btn-xs` → `<BaseButton variant="warning" size="xs" :loading="isPausingAgent">` (Take Control)
- `btn btn-success btn-xs` → `<BaseButton variant="success" size="xs" :loading="isResumingAgent">` (Resume Agent)
- `btn btn-outline btn-xs` → `<BaseButton variant="outline" size="xs">` (Toggle Browser View)
- `btn btn-primary btn-xs` → `<BaseButton variant="primary" size="xs">` (Pop Out)

**Key Features Demonstrated**:
- ✅ Consistent :loading prop across all async operations
- ✅ Both sm and xs size variants for different contexts
- ✅ 7 different variants used: primary, secondary, outline, warning, danger, success
- ✅ Conditional :disabled with :loading (navigation button)

**CSS Removed**: ~39 lines (Tailwind @apply directives: .btn, .btn:disabled, .btn-primary, .btn-secondary, .btn-outline, .btn-warning, .btn-danger, .btn-success, .btn-sm, .btn-xs)

---

**Batch 24 Summary**:
- Component: 1 (ResearchBrowser)
- Buttons: 16 consolidated
- Lines: ~39 saved
- Variants: 7 (primary, secondary, outline, warning, danger, success, + sm/xs sizes)
- **Combined Total**: 10 components, ~566 lines saved, 56 buttons consolidated

---

### **Batch 25 - Terminal & Chat Components** ✅ Completed

**Goal**: Migrate terminal modal dialogs and chat sidebar to BaseButton for consistent UI patterns.

**Components Migrated**: 2 components, 19 buttons, ~114 lines saved

#### **TerminalModals.vue** (6 buttons, ~91 lines saved)

**Purpose**: Terminal confirmation modals for reconnect, command execution, emergency kill, and workflow actions.

**Buttons Migrated by Modal**:

**Reconnect Modal:**
- `btn btn-secondary` → `<BaseButton variant="secondary" :disabled="isReconnecting">` (Cancel)
- `btn btn-primary` → `<BaseButton variant="primary" :loading="isReconnecting">` (Reconnect)

**Command Confirmation Modal:**
- `btn btn-danger` → `<BaseButton variant="danger" :loading="isExecutingCommand">` (Execute Command)
- `btn btn-secondary` → `<BaseButton variant="secondary" :disabled="isExecutingCommand">` (Cancel)

**Emergency Kill Modal:**
- `btn btn-danger` → `<BaseButton variant="danger" :loading="isKillingProcesses">` (Kill All Processes)
- `btn btn-secondary` → `<BaseButton variant="secondary" :disabled="isKillingProcesses">` (Cancel)

**Key Patterns**:
- ✅ Consistent :loading prop for async operations
- ✅ Manual spinner removal (BaseButton handles internally)
- ✅ Proper :disabled usage during loading states
- ⚠️ **Advanced Pattern**: Workflow buttons use conditional loading: `:loading="isProcessingWorkflow && lastWorkflowAction === 'execute'"` to isolate loading state per action

**CSS Removed**: ~91 lines (removed .btn, .btn-primary, .btn-secondary, .btn-danger, .btn-success, .btn-warning, .loading-spinner, @keyframes spin)

#### **ChatSidebar.vue** (13 buttons, ~23 lines saved)

**Purpose**: Chat session management, multi-select deletion, system control, and display settings.

**Buttons Migrated by Section**:

**Sidebar Toggle:**
- Custom toggle → `<BaseButton variant="ghost" class="p-3">` (Collapse/Expand)

**Selection Mode (2 buttons):**
- Selection controls → `<BaseButton variant="ghost" size="xs">` (Select, Cancel)

**Chat History Actions (2 buttons):**
- History item controls → `<BaseButton variant="ghost" size="xs" class="text-blueGray-400 p-1">` (Edit)
- History item controls → `<BaseButton variant="ghost" size="xs" class="text-red-400 p-1">` (Delete)

**Chat Actions Grid (4 buttons):**
- `btn btn-primary text-xs` → `<BaseButton variant="primary" size="xs" class="py-1.5 px-2">` (New)
- `btn btn-secondary text-xs` → `<BaseButton variant="secondary" size="xs" :disabled="!store.currentSessionId">` (Reset)
- `btn btn-danger text-xs` → `<BaseButton variant="danger" size="xs" :disabled="!store.currentSessionId">` (Delete)
- `btn btn-outline text-xs` → `<BaseButton variant="outline" size="xs">` (Refresh)

**Selection Mode Actions:**
- `btn btn-danger w-full` → `<BaseButton variant="danger" size="xs" class="w-full" :disabled="selectedSessions.size === 0">` (Delete Selected)

**System Control:**
- `btn btn-primary w-full` → `<BaseButton variant="primary" size="xs" class="w-full" :loading="isSystemReloading">` (Reload System)

**Edit Modal (2 buttons):**
- Modal cancel → `<BaseButton variant="secondary">` (Cancel)
- Modal save → `<BaseButton variant="primary">` (Save)

**Key Features Demonstrated**:
- ✅ Ghost variant for subtle UI controls (toggle, selection, history actions)
- ✅ Size xs for compact grid layouts
- ✅ Loading state for system reload operation
- ✅ Conditional :disabled based on state (currentSessionId, selectedSessions)
- ✅ Custom classes preserved for specific styling needs

**CSS Removed**: ~23 lines (Tailwind @apply directives: .btn, .btn-primary, .btn-secondary, .btn-danger, .btn-outline, .btn:disabled)

---

**Batch 25 Summary**:
- Components: 2 (TerminalModals, ChatSidebar)
- Buttons: 19 consolidated (6 terminal + 13 chat)
- Lines: ~114 saved (~91 terminal + ~23 chat)
- Variants: 5 (primary, secondary, danger, outline, ghost)
- **Combined Total**: 12 components, ~680 lines saved, 75 buttons consolidated

---

### **Batch 26 - Knowledge, Services & Monitoring Components** ✅ Completed

**Goal**: Migrate knowledge management, service control, and monitoring components to BaseButton for consistent UI patterns.

**Components Migrated**: 3 components, 19 buttons, ~129 lines saved

#### **DocumentChangeFeed.vue** (8 buttons, ~75 lines saved)

**Purpose**: Knowledge base document change tracking with scanning and filtering capabilities.

**Buttons Migrated**:

**Main Controls:**
- `btn btn-primary btn-sm` → `<BaseButton variant="primary" size="sm" :loading="isScanning">` (Scan Now)
- `btn btn-secondary` → `<BaseButton variant="secondary">` (Scan for Changes - empty state)

**Action Buttons:**
- `btn btn-sm btn-outline-secondary` → `<BaseButton variant="outline" size="sm">` (Clear History)
- `btn btn-sm btn-outline-secondary` → `<BaseButton variant="outline" size="sm">` (Export Changes)

**Filter Buttons (4 buttons):**
- `filter-btn` + `.active` class → `<BaseButton :variant="activeFilter === 'all' ? 'primary' : 'outline'" size="sm">` (All)
- `filter-btn` + `.active` class → `<BaseButton :variant="activeFilter === 'added' ? 'primary' : 'outline'" size="sm">` (Added)
- `filter-btn` + `.active` class → `<BaseButton :variant="activeFilter === 'updated' ? 'primary' : 'outline'" size="sm">` (Updated)
- `filter-btn` + `.active` class → `<BaseButton :variant="activeFilter === 'removed' ? 'primary' : 'outline'" size="sm">` (Removed)

**Key Patterns**:
- ✅ Dynamic variant switching for active filters (primary vs outline)
- ✅ Loading state for scan operations
- ✅ Size sm for compact action buttons

**CSS Removed**: ~75 lines (.btn, .btn-primary, .btn-secondary, .btn-outline-secondary, .btn-sm, .filter-btn, .filter-btn:hover, .filter-btn.active)

#### **RedisServiceControl.vue** (6 buttons, ~30 lines saved)

**Purpose**: Redis service management with start, stop, restart controls and confirmation dialogs.

**Buttons Migrated**:

**Service Controls:**
- `btn btn-success` → `<BaseButton variant="success" :disabled="serviceStatus.status === 'running' || loading">` (Start)
- `btn btn-warning` → `<BaseButton variant="warning" :disabled="serviceStatus.status !== 'running' || loading">` (Restart)
- `btn btn-danger` → `<BaseButton variant="danger" :disabled="serviceStatus.status !== 'running' || loading">` (Stop)
- `btn btn-secondary` → `<BaseButton variant="secondary" :loading="loading">` (Refresh)

**Confirmation Dialog:**
- Cancel button → `<BaseButton variant="secondary">` (Cancel)
- Confirm button → `<BaseButton :variant="confirmDialog.type === 'danger' ? 'danger' : 'primary'">` (Confirm)

**Key Patterns**:
- ✅ Conditional :disabled based on service status
- ✅ Loading state for refresh operation
- ✅ Dynamic variant for confirm button based on action severity

**CSS Removed**: ~30 lines (.btn, .btn-success, .btn-warning, .btn-danger, .btn-secondary)

#### **MonitoringDashboard.vue** (5 buttons, ~24 lines saved)

**Purpose**: Phase 9 GPU/NPU monitoring dashboard with real-time performance tracking.

**Buttons Migrated**:

**Dashboard Controls:**
- Toggle monitoring → `<BaseButton :variant="monitoringActive ? 'danger' : 'success'" :disabled="loading">` (Start/Stop)
- Refresh button → `<BaseButton variant="secondary" :loading="loading">` (Refresh Dashboard)

**Alert & Recommendations:**
- Alert banner → `<BaseButton variant="outline" size="sm" class="btn-outline-light">` (View Details)
- Recommendations → `<BaseButton variant="outline" size="sm" class="btn-outline-primary">` (Refresh Recommendations)
- Modal close → `<BaseButton variant="ghost" size="xs" class="btn-close">` (Close Modal)

**Key Patterns**:
- ✅ Dynamic variant toggle (success ↔ danger) based on monitoring state
- ✅ Loading states for async operations
- ✅ Custom outline classes preserved for light backgrounds
- ✅ Ghost variant for minimal close button

**CSS Removed**: ~24 lines (.btn, .btn:disabled, .btn-success, .btn-danger, .btn-secondary, .btn-outline-primary, .btn-outline-light, .btn-sm)

---

**Batch 26 Summary**:
- Components: 3 (DocumentChangeFeed, RedisServiceControl, MonitoringDashboard)
- Buttons: 19 consolidated (8 knowledge + 6 services + 5 monitoring)
- Lines: ~129 saved (~75 knowledge + ~30 services + ~24 monitoring)
- Variants: 6 (primary, secondary, success, warning, danger, outline, ghost)
- **Combined Total**: 15 components, ~809 lines saved, 94 buttons consolidated

---

### **Batch 27 - Advanced Workflow Step Management** ✅ Completed

**Goal**: Migrate advanced workflow modal with complex step management controls to BaseButton for consistent UI patterns.

**Components Migrated**: 1 component, 17 buttons, ~170 lines saved

#### **AdvancedStepConfirmationModal.vue** (17 buttons, ~170 lines saved)

**Purpose**: Advanced workflow step management modal with command editing, risk assessment, and step reordering capabilities.

**Buttons Migrated**:

**Modal Header:**
- Close button → `<BaseButton variant="ghost" size="xs" class="close-button">` (×)

**Command Editor:**
- Edit command → `<BaseButton variant="outline" size="xs" class="edit-command-btn">` (📝 Edit)
- Save command → `<BaseButton variant="success" size="sm">` (💾 Save)
- Cancel command → `<BaseButton variant="secondary" size="sm">` (❌ Cancel)

**Step Management:**
- Toggle steps manager → `<BaseButton variant="outline" size="sm">` (▼ Hide / ▶ Show)
- Move step up → `<BaseButton variant="outline" size="xs" :disabled="index === 0">` (↑)
- Move step down → `<BaseButton variant="outline" size="xs" :disabled="index === workflowSteps.length - 1">` (↓)
- Delete step → `<BaseButton variant="danger" size="xs" :disabled="workflowSteps.length <= 1">` (🗑️)
- Edit step → `<BaseButton variant="outline" size="xs">` (✏️ Edit)
- Insert step after → `<BaseButton variant="success" size="xs">` (➕ Insert After)
- Add new step → `<BaseButton variant="success" class="add-step-btn">` (➕ Add New Step)
- Add step (form) → `<BaseButton variant="success">` (✅ Add Step)
- Cancel add step → `<BaseButton variant="secondary">` (❌ Cancel)

**Edit Dialog:**
- Close edit dialog → `<BaseButton variant="ghost" size="xs" class="close-button">` (×)
- Save edit → `<BaseButton variant="success" :disabled="!isEditFormValid || isSavingEdit" :loading="isSavingEdit">` (💾 Save Changes)
- Cancel edit → `<BaseButton variant="secondary" :disabled="isSavingEdit">` (❌ Cancel)

**Modal Actions (Primary):**
- Execute step → `<BaseButton variant="success" :disabled="!currentStep" class="execute-btn">` (✅ Execute This Step)
- Skip step → `<BaseButton variant="secondary" class="skip-btn">` (⏭️ Skip This Step)
- Manual control → `<BaseButton variant="primary" class="manual-btn">` (👤 Take Manual Control)

**Modal Actions (Secondary):**
- Execute all → `<BaseButton variant="info" class="execute-all-btn">` (🚀 Execute All Remaining)
- Save workflow → `<BaseButton variant="success" class="save-workflow-btn">` (💾 Save Workflow)
- Toggle advanced → `<BaseButton variant="secondary" class="toggle-advanced-btn">` (⚙️ Hide/Show Advanced)

**Key Patterns**:
- ✅ Complex conditional :disabled logic for step management controls
- ✅ Loading state integration with form validation (saveEdit)
- ✅ Ghost variant for minimal close buttons
- ✅ Size xs for compact step control buttons
- ✅ Dynamic variant mapping (success for execute, info for batch operations)
- ✅ Preserved custom classes for layout-specific styling (add-step-btn, execute-btn)

**CSS Removed**: ~170 lines removed from scoped styles:
- `.close-button`, `.edit-command-btn` (~13 lines)
- `.toggle-btn` (~12 lines)
- `.step-control`, `.step-control:hover`, `.step-control:disabled`, `.step-control.delete` (~28 lines)
- `.edit-step-btn`, `.insert-step-btn` (~14 lines)
- `.add-step-btn` (~13 lines)
- `.execute-btn`, `.skip-btn`, `.manual-btn`, `.execute-all-btn`, `.save-workflow-btn`, `.save-btn`, `.cancel-btn` (~93 lines including hover/disabled states)
- `.toggle-advanced-btn` (~14 lines)
- Media query references removed (~35 lines across 3 breakpoints)

---

**Batch 27 Summary**:
- Components: 1 (AdvancedStepConfirmationModal)
- Buttons: 17 consolidated (1 modal header + 3 command editor + 9 step management + 3 edit dialog + 6 modal actions)
- Lines: ~170 saved
- Variants: 7 (primary, secondary, success, danger, info, outline, ghost)
- **Combined Total**: 16 components, ~979 lines saved, 111 buttons consolidated

---

### **Batch 28 - Chat Input Component** ✅ Completed

**Goal**: Migrate chat input interface with file attachments, voice input, emoji picker, and quick actions to BaseButton.

**Components Migrated**: 1 component, 10 buttons, ~65 lines saved

#### **ChatInput.vue** (10 buttons, ~65 lines saved)

**Purpose**: Comprehensive chat input interface with file uploads, voice input, emoji picker, and quick action shortcuts.

**Buttons Migrated**:

**File Management:**
- Retry upload → `<BaseButton variant="danger" size="xs" class="retry-upload-btn">` (per upload item)
- Clear all files → `<BaseButton variant="ghost" size="sm" class="text-red-600">` (Clear all)
- Remove file → `<BaseButton variant="ghost" size="xs" class="remove-file-btn">` (per attached file)

**Input Actions:**
- Attach file → `<BaseButton variant="ghost" size="xs" class="action-btn" :disabled="isDisabled">` (📎)
- Voice input → `<BaseButton variant="ghost" size="xs" class="action-btn" :class="{ 'active': isVoiceRecording }" :disabled="isDisabled">` (🎤)
- Emoji picker → `<BaseButton variant="ghost" size="xs" class="action-btn" :disabled="isDisabled">` (😊)

**Quick Actions (4 buttons in v-for):**
- Help/Summarize/Translate/Explain → `<BaseButton variant="ghost" size="sm" class="action-btn quick-action-btn" :disabled="isDisabled">` (dynamic actions)

**Main Actions:**
- Send message → `<BaseButton variant="primary" class="send-button" :disabled="!canSend" :loading="isSending" :class="{ 'pulse': messageQueueLength > 0 }">` (✈️)

**Emoji Picker:**
- Close emoji picker → `<BaseButton variant="ghost" size="xs" class="close-emoji-btn">` (×)
- Emoji buttons (12 in v-for) → `<BaseButton variant="ghost" size="sm" class="emoji-btn">` (😀)

**Key Patterns**:
- ✅ Loading state integration for send button (`:loading` prop)
- ✅ Conditional :disabled for all input actions
- ✅ Active state preservation via :class for voice recording
- ✅ Ghost variant for minimal UI controls
- ✅ Queue indicator preserved in send button content
- ✅ Size xs for compact action buttons
- ✅ Custom classes preserved for layout (action-btn, send-button)

**CSS Removed**: ~65 lines removed from scoped styles:
- `.retry-upload-btn` (~3 lines)
- `.remove-file-btn` (~3 lines)
- `.action-btn`, `.action-btn:not(.quick-action-btn)`, `.action-btn.active`, `.action-btn:disabled` (~14 lines)
- `.quick-action-btn` (~4 lines)
- `.send-button`, `.send-button.sending` (~10 lines) - kept sizing and pulse animation
- `.close-emoji-btn` (~3 lines)
- `.emoji-btn` (~3 lines)
- Focus states: `.action-btn:focus`, `.quick-action-btn:focus`, `.emoji-btn:focus`, `.send-button:focus` (~8 lines)
- Remaining: action-label, send-button sizing/animation (preserved for layout)

---

**Batch 28 Summary**:
- Components: 1 (ChatInput)
- Buttons: 10 consolidated (3 file management + 3 input actions + 4 quick actions + 1 send + 2 emoji picker)
- Lines: ~65 saved
- Variants: 3 (primary, danger, ghost)
- **Combined Total**: 17 components, ~1,044 lines saved, 121 buttons consolidated

---

### **Batch 29 - Knowledge Browser** ✅ Completed

**Goal**: Migrate knowledge base file browser with category filters, search, batch operations, and file viewer to BaseButton.

**Components Migrated**: 1 component, 9 buttons, ~156 lines saved

#### **KnowledgeBrowser.vue** (9 buttons, ~156 lines saved)

**Purpose**: Comprehensive knowledge base file browser with category navigation, search, batch vectorization, and file viewer.

**Buttons Migrated**:

**Category Management:**
- Populate button (v-for per category) → `<BaseButton variant="primary" size="sm" :loading="populationStates[mainCat.id]?.isPopulating" :disabled="populationStates[mainCat.id]?.isPopulating" class="populate-btn">` (Populate knowledge)

**Category Filters (v-for pattern):**
- Category tabs → `<BaseButton :variant="selectedCategory === cat.value ? 'primary' : 'outline'" size="sm" class="category-tab">` (Filter by category)

**Search Controls:**
- Clear search → `<BaseButton variant="ghost" size="xs" class="clear-btn">` (×)

**Batch Operations Toolbar:**
- Vectorize selected → `<BaseButton variant="primary" :disabled="!canVectorizeSelection || isVectorizing" :loading="isVectorizing" class="toolbar-btn vectorize">` (Batch vectorize)
- Clear selection → `<BaseButton variant="secondary" class="toolbar-btn cancel">` (Clear batch selection)

**Navigation:**
- Breadcrumb root → `<BaseButton variant="ghost" size="sm" class="breadcrumb-item">` (🏠 Root)

**Error Handling:**
- Retry load → `<BaseButton variant="primary" class="retry-btn">` (🔄 Retry)

**Pagination:**
- Load more → `<BaseButton variant="primary" class="load-more-btn">` (Load More)

**File Viewer:**
- Close viewer → `<BaseButton variant="ghost" size="sm" class="close-btn">` (×)

**Key Patterns**:
- ✅ Loading state integration for populate and vectorize buttons (`:loading` prop)
- ✅ Dynamic variant switching for category tabs (primary when active, outline when inactive)
- ✅ Conditional :disabled for batch operations
- ✅ Ghost variant for minimal UI controls (clear, breadcrumb, close)
- ✅ v-for pattern with computed variant logic
- ✅ Progress percentage display in button content during population
- ✅ Size xs for compact control buttons
- ✅ Custom classes preserved for toolbar styling

**CSS Removed**: ~156 lines removed from scoped styles:
- `.populate-btn` (~32 lines) - kept spacing only
- `.category-tab` and active/hover states (~27 lines) - kept layout
- `.clear-btn` (~10 lines) - kept positioning
- `.toolbar-btn` variants (vectorize/cancel) (~27 lines) - kept custom colors
- `.breadcrumb-item` button styles (~18 lines) - removed all
- `.retry-btn` (~13 lines) - kept spacing only
- `.load-more-btn` (~18 lines) - kept container only
- `.close-btn` (~11 lines) - kept sizing only

---

**Batch 29 Summary**:
- Components: 1 (KnowledgeBrowser)
- Buttons: 9 consolidated (1 populate + category tabs + 1 search + 2 toolbar + 1 breadcrumb + 1 retry + 1 load-more + 1 close)
- Lines: ~156 saved
- Variants: 4 (primary, secondary, outline, ghost)
- **Combined Total**: 18 components, ~1,200 lines saved, 130 buttons consolidated

---

### **Batch 30 - Knowledge Advanced Management** ✅ Completed

**Goal**: Migrate knowledge base administrative management interface with population and database management actions to BaseButton.

**Components Migrated**: 1 component, 5 buttons, ~61 lines saved

#### **KnowledgeAdvanced.vue** (5 buttons, ~61 lines saved)

**Purpose**: Administrative knowledge management interface for populating and managing the knowledge base.

**Buttons Migrated**:

**Knowledge Population Actions (3 buttons):**
- Populate AutoBot Documentation → `<BaseButton variant="primary" :disabled="isPopulating" :loading="populateStatus.autobotDocs === 'loading'" class="action-btn">` (~30 documents)
- Populate System Commands → `<BaseButton variant="primary" :disabled="isPopulating" :loading="populateStatus.systemCommands === 'loading'" class="action-btn">` (~150 commands)
- Populate Manual Pages → `<BaseButton variant="primary" :disabled="isPopulating" :loading="populateStatus.manPages === 'loading'" class="action-btn">` (~50 man pages)

**Database Management:**
- Clear All Knowledge → `<BaseButton variant="danger" :disabled="isClearing || isPopulating" :loading="isClearing" class="action-btn">` (Destructive action)

**Status Messages:**
- Dismiss message → `<BaseButton variant="ghost" size="xs" class="dismiss-btn">` (×)

**Key Patterns**:
- ✅ Loading state integration for async operations (`:loading` prop replaces manual spinner)
- ✅ Conditional icon display (hide icon during loading, BaseButton shows spinner)
- ✅ Multiple disabled conditions (isPopulating, isClearing)
- ✅ Danger variant for destructive actions
- ✅ Ghost variant for minimal dismiss buttons
- ✅ Status tracking with computed button text
- ✅ Full width layout for action buttons

**CSS Removed**: ~61 lines removed from scoped styles:
- `.action-btn` base styles (~14 lines) - kept width: 100% only
- `.action-btn:disabled` (~4 lines)
- `.action-btn.primary` (~8 lines)
- `.action-btn.danger` (~8 lines)
- `.dismiss-btn` (~17 lines) - kept positioning only
- Hover states and transitions (~10 lines)

---

### **Batch 31 - Failed Vectorizations Manager** ✅ Completed

**Goal**: Migrate failed vectorization jobs management interface with retry and cleanup actions to BaseButton.

**Components Migrated**: 1 component, 4 buttons, ~58 lines saved

#### **FailedVectorizationsManager.vue** (4 buttons, ~58 lines saved)

**Purpose**: Failed vectorization jobs manager with per-job retry and cleanup functionality.

**Buttons Migrated**:

**Header Actions (2 buttons):**
- Refresh → `<BaseButton variant="primary" size="sm" :disabled="loading" :loading="loading" class="btn-refresh">` (Sync alt icon)
- Clear All → `<BaseButton variant="danger" size="sm" v-if="failedJobs.length > 0" :disabled="loading" class="btn-clear-all">` (Trash alt icon)

**Per-Job Actions (v-for, 2 buttons per job):**
- Retry → `<BaseButton variant="success" size="sm" :disabled="loading || retryingJobs.has(job.job_id)" :loading="retryingJobs.has(job.job_id)" class="btn-retry">` (Redo icon)
- Delete → `<BaseButton variant="secondary" size="sm" :disabled="loading" class="btn-delete">` (Trash icon)

**Key Patterns**:
- ✅ **Per-item loading states in v-for** - Using `Set<string>` for tracking individual job retry states
- ✅ Conditional loading prop with per-item check: `:loading="retryingJobs.has(job.job_id)"`
- ✅ Conditional icon display with Set check: `v-if="!retryingJobs.has(job.job_id)"`
- ✅ Multiple disabled conditions (global loading + per-item retrying)
- ✅ Success variant for positive actions (retry)
- ✅ Danger variant for destructive bulk actions (clear all)
- ✅ Secondary variant for per-item delete (less prominent than bulk clear)
- ✅ Conditional rendering for bulk actions (`v-if="failedJobs.length > 0"`)

**CSS Removed**: ~58 lines removed from scoped styles:
- `.btn-refresh` base styles (~10 lines)
- `.btn-clear-all` base styles (~10 lines)
- `.btn-retry` base styles + success variant (~14 lines)
- `.btn-delete` base styles + secondary variant (~14 lines)
- Hover states and transitions (~10 lines)

---

**Batch 30 Summary**:
- Components: 1 (KnowledgeAdvanced)
- Buttons: 5 consolidated (3 populate actions + 1 clear + 1 dismiss)
- Lines: ~61 saved
- Variants: 3 (primary, danger, ghost)

**Batch 31 Summary**:
- Components: 1 (FailedVectorizationsManager)
- Buttons: 4 consolidated (2 header actions + 2 per-job actions)
- Lines: ~58 saved
- Variants: 4 (primary, danger, success, secondary)

---

### **Batch 32 - File List Table Actions** ✅ Completed

**Goal**: Migrate file browser list table with per-row action buttons to BaseButton.

**Components Migrated**: 1 component, 4 buttons, ~24 lines saved

#### **FileListTable.vue** (4 buttons, ~24 lines saved)

**Purpose**: File browser list table with per-row file/directory actions (view, open, rename, delete).

**Buttons Migrated (v-for per file/directory):**

**Conditional File Actions:**
- View file → `<BaseButton variant="ghost" size="sm" v-if="!file.is_dir" class="action-btn view-btn">` (Eye icon)
- Open directory → `<BaseButton variant="ghost" size="sm" v-if="file.is_dir" class="action-btn open-btn">` (Folder open icon)

**Universal Actions:**
- Rename → `<BaseButton variant="ghost" size="sm" class="action-btn rename-btn">` (Edit icon)
- Delete → `<BaseButton variant="ghost" size="sm" class="action-btn delete-btn">` (Trash icon)

**Key Patterns**:
- ✅ Ghost variant for minimal icon-only action buttons
- ✅ Conditional rendering in v-for (view vs open based on file.is_dir)
- ✅ Per-row actions in table cells
- ✅ Consistent size (sm) for compact table layout
- ✅ Preserved aria-label and title for accessibility
- ✅ Icon-only buttons with hover interactions handled by BaseButton

**CSS Removed**: ~24 lines removed from scoped styles:
- `.action-btn` base styles + hover states (~6 lines)
- `.view-btn:hover` color override (~3 lines)
- `.open-btn:hover` color override (~3 lines)
- `.rename-btn:hover` color override (~3 lines)
- `.delete-btn:hover` color override (~3 lines)
- Tailwind utility classes for sizing, spacing, colors (~6 lines)

---

**Batch 32 Summary**:
- Components: 1 (FileListTable)
- Buttons: 4 consolidated (2 conditional + 2 universal per-row actions)
- Lines: ~24 saved
- Variants: 1 (ghost for minimal action buttons)

---

### **Batch 33 - File Browser Header** ✅ Completed

**Goal**: Migrate file browser header navigation and action buttons to BaseButton.

**Components Migrated**: 1 component, 3 buttons, ~19 lines saved

#### **FileBrowserHeader.vue** (3 buttons, ~19 lines saved)

**Purpose**: File browser header with path navigation and file management actions.

**Buttons Migrated**:

**Path Navigation:**
- Path go button → `<BaseButton variant="primary" size="sm" class="path-go-btn">` (Arrow right icon, navigate to entered path)

**File Actions:**
- New Folder → `<BaseButton variant="outline" size="sm" aria-label="Create new folder">` (Folder plus icon + text)
- Upload File → `<BaseButton variant="outline" size="sm" aria-label="Upload file">` (Upload icon + text)

**Key Patterns**:
- ✅ Primary variant for main path navigation action (blue background)
- ✅ Outline variant for secondary file actions (white background with border)
- ✅ Consistent sm size for compact header layout
- ✅ Icon + text combination for clear action labels
- ✅ Preserved aria-label attributes for accessibility
- ✅ Maintained path input integration with Enter key handler

**CSS Removed**: ~19 lines removed from scoped styles:
- `.path-go-btn` Tailwind classes (~3 lines)
- `.file-actions button` base styles (~3 lines)
- `.file-actions button:hover` hover state (~3 lines)
- `.file-actions button i` icon styles (~3 lines)
- Padding, colors, borders, focus states (~7 lines)

---

**Batch 33 Summary**:
- Components: 1 (FileBrowserHeader)
- Buttons: 3 consolidated (1 navigation + 2 file actions)
- Lines: ~19 saved
- Variants: 2 (primary for navigation, outline for actions)

---

### **Batch 34 - Deduplication Manager** ✅ Completed

**Goal**: Migrate knowledge base deduplication and orphan management interface to BaseButton.

**Components Migrated**: 1 component, 3 buttons, ~50 lines saved

#### **DeduplicationManager.vue** (3 buttons, ~50 lines saved)

**Purpose**: Knowledge base maintenance tool for scanning and removing duplicate and orphaned documents.

**Buttons Migrated**:

**Scan Action:**
- Scan for Issues → `<BaseButton variant="primary" size="sm" :disabled="scanning" :loading="scanning">` (Search icon)

**Cleanup Actions:**
- Remove All Duplicates → `<BaseButton variant="warning" :disabled="cleaning" :loading="cleaning">` (Trash icon, warning variant for caution)
- Remove All Orphans → `<BaseButton variant="danger" :disabled="cleaning" :loading="cleaning">` (Trash icon, danger variant for destructive action)

**Key Patterns**:
- ✅ Loading state integration (`:loading` prop replaces manual spinner conditionals)
- ✅ Conditional icon display (`v-if="!loading"` to hide icon during loading)
- ✅ Dynamic button text based on state (scanning/cleaning vs idle)
- ✅ Warning variant for potentially destructive batch operations (duplicates)
- ✅ Danger variant for irreversible operations (orphans)
- ✅ Primary variant for main scan action
- ✅ Shared cleaning state for both cleanup actions

**CSS Removed**: ~50 lines removed from scoped styles:
- `.btn-scan` base styles + hover + disabled (~18 lines)
- `.btn-cleanup` base styles + disabled (~14 lines)
- `.btn-warning` variant + hover (~6 lines)
- `.btn-danger` variant + hover (~6 lines)
- Flex, padding, colors, transitions (~6 lines)

---

**Batch 34 Summary**:
- Components: 1 (DeduplicationManager)
- Buttons: 3 consolidated (1 scan + 2 cleanup actions)
- Lines: ~50 saved
- Variants: 3 (primary, warning, danger)
- **Combined Total**: 23 components, ~1,412 lines saved, 149 buttons consolidated

---

### **Batch 35 - Chat Messages Component** ✅ Completed

**Goal**: Migrate comprehensive chat message display with inline actions, command approvals, and message editing modals to BaseButton.

**Components Migrated**: 1 component, 10 buttons, ~60 lines saved

#### **ChatMessages.vue** (10 buttons, ~60 lines saved)

**Purpose**: Main chat message display with inline message actions, command approval workflow, comment system, and message editing capabilities.

**Buttons Migrated**:

**Message Actions (Inline per message):**
- Edit message → `<BaseButton variant="ghost" size="xs" v-if="message.sender === 'user'" class="action-btn">` (conditional on user messages)
- Copy message → `<BaseButton variant="ghost" size="xs" class="action-btn">` (universal action)
- Delete message → `<BaseButton variant="ghost" size="xs" class="action-btn danger">` (universal action)

**Comment Actions:**
- Cancel comment → `<BaseButton variant="secondary" size="sm" class="cancel-comment-btn">` (Cancel)
- Submit approval → `<BaseButton variant="primary" size="sm" :disabled="!approvalComment.trim()" class="submit-comment-btn">` (Submit Approval/Denial)

**Approval Actions (Command approval workflow):**
- Approve command → `<BaseButton variant="success" size="sm" :disabled="processingApproval || showCommentInput" class="approve-btn">` (Approve)
- Add comment → `<BaseButton variant="outline" size="sm" :disabled="processingApproval || showCommentInput" class="comment-btn">` (Comment)
- Deny command → `<BaseButton variant="danger" size="sm" :disabled="processingApproval || showCommentInput" class="deny-btn">` (Deny)

**Edit Modal Actions:**
- Cancel edit → `<BaseButton variant="secondary" @click="cancelEdit">` (Cancel)
- Save edit → `<BaseButton variant="primary" @click="saveEditedMessage" :disabled="!editingContent.trim()">` (Save)

**Key Patterns**:
- ✅ Ghost variant with xs size for minimal inline message actions (edit, copy, delete)
- ✅ Conditional rendering for user-only actions (edit message)
- ✅ Success/danger variants for approval workflow (approve = green, deny = red)
- ✅ Outline variant for neutral actions (comment)
- ✅ Disabled state management with complex conditions (processingApproval || showCommentInput)
- ✅ Form validation in disabled state (!approvalComment.trim(), !editingContent.trim())
- ✅ Secondary variant for cancel actions in modals and forms
- ✅ Primary variant for main submit actions
- ✅ Preserved custom classes for layout-specific styling

**CSS Removed**: ~60 lines removed from scoped styles:
- `.action-btn` base and color overrides for user/assistant messages (~17 lines)
- `.action-btn.danger:hover` (~3 lines)
- `.approve-btn`, `.deny-btn` base styles and variants (~12 lines)
- `.cancel-comment-btn`, `.submit-comment-btn`, `.comment-btn` (~12 lines)
- Responsive overrides for `.action-btn`, `.approve-btn`, `.deny-btn` (~12 lines)
- Remaining: Layout containers (`.message-actions`, `.approval-actions`, `.comment-actions`) preserved for flex layouts

---

**Batch 35 Summary**:
- Components: 1 (ChatMessages)
- Buttons: 10 consolidated (3 inline message actions + 2 comment actions + 3 approval workflow + 2 edit modal)
- Lines: ~60 saved
- Variants: 6 (primary, secondary, success, danger, outline, ghost)
- **Combined Total**: 24 components, ~1,472 lines saved, 159 buttons consolidated

---

### **Batch 36 - Knowledge Entries Management** ✅ Completed

**Goal**: Migrate comprehensive knowledge entry management interface with tabs, filters, bulk actions, per-entry actions, pagination, and edit dialog to BaseButton.

**Components Migrated**: 1 component, 15 buttons, ~90 lines saved

#### **KnowledgeEntries.vue** (15 buttons, ~90 lines saved)

**Purpose**: Main knowledge entry management interface with upload/manage/advanced tabs, bulk operations, filtering, per-entry actions, pagination, and full-featured edit dialog.

**Buttons Migrated**:

**Tab Navigation (3 buttons):**
- Upload tab → `<BaseButton variant="ghost" :class="['manage-tab-btn', { active: manageTab === 'upload' }]">` (Upload)
- Manage tab → `<BaseButton variant="ghost" :class="['manage-tab-btn', { active: manageTab === 'manage' }]">` (Manage)
- Advanced tab → `<BaseButton variant="ghost" :class="['manage-tab-btn', { active: manageTab === 'advanced' }]">` (Advanced)

**Bulk Actions (2 buttons):**
- Export selected → `<BaseButton variant="primary" size="sm" :disabled="selectedEntries.length === 0">` (Export (N))
- Delete selected → `<BaseButton variant="danger" size="sm" :disabled="selectedEntries.length === 0">` (Delete (N))

**Filter Actions (1 button):**
- Clear filters → `<BaseButton variant="secondary" size="sm" class="clear-filters-btn">` (Clear Filters)

**Per-Entry Actions in Table (3 buttons per entry in v-for):**
- View entry → `<BaseButton variant="ghost" size="xs" class="icon-btn">` (eye icon)
- Edit entry → `<BaseButton variant="ghost" size="xs" class="icon-btn">` (edit icon)
- Delete entry → `<BaseButton variant="ghost" size="xs" class="icon-btn danger">` (trash icon)

**Pagination (2 buttons):**
- Previous page → `<BaseButton variant="outline" size="sm" :disabled="currentPage === 1">` (chevron-left)
- Next page → `<BaseButton variant="outline" size="sm" :disabled="currentPage === totalPages">` (chevron-right)

**Dialog Actions (4 buttons):**
- Close dialog → `<BaseButton variant="ghost" size="sm" class="close-btn">` (× icon)
- Edit button (view mode) → `<BaseButton variant="primary" v-if="dialogMode === 'view'">` (Edit)
- Cancel edit → `<BaseButton variant="secondary" v-if="dialogMode === 'edit'">` (Cancel)
- Save changes → `<BaseButton variant="primary" v-if="dialogMode === 'edit'">` (Save Changes)

**Key Patterns**:
- ✅ Ghost variant for minimal tab navigation with .active class preserved
- ✅ Primary/danger variants for bulk actions with dynamic count display
- ✅ Ghost variant with xs size for compact table icon buttons
- ✅ Outline variant for pagination controls
- ✅ Disabled state with selection count validation (selectedEntries.length === 0)
- ✅ Disabled state with boundary checks (currentPage === 1, currentPage === totalPages)
- ✅ Conditional rendering with v-if for dialog mode (view vs edit)
- ✅ Secondary variant for cancel actions
- ✅ Preserved custom classes for active state styling (.manage-tab-btn.active)

**CSS Removed**: ~90 lines removed from scoped styles:
- `.manage-tab-btn` base styles and hover (~13 lines) - kept .active class
- `.action-btn` base, hover, danger, disabled states (~27 lines)
- `.clear-filters-btn` base and hover (~14 lines)
- `.icon-btn` base, hover, danger hover (~23 lines)
- `.page-btn` base, hover, disabled states (~22 lines)
- `.close-btn` base and hover (~17 lines)
- `.edit-btn`, `.cancel-btn`, `.save-btn` shared and individual styles (~40 lines)
- Remaining: Layout containers (.manage-tabs, .pagination, .dialog-actions) and .active state preserved

---

**Batch 36 Summary**:
- Components: 1 (KnowledgeEntries)
- Buttons: 15 consolidated (3 tabs + 2 bulk actions + 1 filter + 3 per-entry actions + 2 pagination + 4 dialog)
- Lines: ~90 saved
- Variants: 5 (primary, secondary, danger, outline, ghost)
- **Combined Total**: 25 components, ~1,562 lines saved, 174 buttons consolidated

---

### **Batch 37 - Knowledge Categories Browser** ✅ Completed

**Goal**: Migrate main knowledge category browsing interface with category navigation, management actions, document viewing, and modal forms to BaseButton.

**Components Migrated**: 1 component, 8 buttons, ~65 lines saved

#### **KnowledgeCategories.vue** (8 buttons, ~65 lines saved)

**Purpose**: Main knowledge category browsing interface with main category selection, legacy user category management, and document panel.

**Buttons Migrated**:

**Navigation (1 button):**
- Back to categories → `<BaseButton variant="outline" class="back-btn">` (Back to Categories)

**Category Management (2 buttons):**
- Create category → `<BaseButton variant="primary" size="sm" class="create-category-btn">` (New Category)

**Per-Category Actions (2 buttons per category with @click.stop):**
- Edit category → `<BaseButton variant="ghost" size="xs" @click.stop="editCategory(category)">` (edit icon)
- Delete category → `<BaseButton variant="ghost" size="xs" @click.stop="deleteCategory(category)" class="action-btn danger">` (trash icon)

**Document Actions (1 button):**
- View documents → `<BaseButton variant="outline" size="sm" @click.stop="viewDocuments(category)">` (View Documents)

**Dialog Actions (2 buttons with form validation):**
- Cancel → `<BaseButton variant="secondary" @click="closeDialogs">` (Cancel)
- Save/Update → `<BaseButton variant="primary" :disabled="!categoryForm.name.trim()">` (Create/Update - dynamic text)

**Panel Actions (1 button):**
- Close panel → `<BaseButton variant="ghost" size="sm" class="close-panel-btn">` (× icon)

**Key Patterns**:
- ✅ Outline variant for navigation and view actions
- ✅ Primary variant for create action with sm size
- ✅ Ghost variant with xs size for compact per-category icon buttons
- ✅ Event propagation control with @click.stop on nested clickable elements
- ✅ Form validation with disabled state (!categoryForm.name.trim())
- ✅ Dynamic button text based on dialog mode (showEditDialog ? 'Update' : 'Create')
- ✅ Secondary variant for cancel actions
- ✅ Preserved category card click handlers while allowing independent action buttons

**CSS Removed**: ~65 lines removed from scoped styles:
- `.back-btn` base styles and hover (~18 lines)
- `.create-category-btn` base and hover (~17 lines)
- `.action-btn` base, hover, danger states (~23 lines)
- `.view-docs-btn` base and hover (~16 lines)
- `.cancel-btn`, `.save-btn` shared and individual styles (~32 lines)
- `.close-panel-btn` base and hover (~17 lines)
- Remaining: Layout containers (.category-grid, .category-card, .panel-header) and card selection state preserved

---

**Batch 37 Summary**:
- Components: 1 (KnowledgeCategories)
- Buttons: 8 consolidated (1 navigation + 1 create + 2 per-category actions + 1 view + 2 dialog + 1 panel)
- Lines: ~65 saved
- Variants: 4 (primary, secondary, outline, ghost)
- **Combined Total**: 26 components, ~1,627 lines saved, 182 buttons consolidated

---

### **Batch 38 - Knowledge Persistence Dialog** ✅ Completed

**Goal**: Migrate comprehensive knowledge management decision dialog with bulk actions, compile functionality, and decision tracking to BaseButton.

**Components Migrated**: 1 component, 9 buttons, ~85 lines saved

#### **KnowledgePersistenceDialog.vue** (9 buttons, ~85 lines saved)

**Purpose**: Comprehensive knowledge management dialog for reviewing, categorizing, and persisting chat knowledge items with bulk operations and compile functionality.

**Buttons Migrated**:

**Header (1 button):**
- Close dialog → `<BaseButton variant="ghost" size="sm" class="close-button">` (× icon)

**Bulk Actions (5 buttons with selection validation):**
- Select all → `<BaseButton variant="outline" class="bulk-button">` (✅ Select All)
- Deselect all → `<BaseButton variant="outline" class="bulk-button">` (❌ Deselect All)
- Add to KB → `<BaseButton variant="success" :disabled="!hasSelectedItems" class="bulk-button add">` (💾 Add Selected to KB)
- Keep temporary → `<BaseButton variant="warning" :disabled="!hasSelectedItems" class="bulk-button temp">` (⏰ Keep Selected Temporarily)
- Delete → `<BaseButton variant="danger" :disabled="!hasSelectedItems" class="bulk-button delete">` (🗑️ Delete Selected)

**Compile Section (1 button):**
- Compile chat → `<BaseButton variant="primary" class="compile-button">` (📚 Compile Chat to Knowledge Base)

**Dialog Actions (2 buttons):**
- Apply decisions → `<BaseButton variant="success" :disabled="!hasDecisions" class="primary-button">` (✅ Apply Decisions)
- Cancel → `<BaseButton variant="secondary" class="secondary-button">` (❌ Cancel)

**Key Patterns**:
- ✅ Ghost variant with sm size for minimal header close button
- ✅ Outline variant for selection control actions
- ✅ Success/warning/danger variants for categorized bulk actions
- ✅ Disabled state with computed property validation (hasSelectedItems, hasDecisions)
- ✅ Primary variant for major action (compile chat)
- ✅ Success variant for primary dialog action with disabled state
- ✅ Secondary variant for cancel action
- ✅ Consistent emoji icons preserved in button text

**CSS Removed**: ~85 lines removed from scoped styles:
- `.close-button` base and hover (~13 lines)
- `.bulk-button` base, hover, disabled, and variant-specific styles (.add, .temp, .delete) (~34 lines)
- `.compile-button` base and hover (~14 lines)
- `.primary-button` base, hover, disabled (~18 lines)
- `.secondary-button` base and hover (~6 lines)
- Responsive media query button styles removed
- Remaining: Layout containers (.bulk-buttons, .action-buttons) and summary items preserved

---

**Batch 38 Summary**:
- Components: 1 (KnowledgePersistenceDialog)
- Buttons: 9 consolidated (1 close + 5 bulk actions + 1 compile + 2 dialog actions)
- Lines: ~85 saved
- Variants: 6 (primary, secondary, success, warning, danger, outline, ghost)
- **Combined Total**: 27 components, ~1,712 lines saved, 191 buttons consolidated

---

### **Batch 39 - Phase Progression Indicator** ✅ Completed

**Goal**: Migrate system phase validation and progression controls with status monitoring, validation triggers, and auto-progression to BaseButton.

**Components Migrated**: 1 component, 6 buttons, ~70 lines saved

#### **PhaseProgressionIndicator.vue** (6 buttons, ~70 lines saved)

**Purpose**: System phase status monitoring with on-demand validation, manual progression triggers, and auto-progression controls.

**Buttons Migrated**:

**Header Controls (1 button):**
- Load validation data → `<BaseButton variant="outline" :disabled="loading" class="load-validation-btn">` (Load Validation Data)

**Error State (1 button):**
- Retry load → `<BaseButton variant="warning" class="retry-button">` (Retry)

**Per-Phase Actions (2 buttons per phase):**
- Progress phase → `<BaseButton variant="primary" size="sm" :disabled="progressionInProgress" class="btn-progression">` (Progress)
- Validate phase → `<BaseButton variant="success" size="sm" :disabled="validationInProgress" class="btn-validate">` (Validate)

**Auto-Progression Controls (2 buttons):**
- Run full validation → `<BaseButton variant="primary" :disabled="validationInProgress" class="btn-full-validation">` (Run Full System Validation)
- Trigger auto-progression → `<BaseButton variant="success" :disabled="progressionInProgress || !autoProgressionEnabled" class="btn-auto-progression">` (Trigger Auto-Progression)

**Key Patterns**:
- ✅ Outline variant for header control action
- ✅ Warning variant for error state retry action
- ✅ Primary/success variants with sm size for per-phase actions
- ✅ Disabled states with loading/progress flags (loading, progressionInProgress, validationInProgress)
- ✅ Disabled state with conditional logic (!autoProgressionEnabled)
- ✅ Dynamic button text with loading state (loading ? 'Loading...' : 'Load Validation Data')
- ✅ Spinner icons for loading states (fa-spinner fa-spin)

**CSS Removed**: ~70 lines removed from scoped styles:
- `.load-validation-btn` base, hover, disabled (~23 lines)
- `.retry-button` base, hover, icon styles (~20 lines)
- `.btn-progression`, `.btn-validate` shared and individual styles (~17 lines)
- `.btn-full-validation`, `.btn-auto-progression` shared and individual styles (~30 lines)
- Remaining: Layout containers (.header-controls, .phase-actions, .controls-grid) preserved

---

**Batch 39 Summary**:
- Components: 1 (PhaseProgressionIndicator)
- Buttons: 6 consolidated (1 header + 1 retry + 2 per-phase actions + 2 auto-progression controls)
- Lines: ~70 saved
- Variants: 4 (primary, success, warning, outline)
- **Combined Total**: 28 components, ~1,782 lines saved, 197 buttons consolidated

---

### **Batch 40 - System Status Indicator** ✅ Completed

**Goal**: Migrate system status monitoring indicator with notification management, status details, and quick actions to BaseButton.

**Components Migrated**: 1 component, 5 buttons, ~35 lines saved

#### **SystemStatusIndicator.vue** (5 buttons, ~35 lines saved)

**Purpose**: Fixed system status indicator with dropdown details panel, notification list, and quick action controls.

**Buttons Migrated**:

**Main Status Indicator (1 button):**
- Status indicator → `<BaseButton variant="primary" :class="statusClasses" :title="getStatusDescription(indicator.status)">` (System status with dynamic classes)

**Details Panel Controls (2 buttons):**
- Close details → `<BaseButton variant="ghost" size="sm" class="text-gray-400...">` (Close)
- Refresh status → `<BaseButton variant="primary" size="xs" class="px-3 py-1...">` (Refresh)

**Notification Actions (2 buttons):**
- Clear all notifications → `<BaseButton variant="danger" size="xs" v-if="activeNotificationCount > 0" class="px-3 py-1...">` (Clear All)
- Hide notification → `<BaseButton variant="ghost" size="xs" class="ml-2 p-1">` (Per-notification hide, v-for)

**Key Patterns**:
- ✅ Primary variant for main status indicator with preserved dynamic class bindings (statusClasses computed property)
- ✅ Ghost variant with sm/xs sizes for minimal close/hide buttons
- ✅ Primary/danger variants with xs size for quick actions
- ✅ Conditional rendering with notification count (v-if="activeNotificationCount > 0")
- ✅ Per-notification actions in v-for loop
- ✅ Preserved complex status-based styling (bg-green/yellow/red/gray with animate-pulse)
- ✅ Teleport integration with dropdown details panel
- ✅ Icon components (Heroicons) with dynamic rendering

**CSS Impact**: ~35 lines saved from cleaner template code (no button-specific CSS in this component - uses custom animations and scrollbar styles for other UI elements).

---

**Batch 40 Summary**:
- Components: 1 (SystemStatusIndicator)
- Buttons: 5 consolidated (1 main status + 1 close + 2 quick actions + 1 per-notification hide)
- Lines: ~35 saved
- Variants: 3 (primary, ghost, danger)
- **Combined Total**: 29 components, ~1,817 lines saved, 202 buttons consolidated

---

## BaseAlert Component Creation & Migration (Batches 41-46)

### **Batch 41 - BaseAlert Component Creation + LoginForm Migration** ✅ Completed

**Goal**: Create reusable BaseAlert component to consolidate inline alert patterns and migrate first component.

**New Component**: BaseAlert.vue (`autobot-user-frontend/src/components/ui/BaseAlert.vue`)

**Features**:
- 5 variants: success, info, warning, error, critical
- Icon support with Heroicons (CheckCircleIcon, InformationCircleIcon, ExclamationTriangleIcon, XCircleIcon)
- Optional title and message props
- Slots: default (message), icon, actions
- Dismissible with optional auto-dismiss timer (milliseconds)
- Bordered variant with left accent border (4px)
- Dark mode support with adjusted colors
- TypeScript interface for props
- Accessible with role="alert"
- Emits dismiss event

**First Migration**: LoginForm.vue (2 alerts, ~22 lines saved)
- Replaced error-alert div with BaseAlert variant="error"
- Replaced warning-alert div with BaseAlert variant="warning"
- Removed error-alert/warning-alert CSS (~18 lines)
- Removed icon CSS (~2 lines: icon-alert-circle, icon-lock)

---

### **Batch 42 - KnowledgeUpload Migration** ✅ Completed

**Component**: KnowledgeUpload.vue (2 alerts, ~18 lines saved)

**Alerts Migrated**:
1. Success message → BaseAlert variant="success"
2. Error message → BaseAlert variant="error"

**Changes**:
- Added BaseAlert import
- Replaced alert divs with BaseAlert components
- Removed alert CSS (~15 lines: .alert + .alert-success + .alert-error)
- Removed FontAwesome icon markup (CheckCircle, ExclamationCircle)

---

### **Batch 43 - NPUWorkersSettings Migration** ✅ Completed

**Component**: NPUWorkersSettings.vue (1 alert, ~14 lines saved)

**Alert Migrated**:
1. Worker form error → BaseAlert variant="error"

**Changes**:
- Added BaseAlert import
- Replaced error-alert div with BaseAlert component
- Removed error-alert CSS (~14 lines: base class + icon styles)
- Replaced FontAwesome with Heroicons automatically

---

### **Batch 44 - ValidationDashboard Migration** ✅ Completed

**Component**: ValidationDashboard.vue (alerts list, ~40 lines saved)

**Alerts Migrated**:
- Alert list with v-for loop (critical/warning/info variants)
- Dynamic variant binding based on alert.level
- Title and message props from alert data
- Timestamp in actions slot

**Changes**:
- Added BaseAlert import and component registration
- Replaced v-for div with BaseAlert v-for loop
- Used bordered prop for left accent border
- Moved timestamp to actions slot for right-aligned display
- Removed alert CSS (~40 lines: .alert, .alert-critical, .alert-warning, .alert-info, .alert-title)
- Added .alerts-list CSS for flex gap spacing

**Key Patterns**:
- Dynamic variant binding: `:variant="alert.level"`
- Title/message props from data
- Actions slot for timestamp display
- V-for rendering with BaseAlert

---

### **Batch 45 - MonitoringDashboard Migration** ✅ Completed

**Component**: MonitoringDashboard.vue (alert banner, ~17 lines saved)

**Alert Migrated**:
- Critical alert banner with dynamic count message
- BaseButton in actions slot for "View Details"

**Changes**:
- Added BaseAlert import and component registration
- Replaced alert-banner div with BaseAlert variant="critical"
- Dynamic message with template literal for alert count
- BaseButton placed in actions slot
- Removed alert-banner CSS (~17 lines: base class + critical variant)

**Note**: Alert items list in modal not migrated - uses custom structure with StatusBadge, specific header layout, and recommendation section that doesn't fit BaseAlert pattern.

---

### **Batch 46 - ResearchBrowser Migration** ✅ Completed

**Component**: ResearchBrowser.vue (interaction alert, ~10 lines saved)

**Alert Migrated**:
- Interaction required warning with action buttons
- Warning variant for user attention
- Two BaseButtons in actions slot (Wait, Open Browser)

**Changes**:
- Added BaseAlert import and component registration
- Replaced interaction-alert div with BaseAlert variant="warning"
- Used bordered prop for left accent border
- Actions slot contains flex container with two buttons
- Removed inline Tailwind classes (~10 lines of utility classes)

---

**BaseAlert Migration Summary (Batches 41-46)**:
- **Components Migrated**: 6 components (LoginForm, KnowledgeUpload, NPUWorkersSettings, ValidationDashboard, MonitoringDashboard, ResearchBrowser)
- **Alerts Consolidated**: 10+ alerts
- **Lines Saved**: ~121 lines
- **Target**: ~50-100 lines estimated → **121 lines achieved** ✅ **TARGET EXCEEDED**
- **Variants Used**: All 5 variants (success, info, warning, error, critical)
- **Key Patterns**: Simple messages, v-for loops, actions slot with buttons, dynamic variant binding, title + message structure

---

## BaseModal Component Adoption (Batches 47-49)

### **Batch 47 - TerminalModals.vue Migration** ✅ Completed

**Goal**: Migrate 4 terminal-related modals to BaseModal, consolidating duplicate overlay and modal structure code.

**Component**: TerminalModals.vue (963 → 781 lines, ~182 lines saved, 19% reduction)

**Modals Migrated**:
1. **Reconnect modal** - Connection lost dialog (small size)
2. **Command confirmation modal** - Destructive command warning with risk assessment (medium size)
3. **Emergency kill modal** - Process termination warning (medium size, emergency styling)
4. **Legacy workflow modal** - AI workflow step confirmation with 3 action buttons (large size)

**Changes**:
- Added BaseModal import and component usage
- Converted all 4 modals from inline overlay/modal divs to BaseModal with v-model
- Mapped size variants (small, medium, large) directly to BaseModal sizes
- Preserved all content-specific styling (command-preview, risk-assessment, workflow-options)
- Maintained BaseButton integration throughout all modal actions
- Implemented conditional closeOnOverlay based on loading states (isReconnecting, isExecutingCommand, isKillingProcesses, isProcessingWorkflow)

**CSS Removed**:
- Modal overlay structure (~10 lines)
- Confirmation modal overlay and structure (~30 lines)
- Modal header, title, and content structure (~20 lines)
- Modal actions footer structure (~10 lines)
- Duplicate mobile responsiveness rules (~30 lines)
- Total: ~100 lines of structure CSS

**Patterns Preserved**:
- Error/success message displays remain unchanged
- Risk assessment styling intact (risk-level variants: low/moderate/high/critical)
- Emergency warning styling preserved
- Workflow step counter and options styling maintained
- Loading states with disabled close-on-overlay during operations

---

### **Batch 48 - KnowledgeSearch.vue Migration** ✅ Completed

**Goal**: Migrate document viewer modal to BaseModal.

**Component**: KnowledgeSearch.vue (741 → 686 lines, ~54 lines saved, 7% reduction)

**Modal Migrated**:
- **Document viewer modal** - Full document display with metadata and copy action (large size, scrollable)

**Changes**:
- Added BaseModal import
- Converted document-modal-overlay div to BaseModal with v-model bound to showDocumentModal
- Used large scrollable modal size for optimal document viewing
- Document metadata (type, category, updated date) moved into default slot
- Copy action and close buttons moved to actions slot

**CSS Removed**:
- document-modal-overlay and fadeIn animation (~15 lines)
- document-modal container and slideUp animation (~15 lines)
- document-modal-header structure (~10 lines)
- modal-close-button styling (~3 lines)
- document-modal-content wrapper (~3 lines)
- document-modal-footer structure (~8 lines)
- Total: ~54 lines

**Content-Specific Styles Preserved**:
- document-modal-meta display
- modal-meta-item styling
- modal-loading spinner
- document-text display
- modal-no-content empty state
- modal-action-button custom styling

---

### **Batch 49 - SecretsManager.vue Migration** ✅ Completed

**Goal**: Migrate all 3 secrets management modals to BaseModal.

**Component**: SecretsManager.vue (1103 → 1037 lines, ~65 lines saved, 6% reduction)

**Modals Migrated**:
1. **Create/Edit modal** - Secret form for creating/updating secrets (medium size, form validation)
2. **View modal** - Secret details display with show/hide value toggle (medium size)
3. **Transfer modal** - Confirmation dialog for transferring secrets between scopes (medium size, checkbox confirmation)

**Changes**:
- Added BaseModal to component imports and registration
- Converted all 3 modal-overlay divs to BaseModal with v-model patterns
- Create/Edit: Combined showCreateModal || showEditModal into single v-model condition
- View: Bound v-model to showViewModal
- Transfer: Bound v-model to showTransferModal
- All form submissions and action buttons moved to actions slots
- Conditional closeOnOverlay for Create/Edit (!saving) and Transfer (!transferring) modals

**CSS Removed**:
- modal-overlay structure (~15 lines)
- modal container and sizing (~8 lines)
- modal-header with h3 and close button (~20 lines)
- btn-close button styling (~12 lines)
- modal-body padding (~3 lines)
- modal-actions footer structure (~7 lines)
- Total: ~65 lines

**Features Preserved**:
- Create/Edit modal: Form structure with required fields, validation, saving state
- View modal: Secret value show/hide toggle, metadata display, copy functionality
- Transfer modal: Confirmation checkbox, warning message, transferring state
- Custom button styling maintained (btn-primary, btn-secondary)
- Form groups and validation intact
- StatusBadge integration for scope and type badges

---

### **Batch 50 - NPUWorkersSettings.vue Migration** ✅ Completed

**Goal**: Migrate all 3 NPU worker management modals to BaseModal.

**Component**: NPUWorkersSettings.vue (1446 → 1359 lines, ~87 lines saved, 6% reduction)

**Modals Migrated**:
1. **Add/Edit Worker modal** - Complex form with validation, BaseAlert integration (medium size)
2. **Delete Confirmation modal** - Warning dialog with danger styling (small size)
3. **Worker Metrics modal** - Performance metrics grid display (large size)

**Changes**:
- Added BaseModal import and component usage
- Add/Edit Worker: Conditional title (showEditWorkerDialog ? 'Edit' : 'Add'), form validation, operation locking
- Delete Confirmation: Custom title slot with red warning styling, conditional close during deletion
- Worker Metrics: Conditional rendering with v-if="selectedWorkerMetrics", metrics grid layout
- All modals use conditional closeOnOverlay based on operation states (isSavingWorker, isDeletingWorker, operationInProgress)

**CSS Removed**:
- .modal-overlay structure with inset positioning and backdrop (~10 lines)
- .modal-dialog + size variants (.modal-sm, .modal-lg) (~15 lines)
- .modal-header structure (~10 lines)
- .modal-title styling (~5 lines)
- .modal-close button (~10 lines)
- .modal-body scrollable container (~5 lines)
- .modal-footer actions container (~7 lines)
- Total: ~70 lines of structure CSS

**Patterns Preserved**:
- Form validation with isWorkerFormValid computed property
- Loading states with spinner icons
- Operation locking to prevent race conditions
- BaseAlert error display integration
- Custom title slots for icons and styling
- Metrics grid display for performance data

---

### **Batch 51 - UserManagementSettings.vue Migration** ✅ Completed

**Goal**: Migrate user authentication and profile management modals to BaseModal.

**Component**: UserManagementSettings.vue (662 → 589 lines, ~73 lines saved, 11% reduction)

**Modals Migrated**:
1. **Login modal** - Simple wrapper around LoginForm component (medium size)
2. **Change Password modal** - Password form with validation (medium size)

**Changes**:
- Added BaseModal import
- Removed teleport wrappers (BaseModal handles portal internally)
- Login: Clean integration with LoginForm, success/error callback handling
- Change Password: Three password fields (current, new, confirm), conditional closeOnOverlay during password change
- Actions moved to slots with proper button ordering (Cancel first, Action second)

**CSS Removed**:
- .modal-overlay structure (~12 lines)
- .modal-content container (~8 lines)
- .modal-header structure (~7 lines)
- .modal-header h3 styling (~4 lines)
- .close-btn button (~7 lines)
- .change-password-form padding wrapper (~3 lines)
- Dark theme modal overrides (content, header, h3) (~12 lines)
- Total: ~79 lines

**Features Preserved**:
- LoginForm component integration unchanged
- Password form validation (matching new/confirm passwords)
- Loading states with spinner icons
- Disabled button states during async operations
- Success/error callback handling (onLoginSuccess, onLoginError)
- User profile state management

---

### **Batch 52 - MonitoringDashboard.vue Migration** ✅ Completed

**Goal**: Migrate performance monitoring alerts modal to BaseModal.

**Component**: MonitoringDashboard.vue (1386 → 1333 lines, ~53 lines saved, 4% reduction)

**Modal Migrated**:
- **Performance Alerts modal** - Scrollable list of performance alerts with severity badges (large, scrollable)

**Changes**:
- Added BaseModal import and component registration
- Converted modal-overlay to BaseModal with large scrollable size
- StatusBadge integration for severity display maintained
- Alert list with v-for iteration preserved
- Empty state for when no alerts present

**CSS Removed**:
- .modal-overlay structure (~12 lines)
- .modal-content container with max dimensions (~10 lines)
- .modal-header structure (~8 lines)
- .modal-header h5 styling (~4 lines)
- .btn-close button (~8 lines)
- .modal-body scrollable container (~6 lines)
- Total: ~57 lines

**Patterns Preserved**:
- StatusBadge integration with getSeverityVariant() mapping
- Alert severity classes (critical, warning)
- Timestamp formatting via formatTimestamp()
- Alert structure (header with badge/category/timestamp + message + recommendation)
- Empty state with check icon when no alerts
- Scrollable content for potentially long alert lists

---

### **Batch 53 - KnowledgeEntries.vue Migration** ✅ Completed

**Goal**: Migrate large dual-mode knowledge entry modal to BaseModal.

**Component**: KnowledgeEntries.vue (1130 → 1068 lines, ~62 lines saved, 5.5% reduction)

**Modal Migrated**:
- **View/Edit Dialog** - Large scrollable modal with dual mode (view/edit) for knowledge entries

**Changes**:
- Added BaseModal import
- Converted dialog-overlay structure to BaseModal with large scrollable size
- Dynamic title based on dialogMode ('View Entry' vs 'Edit Entry')
- Conditional content rendering (view mode vs edit mode) in default slot
- Actions slot with mode-specific buttons (Edit in view, Cancel/Save in edit)

**CSS Removed**:
- .dialog-overlay fixed positioning and overlay (~18 lines)
- .dialog modal structure with max dimensions (~12 lines)
- .dialog.large size variant (~3 lines)
- .dialog-header with flex layout (~8 lines)
- .dialog-content padding wrapper (~4 lines)
- .dialog-actions footer with flex layout (~8 lines)
- Total: ~71 lines

**Patterns Preserved**:
- Entry metadata grid display with category badges
- Tags list with chip styling
- Content viewer with HTML rendering
- Edit form with category select, source input, tags input, content textarea
- Form validation and save/cancel actions
- Scrollable content for long knowledge entries

---

### **Batch 54 - RedisServiceControl.vue Migration** ✅ Completed

**Goal**: Migrate Redis service confirmation dialog to BaseModal.

**Component**: RedisServiceControl.vue (434 → 419 lines, ~15 lines saved, 3.5% reduction)

**Modal Migrated**:
- **Confirmation Dialog** - Medium modal for confirming service operations (restart/stop)

**Changes**:
- Added BaseModal import
- Converted fixed overlay structure to BaseModal with medium size
- Dynamic title from confirmDialog.title
- Message and warning sections in default slot
- Actions slot with Cancel and Confirm buttons
- Dynamic Confirm button variant (danger for stop, primary for restart)

**Template Simplified**:
- Removed fixed positioning overlay structure (~23 lines)
- Removed custom centering flex layout
- Removed custom modal card structure
- BaseModal handles all positioning and overlay

**Patterns Preserved**:
- Dynamic title based on operation type
- Message display with operation description
- Conditional warning section with yellow alert styling
- Dynamic button variants based on operation risk
- onConfirm callback pattern for action handling

---

### **Batch 55 - ChatMessages.vue Migration** ✅ Completed

**Goal**: Migrate chat message editing modal to BaseModal.

**Component**: ChatMessages.vue (1351 → 1351 lines, ~0 lines net, improved consistency)

**Modal Migrated**:
- **Edit Message Modal** - Medium modal for editing user messages in chat

**Changes**:
- Added BaseModal import
- Converted fixed overlay structure to BaseModal with medium size
- Textarea with keyboard shortcut support preserved
- Actions slot with Cancel and Save buttons
- Save button disabled validation maintained

**Template Simplified**:
- Removed fixed positioning overlay structure
- Removed custom centering flex layout
- Removed custom modal card structure
- BaseModal handles all positioning and overlay
- Note: Slight net increase due to BaseModal import + slot structure, but gained consistency and maintainability

**Patterns Preserved**:
- Textarea ref for focus management
- Keyboard shortcut handling (Ctrl+Enter / Cmd+Enter)
- Save button disabled when content empty (trim validation)
- Keyboard shortcut hint text below textarea
- Cancel/Save action pattern

---

### **Batch 56 - ChatSidebar.vue Migration** ✅ Completed

**Goal**: Migrate edit chat name modal to BaseModal.

**Component**: ChatSidebar.vue (428 → 431 lines, ~3 lines net increase, consistency gain)

**Modal Migrated**:
- **Edit Session Name Modal** - Simple text input modal for renaming chat sessions

**Changes**:
- Added BaseModal import
- Converted inline modal to BaseModal with medium size
- Input field with keyboard shortcuts preserved (Enter to save, Escape to cancel)
- Actions slot with Cancel and Save buttons
- Input ref maintained for focus management

**Template Simplified**:
- Removed fixed positioning overlay (~9 lines of template structure)
- Removed custom centering flex layout
- Removed custom modal card wrapper
- BaseModal handles all positioning and overlay
- Note: Slight net increase due to BaseModal import + slot structure, but gained consistency

**Patterns Preserved**:
- Input ref for focus management (editInput)
- Keyboard shortcut handlers (@keyup.enter, @keyup.escape)
- Save button triggers saveSessionName method
- Cancel button triggers cancelEdit method
- Inline Tailwind utility classes for input styling

---

### **Batch 57 - PhaseStatusIndicator.vue Migration** ✅ Completed

**Goal**: Migrate validation report modal to BaseModal.

**Component**: PhaseStatusIndicator.vue (653 → 595 lines, ~58 lines saved, 8.9% reduction)

**Modal Migrated**:
- **Validation Report Modal** - Large scrollable modal displaying validation report

**Changes**:
- Added BaseModal import and component registration
- Converted modal-overlay structure to BaseModal with large scrollable size
- Pre-formatted text display for validation report preserved
- No custom actions (uses default close button only)

**CSS Removed**:
- .modal-overlay fixed positioning and structure (~12 lines)
- .modal-content wrapper with max dimensions (~9 lines)
- .modal-header layout and styling (~7 lines)
- .modal-header h3 styling (~4 lines)
- .close-btn button styles (~8 lines)
- .close-btn:hover state (~3 lines)
- .modal-body scrollable container (~5 lines)
- Removed manual keyboard event handlers (@click.self, @keyup.enter, @keyup.space)
- Total: ~57 lines

**Patterns Preserved**:
- .validation-report styling (background, padding, font-family, monospace, etc.)
- Pre tag for formatted text display
- Large size for potentially long text content
- Scrollable content area

---

**BaseModal Migration Summary (Batches 47-57)**:
- **Components Migrated**: 11 components (TerminalModals, KnowledgeSearch, SecretsManager, NPUWorkersSettings, UserManagementSettings, MonitoringDashboard, KnowledgeEntries, RedisServiceControl, ChatMessages, ChatSidebar, PhaseStatusIndicator)
- **Modals Consolidated**: 19 modals total (4 terminal + 1 document + 3 secrets + 3 workers + 2 user mgmt + 1 monitoring + 1 knowledge + 1 service + 2 chat + 1 phase status)
- **Lines Saved**: ~642 lines total
  - Batches 47-49: ~301 lines (182 + 54 + 65)
  - Batches 50-52: ~213 lines (87 + 73 + 53)
  - Batches 53-55: ~73 lines (62 + 15 - 4)
  - Batches 56-57: ~55 lines (-3 + 58)
- **Target**: ~450-500 lines estimated → **642 lines achieved** ✅ **TARGET EXCEEDED (128%)**
- **Sizes Used**: All 3 sizes (small, medium, large)
- **Key Patterns**: v-model binding, size variants, scrollable modals, conditional closeOnOverlay, custom title slots, actions slot with custom buttons, form submissions in modals, StatusBadge integration, operation locking, loading states, dual-mode modals, confirmation dialogs, keyboard shortcuts, pre-formatted text display

---

## BasePanel Component Adoption (Batches 58-59)

### **Batch 58 - ValidationDashboard.vue Migration** ✅ Completed

**Goal**: Migrate validation dashboard stat cards and content sections to BasePanel.

**Component**: ValidationDashboard.vue (605 → 607 lines, CSS consolidation)

**Panels Migrated**:
1. **4 Stat Cards** - System overview metrics with elevated variant
   - System Maturity card (health-coded percentage)
   - Phases Completed card (progress fraction)
   - Active Capabilities card
   - System Health card (status text)
2. **5 Content Sections** - Main dashboard panels with bordered variant
   - Phase Progress section (phases list with completion bars)
   - System Alerts section (BaseAlert components integration)
   - Recommendations section (urgency badges)
   - Progression Status section (grid layout with metrics)
   - Phase Progression Indicator section (embedded component)

**Template Changes**:
- Replaced `.stat-card` divs with `BasePanel variant="elevated" size="small"`
- Replaced `.section` divs with `BasePanel variant="bordered" size="medium"`
- Moved h2/h3 titles to header slot
- Preserved all internal structure (metrics, alerts, recommendations, progress)

**CSS Removed (~15 lines)**:
- `.stat-card` panel structure (background, padding, border-radius, box-shadow) - 9 lines
- `.section` panel structure - 6 lines
- `.section h2, .section h3` styling - 4 lines (handled by BasePanel header slot)

**Key Features Preserved**:
- System maturity calculation and health color coding
- Phase progress tracking with status colors
- System alerts with BaseAlert integration
- Recommendations with urgency indicators
- Progression status metrics
- All responsive grid layouts

---

### **Batch 59 - VoiceInterface.vue Migration** ✅ Completed

**Goal**: Migrate voice interface configuration panels to BasePanel.

**Component**: VoiceInterface.vue (659 → 638 lines, ~21 lines saved, 3.2% reduction)

**Panels Migrated**:
1. **Voice Settings Panel** - Speech recognition configuration
   - Language selector (en-US, en-GB, es-ES, fr-FR, de-DE)
   - Voice speed slider (0.5x - 2x range)
   - Voice pitch slider (0.5x - 2x range)
   - Auto-listen checkbox
2. **Voice History Panel** - Recent voice commands display
   - Command timestamp
   - Transcribed text
   - Confidence percentage

**Template Changes**:
- Replaced `.voice-settings` div with `BasePanel variant="bordered" size="medium"`
- Replaced `.voice-history` div with `BasePanel variant="bordered" size="medium"`
- Moved h3 titles to header slot
- Preserved all form controls and history list structure

**CSS Removed (~21 lines total)**:
- `.voice-settings` panel structure - 7 lines
  - padding, background, border-radius, border, box-shadow
- `.voice-settings h3` title styling - 5 lines
- `.voice-history` panel structure - 7 lines
  - padding, background, border-radius, border, box-shadow
- `.voice-history h3` title styling - 5 lines

**Key Features Preserved**:
- Speech recognition language selection
- Voice speed and pitch controls (sliders)
- Auto-listen toggle functionality
- Voice command history with confidence scores
- Real-time voice visualization
- Voice status indicators (listening, processing, speaking)

---

**BasePanel Migration Summary (Batches 58-59)**:
- **Components Migrated**: 2 components
- **Panels Consolidated**: 11 panels (4 stat cards + 5 sections + 2 voice panels)
- **Lines Saved**: ~36 lines total
  - Batch 58: ~15 lines (CSS consolidation)
  - Batch 59: ~21 lines (CSS consolidation)
- **Variants Used**: elevated (stat cards), bordered (content sections)
- **Sizes Used**: small (stat cards), medium (content sections)
- **Key Patterns**: header slot for titles, default slot for content, BasePanel wrapping existing content structures

**BasePanel Adoption Findings**:
- ✅ **Successful for content panels**: Stat cards and section containers migrate cleanly
- ❌ **Not suitable for list items**: Components with `.workflow-card`, `.phase-card`, `.step-card` patterns are list items in grids/loops, not content panels
- ⚠️ **Large dashboards**: MonitoringDashboard (16 panels), CodebaseAnalytics (16 panels), SystemMonitor (12 panels) are high-value but complex
- 📋 **Estimated Remaining Opportunity**: ~150-250 lines across larger dashboard components

---

### **Batch 60 - MonitoringDashboard.vue Migration** ✅ Completed

**Goal**: Migrate performance monitoring dashboard metric cards, chart cards, and optimization section to BasePanel.

**Component**: MonitoringDashboard.vue (1333 → 1312 lines, ~21 lines saved, 1.6% reduction)

**Panels Migrated**:
1. **4 Metric Cards** - Performance overview cards with elevated variant (small size)
   - Overall Health card - System maturity score with health status
   - GPU card - NVIDIA RTX 4070 utilization, memory, temperature, power
   - NPU card - Intel NPU utilization, acceleration ratio, inferences
   - System card - 22-core CPU, memory, load average, network stats

2. **2 Chart Cards** - Timeline visualization cards with bordered variant (medium size)
   - GPU Utilization Chart - Time series with range selector (5/15/60 min)
   - System Performance Chart - Time series with range selector (5/15/60 min)

3. **1 Optimization Section** - Recommendations panel with bordered variant (medium size)
   - Performance Optimization Recommendations - Priority-coded suggestions with StatusBadge

**Template Changes**:
```vue
<!-- Before: Metric Card -->
<div class="metric-card overall-health">
  <div class="card-header">
    <h5><i class="fas fa-heartbeat"></i> Overall Health</h5>
  </div>
  <div class="card-body">
    <div :class="['health-score', overallHealth]">{{ overallHealthText }}</div>
    <div class="performance-score">Score: {{ performanceScore }}/100</div>
  </div>
</div>

<!-- After: BasePanel -->
<BasePanel variant="elevated" size="small">
  <template #header>
    <h5><i class="fas fa-heartbeat"></i> Overall Health</h5>
  </template>
  <div class="overall-health">
    <div :class="['health-score', overallHealth]">{{ overallHealthText }}</div>
    <div class="performance-score">Score: {{ performanceScore }}/100</div>
  </div>
</BasePanel>

<!-- Before: Chart Card -->
<div class="chart-card">
  <div class="chart-header">
    <h5>GPU Utilization Timeline</h5>
    <div class="chart-controls">
      <select v-model="gpuTimeRange">...</select>
    </div>
  </div>
  <div class="chart-container">...</div>
</div>

<!-- After: BasePanel with Header Wrapper -->
<BasePanel variant="bordered" size="medium">
  <template #header>
    <div class="chart-header-content">
      <h5>GPU Utilization Timeline</h5>
      <div class="chart-controls">
        <select v-model="gpuTimeRange">...</select>
      </div>
    </div>
  </template>
  <div class="chart-container">...</div>
</BasePanel>
```

**CSS Removed** (~60 lines):
- `.metric-card` structure (background, border-radius, box-shadow, height) - 7 lines
- `.metric-card .card-header` (background, padding, border) - 5 lines
- `.metric-card .card-header h5` (margin, color, font-size) - 5 lines
- `.metric-card .card-body` (padding, height, overflow) - 5 lines
- `.chart-card` structure (background, border-radius, box-shadow) - 6 lines
- `.chart-header` layout (flex, justify, align, padding, background, border) - 8 lines
- `.chart-header h5` (margin, color, font-size) - 5 lines
- `.optimization-section` structure (background, border-radius, box-shadow, margin) - 7 lines
- `.section-header` layout (flex, justify, align, padding, background, border) - 8 lines
- `.section-header h4` (margin, color, font-size) - 5 lines

**CSS Added** (~20 lines):
- `.chart-header-content` (flex layout for header slot with controls) - 9 lines
- `.section-header-content` (flex layout for header slot with actions) - 7 lines
- `.service-health .section-header` (scoped to non-migrated service-health section) - 4 lines

**Features Preserved**:
- Real-time WebSocket monitoring with connection status indicators
- GPU/NPU/System metrics with EmptyState fallbacks for unavailable hardware
- Chart.js timeline visualizations with time range selector controls
- StatusBadge integration for priority/severity indicators
- BaseButton integration for monitoring controls
- BaseAlert integration for critical alerts banner
- BaseModal integration for alerts detail modal
- Recommendations list with priority color coding (list items not migrated)
- Service health cards grid (list items not migrated)

**Key Pattern**: Header wrappers (`.chart-header-content`, `.section-header-content`) created to maintain flex layout for controls/actions in BasePanel header slot

---

### **Batch 61 - CodebaseAnalytics.vue Migration** ✅ Completed

**Goal**: Migrate real-time codebase analytics dashboard cards to BasePanel.

**Component**: CodebaseAnalytics.vue (1607 → 1576 lines, ~31 lines saved, 1.9% reduction)

**Panels Migrated**:
1. **4 Analytics Cards** - Enhanced metrics with bordered variant (medium size)
   - System Overview - API requests/min, response time, active connections, system health
   - Communication Patterns - WebSocket connections, API call frequency, data transfer rate
   - Code Quality - Overall score gauge, test coverage, code duplicates, technical debt
   - Performance Metrics - Efficiency gauge, memory usage, CPU usage, load time

2. **4 Stat Cards** - Codebase statistics with elevated variant (small size)
   - Total Files - File count metric
   - Lines of Code - Total lines metric
   - Functions - Function count metric
   - Classes - Class count metric

**Template Changes**:
```vue
<!-- Before: Analytics Card -->
<div class="analytics-card quality-card">
  <div class="card-header">
    <h3><i class="fas fa-code-branch"></i> Code Quality</h3>
    <button @click="loadCodeQuality" class="refresh-btn">
      <i class="fas fa-sync"></i>
    </button>
  </div>
  <div class="card-content">
    <div v-if="codeQuality" class="quality-metrics">...</div>
    <EmptyState v-else icon="fas fa-star" message="No quality metrics" />
  </div>
</div>

<!-- After: BasePanel with Header Wrapper -->
<BasePanel variant="bordered" size="medium">
  <template #header>
    <div class="card-header-content">
      <h3><i class="fas fa-code-branch"></i> Code Quality</h3>
      <button @click="loadCodeQuality" class="refresh-btn">
        <i class="fas fa-sync"></i>
      </button>
    </div>
  </template>
  <div v-if="codeQuality" class="quality-metrics">...</div>
  <EmptyState v-else icon="fas fa-star" message="No quality metrics" />
</BasePanel>

<!-- Before: Stat Card -->
<div class="stat-card">
  <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
  <div class="stat-label">Total Files</div>
</div>

<!-- After: BasePanel -->
<BasePanel variant="elevated" size="small">
  <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
  <div class="stat-label">Total Files</div>
</BasePanel>
```

**CSS Removed** (~52 lines):
- `.analytics-card` structure (background, border, border-radius, overflow, transition) - 7 lines
- `.analytics-card:hover` (transform, box-shadow, border-color) - 4 lines
- `.card-header` layout (background, padding, border, flex, justify, align) - 8 lines
- `.card-header h3` (margin, color, font-size, font-weight) - 6 lines
- `.card-content` (padding) - 3 lines
- `.stat-card` structure (background, padding, border-radius, text-align, border, transition) - 8 lines
- `.stat-card:hover` (border-color, transform) - 3 lines
- Plus hover states and spacing - 13 lines

**CSS Added** (~10 lines):
- `.card-header-content` (flex layout for header slot with controls) - 8 lines
- `.stat-value`, `.stat-label` (text-align: center) - 2 lines (added to existing styles)

**Features Preserved**:
- Real-time analytics with live/static indicator toggle
- EmptyState fallbacks for all 8 panels when data unavailable
- System health status with color-coded badges
- Quality score and efficiency gauges with dynamic classes
- Refresh controls per analytics card
- Statistics grid layout preserved
- All metric calculations and formatting intact
- Problems, duplicates, declarations sections NOT migrated (list items in v-for)

**Key Pattern**: Header wrapper (`.card-header-content`) created to maintain flex layout for titles + refresh buttons in BasePanel header slot

---

### **Batch 62 - SystemMonitor.vue Migration** ✅ Completed

**Goal**: Migrate real-time system monitoring dashboard glass-cards to BasePanel.

**Component**: SystemMonitor.vue (686 → 684 lines, ~2 lines saved, 0.3% reduction)

**Panels Migrated**:
1. **6 Glass Cards** - System monitoring panels with elevated variant (medium size)
   - Performance Metrics - CPU, Memory, GPU, NPU, Network usage bars with refresh indicator
   - Service Status - Online/offline service list with version info (v-for service-item)
   - Performance History - Canvas chart with timeframe selector buttons
   - API Health - Endpoint groups with response times (v-for endpoint-item)
   - Quick Actions - Router links for chat, upload, terminal, logs
   - Recent Activity - Activity feed with icons and timestamps (v-for activity-item)

**Template Changes**:
```vue
<!-- Before: Glass Card -->
<div class="metric-card glass-card">
  <div class="card-header">
    <h3>System Performance</h3>
    <div class="refresh-indicator" :class="{ spinning: isRefreshing }">⟳</div>
  </div>
  <div class="metric-content">
    <div class="metric-item">...</div>
  </div>
</div>

<!-- After: BasePanel with Header Wrapper -->
<BasePanel variant="elevated" size="medium">
  <template #header>
    <div class="card-header-content">
      <h3>System Performance</h3>
      <div class="refresh-indicator" :class="{ spinning: isRefreshing }">⟳</div>
    </div>
  </template>
  <div class="metric-content">
    <div class="metric-item">...</div>
  </div>
</BasePanel>
```

**CSS Removed** (~21 lines):
- `.glass-card` structure (background, border, border-radius, padding, backdrop-filter, box-shadow) - 8 lines
- `.card-header` layout (display, justify, align, margin, padding, border) - 8 lines
- `.card-header h3` (font-size, font-weight, color) - 5 lines

**CSS Added** (~9 lines):
- `.card-header-content` (flex layout for header slot with controls/stats) - 7 lines
- `.card-header-content h3` (font-size, font-weight, color) - 2 lines

**Features Preserved**:
- Glass morphism visual style (backdrop-filter blur) now via BasePanel elevated variant
- Real-time refresh indicator with spinning animation (@keyframes spin)
- Service status badges with online/offline states
- Chart.js canvas integration with timeframe control buttons
- API endpoint grouping with health status color coding
- Router-link quick actions grid layout
- Activity feed with icon + timestamp structure
- All v-for list items preserved (service-item, endpoint-item, activity-item)

**Key Pattern**: Header wrapper (`.card-header-content`) created for cards with controls/stats in header slot (refresh indicator, status summary, API stats, timeframe buttons)

---

### **Batch 63 - KnowledgeStats.vue Migration** ✅ Completed

**Goal**: Migrate comprehensive knowledge base statistics dashboard with vector DB stats, overview cards, charts, and sections to BasePanel.

**Component**: KnowledgeStats.vue (1632 → 1578 lines, ~54 lines saved, 3.3% reduction)

**Panels Migrated (14 total)**:

1-4. **Vector Stat Cards** (4 cards) → BasePanel `variant="elevated" size="medium"` (glass morphism):
```vue
<!-- Before: vector-stat-card with glass morphism -->
<div class="vector-stat-card">
  <div class="vector-stat-icon facts">
    <i class="fas fa-lightbulb"></i>
  </div>
  <div class="vector-stat-content">
    <h4>Total Facts</h4>
    <p class="vector-stat-value">{{ vectorStats.total_facts || 0 }}</p>
    <p class="vector-stat-label">Knowledge items stored</p>
  </div>
</div>

<!-- After: BasePanel elevated (handles glass morphism) -->
<BasePanel variant="elevated" size="medium">
  <div class="vector-stat-icon facts">
    <i class="fas fa-lightbulb"></i>
  </div>
  <div class="vector-stat-content">
    <h4>Total Facts</h4>
    <p class="vector-stat-value">{{ vectorStats.total_facts || 0 }}</p>
    <p class="vector-stat-label">Knowledge items stored</p>
  </div>
</BasePanel>
```

5-9. **Overview Stat Cards** (5 cards) → BasePanel `variant="elevated" size="small"`:
```vue
<!-- Before: stat-card structure -->
<div class="stat-card" role="article" aria-labelledby="facts-title">
  <div class="stat-icon facts" aria-hidden="true">
    <i class="fas fa-lightbulb"></i>
  </div>
  <div class="stat-content">
    <h4 id="facts-title">Total Facts</h4>
    <p class="stat-value" aria-live="polite">{{ vectorStats?.total_facts || 0 }}</p>
    <p class="stat-change" aria-label="Knowledge items stored in Redis database">
      Knowledge items in Redis
    </p>
  </div>
</div>

<!-- After: BasePanel small with preserved accessibility -->
<BasePanel variant="elevated" size="small" role="article" aria-labelledby="facts-title">
  <div class="stat-icon facts" aria-hidden="true">
    <i class="fas fa-lightbulb"></i>
  </div>
  <div class="stat-content">
    <h4 id="facts-title">Total Facts</h4>
    <p class="stat-value" aria-live="polite">{{ vectorStats?.total_facts || 0 }}</p>
    <p class="stat-change" aria-label="Knowledge items stored in Redis database">
      Knowledge items in Redis
    </p>
  </div>
</BasePanel>
```

10-11. **Chart Containers** (2 charts) → BasePanel `variant="bordered" size="medium"`:
```vue
<!-- Before: chart-container -->
<div class="chart-container">
  <h4>Documents by Category</h4>
  <div class="bar-chart">
    <!-- chart content -->
  </div>
</div>

<!-- After: BasePanel bordered -->
<BasePanel variant="bordered" size="medium">
  <h4>Documents by Category</h4>
  <div class="bar-chart">
    <!-- chart content -->
  </div>
</BasePanel>
```

12-14. **Section Containers** (3 sections) → BasePanel `variant="bordered" size="medium"`:
- Activity Section (recent activity timeline)
- Tag Cloud Section (popular tags with dynamic sizing)
- Man Pages Section (ManPageManager component wrapper)

**CSS Removed** (~60 lines):
```css
/* Removed duplicate card structures: */
.stat-card { background: white; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1.5rem; display: flex; gap: 1rem; }  /* 8 lines */
.vector-stat-card { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.2); border-radius: 0.75rem; padding: 1.5rem; display: flex; align-items: center; gap: 1rem; transition: all 0.3s ease; }  /* 17 lines */
.chart-container { background: white; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1.5rem; }  /* 12 lines */
.activity-section { background: white; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1.5rem; margin-bottom: 2rem; }  /* 8 lines */
.tag-cloud-section { background: white; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1.5rem; margin-bottom: 2rem; }  /* 8 lines */
.manpages-section { background: white; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1.5rem; margin-bottom: 2rem; }  /* 7 lines */
```

**Key Features Preserved**:
- Conditional styling preserved (`:class="{ 'needs-attention': needsVectorization }"`)
- Component integration maintained (StatusBadge, EmptyState, ManPageManager)
- ARIA labels and accessibility attributes (role, aria-labelledby, aria-live, aria-label)
- Vector database statistics with gradient purple background wrapper
- Glass morphism visual style via BasePanel elevated variant
- Bar chart and pie chart with type stats integration
- Tag cloud with dynamic font sizing (`:style="{ fontSize: \`\${tag.size}rem\` }"`)
- Activity timeline with activity type icons (created, updated, deleted)
- All v-for list items preserved (type-item, category-bar, activity-item, health-item, detail-item)

**Key Patterns**:
- Glass morphism cards use BasePanel elevated variant (handles backdrop-filter automatically)
- Overview metrics use small elevated panels
- Charts and content sections use medium bordered panels
- Accessibility attributes (role, aria-*) passed directly to BasePanel
- Conditional classes preserved for dynamic styling needs

---

### **Batch 64 - MCPDashboard.vue Migration** ✅ Completed

**Goal**: Migrate system health monitoring dashboard with health cards and status sections to BasePanel.

**Component**: MCPDashboard.vue (574 → 544 lines, ~30 lines saved, 5.2% reduction)

**Panels Migrated (6 total)**:

1-4. **Health Cards** (4 cards) → BasePanel `variant="elevated" size="medium"`:
```vue
<!-- Before: health-card with conditional styling -->
<div class="health-card" :class="getHealthClass(health.frontend)">
  <div class="card-header">
    <i class="fas fa-desktop"></i>
    <h3>Frontend</h3>
    <span class="status-icon">
      <i :class="getStatusIcon(health.frontend.status)"></i>
    </span>
  </div>
  <div class="card-body">
    <div class="metric">
      <span class="label">Console Errors:</span>
      <span class="value" :class="{ 'text-danger': health.frontend.errorCount > 0 }">
        {{ health.frontend.errorCount }}
      </span>
    </div>
  </div>
</div>

<!-- After: BasePanel elevated with header slot -->
<BasePanel variant="elevated" size="medium" :class="getHealthClass(health.frontend)">
  <template #header>
    <i class="fas fa-desktop"></i>
    <h3>Frontend</h3>
    <span class="status-icon">
      <i :class="getStatusIcon(health.frontend.status)"></i>
    </span>
  </template>
  <div class="card-body">
    <div class="metric">
      <span class="label">Console Errors:</span>
      <span class="value" :class="{ 'text-danger': health.frontend.errorCount > 0 }">
        {{ health.frontend.errorCount }}
      </span>
    </div>
  </div>
</BasePanel>
```

5-6. **Status Sections** (2 sections) → BasePanel `variant="bordered" size="medium"`:
```vue
<!-- Before: activity-section -->
<div class="activity-section">
  <h3><i class="fas fa-history"></i> Recent Activity</h3>
  <div class="activity-log">
    <!-- log entries -->
  </div>
</div>

<!-- After: BasePanel bordered with header slot -->
<BasePanel variant="bordered" size="medium">
  <template #header>
    <h3><i class="fas fa-history"></i> Recent Activity</h3>
  </template>
  <div class="activity-log">
    <!-- log entries -->
  </div>
</BasePanel>
```

**CSS Removed** (~30 lines):
```css
/* Removed duplicate card structures: */
.health-card { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 0; overflow: hidden; transition: transform 0.2s, box-shadow 0.2s; }
.health-card:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
.card-header { padding: 15px 20px; background: #f8f9fa; border-bottom: 1px solid #e9ecef; display: flex; align-items: center; gap: 10px; }
.card-header h3 { margin: 0; font-size: 18px; flex: 1; }
.activity-section, .mcp-tools-section { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 20px; }
/* Kept conditional health state border classes (.health-good, .health-warning, .health-error, .health-unknown) */
```

**Key Features Preserved**:
- Conditional health state styling (health-good/warning/error/unknown classes with colored borders)
- Status icon positioning with margin-left: auto
- Health metrics with conditional danger highlighting
- Activity log entries with log level styling (log-error, log-warning, log-success)
- MCP tools grid with active/inactive states
- Card hover effects handled by BasePanel
- All header icons and titles preserved

**Key Patterns**:
- Health cards use elevated variant for prominence with shadow effects
- Status sections use bordered variant for clean separation
- Header slot used for titles with icons
- Conditional classes preserved for dynamic health states
- BasePanel handles hover transitions automatically

---

### **Batch 65 - SystemKnowledgeManager.vue Migration** ✅ Completed

**Goal**: Migrate knowledge base management component panels to BasePanel.

**Component**: SystemKnowledgeManager.vue (1013 → 1011 lines, ~2 lines saved, 0.2% reduction)

**Panels Migrated (5 total)**:

1-4. **Status Cards** (4 cards) → BasePanel `variant="elevated" size="small"`:
```vue
<!-- Before: status-card with icon and content -->
<div class="status-card">
  <div class="status-icon">📚</div>
  <div class="status-content">
    <h3>{{ stats.total_facts || 0 }}</h3>
    <p>Total Facts</p>
  </div>
</div>

<!-- After: BasePanel elevated with status-card-content wrapper -->
<BasePanel variant="elevated" size="small">
  <div class="status-card-content">
    <div class="status-icon">📚</div>
    <div class="status-content">
      <h3>{{ stats.total_facts || 0 }}</h3>
      <p>Total Facts</p>
    </div>
  </div>
</BasePanel>
```

5. **Info Section** → BasePanel `variant="bordered" size="medium"`:
```vue
<!-- Before: info-section with title and content -->
<div class="info-section">
  <h3>ℹ️ About System Knowledge</h3>
  <div class="info-content">
    <p><strong>Initialize Machine Knowledge:</strong> Creates vector embeddings...</p>
    <!-- more info paragraphs -->
  </div>
</div>

<!-- After: BasePanel bordered with header slot -->
<BasePanel variant="bordered" size="medium">
  <template #header>
    <h3>ℹ️ About System Knowledge</h3>
  </template>
  <div class="info-content">
    <p><strong>Initialize Machine Knowledge:</strong> Creates vector embeddings...</p>
    <!-- more info paragraphs -->
  </div>
</BasePanel>
```

**CSS Removed** (~16 lines):
```css
/* Removed duplicate card/section structures: */
.status-card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; align-items: center; gap: 15px; }
.info-section { background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 30px; }
.info-section h3 { margin: 0 0 15px 0; color: #2c3e50; }

/* Kept content-level styles: */
.status-card-content { display: flex; align-items: center; gap: 15px; }
.status-icon { font-size: 32px; }
.status-content h3/p { /* styling preserved */ }
.info-content p { margin: 10px 0; line-height: 1.6; color: #555; }
```

**Key Features Preserved**:
- Status card icon and content layout (status-icon + status-content)
- Stats bindings (stats.total_facts, stats.total_vectors, commandsIndexed, docsIndexed)
- Info section header moved to BasePanel header slot
- Info content paragraphs with usage instructions for all operations (Initialize, Reindex, Refresh Man Pages, Populate Commands, Index Docs)
- All styling and spacing maintained

**Key Patterns**:
- Status cards use elevated variant small for compact metric display
- Info section uses bordered variant medium for documentation content
- Header slot used for info section title with emoji
- Status cards wrap content in status-card-content div for internal layout
- BasePanel handles container styling, content classes remain for internal structure

---

### **Batch 66 - MCPDashboard.vue BaseButton Migration** ✅ Completed

**Goal**: Migrate refresh button to BaseButton for consistent styling and behavior (returning to BaseButton migrations).

**Component**: MCPDashboard.vue (545 → 528 lines, ~17 lines saved, 3.1% reduction)

**Button Migrated (1 total)**:

1. **Refresh Button** → BaseButton `variant="primary"` with loading state:
```vue
<!-- Before: custom button with manual loading handling -->
<button @click="refreshData" :disabled="loading" class="btn-refresh">
  <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
  Refresh
</button>

<!-- After: BaseButton with built-in loading -->
<BaseButton
  @click="refreshData"
  :disabled="loading"
  variant="primary"
  :loading="loading"
  icon="fas fa-sync-alt"
>
  Refresh
</BaseButton>
```

**CSS Removed** (~20 lines):
```css
/* Removed manual button styling: */
.btn-refresh { padding: 8px 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: background 0.3s; }
.btn-refresh:hover:not(:disabled) { background: #0056b3; }
.btn-refresh:disabled { opacity: 0.6; cursor: not-allowed; }
```

**Key Features Preserved**:
- Loading state with spinning icon (BaseButton `:loading` prop handles icon animation)
- Disabled state during refresh operation
- Click handler for refreshData method
- Primary blue styling via variant="primary"
- Icon positioning and display

**Key Patterns**:
- BaseButton :loading prop replaces manual :class="{ 'fa-spin': loading }"
- Icon specified via icon prop instead of template <i> element
- Variant primary provides blue background matching previous .btn-refresh
- All hover, active, and disabled states handled by BaseButton
- Consistent with 29 other components using BaseButton

**Note**: This batch returns to BaseButton migrations after completing BasePanel work (Batches 58-65). MCPDashboard.vue was migrated to BasePanel in Batch 64, but its button was not migrated at that time.

---

### **Batch 67 - ConnectionStatus.vue BaseButton Migration** ✅ Completed

**Goal**: Migrate connection status monitoring buttons to BaseButton for consistency and centralized behavior.

**Component**: ConnectionStatus.vue (390 → 405 lines, +15 lines - consistency gain, 3.8% increase)

**Buttons Migrated (4 total)**:

1. **Toggle Details Button** → BaseButton `variant="ghost" size="sm"`:
```vue
<!-- Before: custom button with SVG chevron -->
<button
  @click="toggleDetails"
  class="text-gray-400 hover:text-gray-600 ml-2"
  :aria-expanded="showDetails"
  aria-label="Toggle connection details"
>
  <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showDetails }">
    <!-- chevron path -->
  </svg>
</button>

<!-- After: BaseButton ghost with SVG in slot -->
<BaseButton
  @click="toggleDetails"
  variant="ghost"
  size="sm"
  :aria-expanded="showDetails"
  aria-label="Toggle connection details"
  class="ml-2 text-gray-400 hover:text-gray-600"
>
  <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showDetails }">
    <!-- chevron path -->
  </svg>
</BaseButton>
```

2-3. **Action Buttons** (Force Reconnect, Health Check) → BaseButton `variant="link" size="xs"`:
```vue
<!-- Before: custom text buttons with manual loading text -->
<button
  @click="forceReconnect"
  class="text-blue-600 hover:text-blue-800 text-xs"
  :disabled="reconnecting"
>
  {{ reconnecting ? 'Reconnecting...' : 'Force Reconnect' }}
</button>

<!-- After: BaseButton link with :loading prop -->
<BaseButton
  @click="forceReconnect"
  variant="link"
  size="xs"
  :loading="reconnecting"
  :disabled="reconnecting"
  class="text-blue-600 hover:text-blue-800"
>
  {{ reconnecting ? 'Reconnecting...' : 'Force Reconnect' }}
</BaseButton>
```

4. **Close Toast Button** → BaseButton `variant="ghost" size="sm"`:
```vue
<!-- Before: custom button with X icon -->
<button
  @click="removeToast(toast.id)"
  class="ml-2 text-gray-400 hover:text-gray-600"
>
  <svg class="w-4 h-4"><!-- X icon path --></svg>
</button>

<!-- After: BaseButton ghost with accessibility -->
<BaseButton
  @click="removeToast(toast.id)"
  variant="ghost"
  size="sm"
  class="ml-2 text-gray-400 hover:text-gray-600"
  aria-label="Close notification"
>
  <svg class="w-4 h-4"><!-- X icon path --></svg>
</BaseButton>
```

**Key Features Preserved**:
- Toggle details with animated chevron rotation (:class="{ 'rotate-180': showDetails }")
- Loading states for reconnect and health check (BaseButton :loading prop)
- Toast notification close functionality with icon
- All Tailwind utility classes for positioning (ml-2) and colors (text-blue-600, hover:text-blue-800)
- Accessibility attributes (aria-expanded, aria-label added for close button)
- Button disabled states during operations

**Key Patterns**:
- Ghost variant for icon-only buttons (toggle, close)
- Link variant for text action buttons (reconnect, health check)
- Size xs for compact action buttons, sm for icon buttons
- SVG icons passed in default slot
- Tailwind classes preserved on BaseButton for custom colors
- BaseButton :loading handles loading states instead of manual text changes
- Accessibility improvements (added aria-label to close button)

**Note**: File increased by 15 lines due to BaseButton's more explicit prop syntax (multi-line prop declarations for readability), but gains consistency with 30 other components and centralized button behavior. This is a consistency gain migration rather than lines saved.

---

**BasePanel Migration Summary (Batches 58-65)**:
- **Components Migrated**: 8 components (ValidationDashboard, VoiceInterface, MonitoringDashboard, CodebaseAnalytics, SystemMonitor, KnowledgeStats, MCPDashboard, SystemKnowledgeManager)
- **Panels Consolidated**: 57 panels (13 stat cards + 10 sections + 2 voice panels + 4 metric cards + 4 chart cards + 1 optimization section + 4 analytics cards + 6 glass cards + 4 vector stat cards + 4 health cards + 4 status cards + 1 info section)
- **Lines Saved**: ~176 lines total
  - Batch 58: ~0 lines (CSS consolidation, template overhead offset)
  - Batch 59: ~36 lines (CSS consolidation)
  - Batch 60: ~21 lines (CSS consolidation)
  - Batch 61: ~31 lines (CSS consolidation)
  - Batch 62: ~2 lines (CSS consolidation)
  - Batch 63: ~54 lines (CSS consolidation)
  - Batch 64: ~30 lines (CSS consolidation)
  - Batch 65: ~2 lines (CSS consolidation)
- **Variants Used**: elevated (metric/stat/glass/vector/health/status cards), bordered (sections/charts/optimization/analytics/activity/tag-cloud/manpages/status/info)
- **Sizes Used**: small (metric/stat/status cards), medium (sections/charts/optimization/analytics/glass cards/vector cards/health cards/info section)
- **Key Patterns**: header slot for titles, header wrappers for controls, default slot for content, accessibility attributes preservation, conditional styling preservation

---

**Migration Status Update**:
- EmptyState migrations: ~579 lines (38.6% of realistic target)
- Utility consolidation: ~18 lines (batch 14)
- StatusBadge adoptions: ~197 lines (batches 15-19)
  - Batch 15: ~14 lines (3 components)
  - Batch 16: ~49 lines (2 components)
  - Batch 17: ~15 lines (1 component, 2 patterns)
  - Batch 18: ~90 lines (4 components, 5 patterns)
  - Batch 19: ~29 lines (1 component - final sweep)
- BaseButton adoptions: ~1,834 lines saved, -15 lines consistency gain (batches 20-40, 66-67)
  - Batch 20: ~157 lines (3 components, 10 buttons)
  - Batch 21: ~87 lines (2 components, 11 buttons)
  - Batch 22: ~187 lines (2 components, 7 buttons)
  - Batch 23: ~96 lines (2 components, 12 buttons)
  - Batch 24: ~39 lines (1 component, 16 buttons)
  - Batch 25: ~114 lines (2 components, 19 buttons)
  - Batch 26: ~129 lines (3 components, 19 buttons)
  - Batch 27: ~170 lines (1 component, 17 buttons)
  - Batch 28: ~65 lines (1 component, 10 buttons)
  - Batch 29: ~156 lines (1 component, 9 buttons)
  - Batch 30: ~61 lines (1 component, 5 buttons)
  - Batch 31: ~58 lines (1 component, 4 buttons)
  - Batch 32: ~24 lines (1 component, 4 buttons)
  - Batch 33: ~19 lines (1 component, 3 buttons)
  - Batch 34: ~50 lines (1 component, 3 buttons)
  - Batch 35: ~60 lines (1 component, 10 buttons)
  - Batch 36: ~90 lines (1 component, 15 buttons)
  - Batch 37: ~65 lines (1 component, 8 buttons)
  - Batch 38: ~85 lines (1 component, 9 buttons)
  - Batch 39: ~70 lines (1 component, 6 buttons)
  - Batch 40: ~35 lines (1 component, 5 buttons)
  - Batch 66: ~17 lines (1 component, 1 button)
  - Batch 67: -15 lines (1 component, 4 buttons - consistency gain)
- BaseAlert adoptions: ~121 lines (batches 41-46)
  - Batch 41: ~22 lines (1 component, 2 alerts) + BaseAlert.vue creation
  - Batch 42: ~18 lines (1 component, 2 alerts)
  - Batch 43: ~14 lines (1 component, 1 alert)
  - Batch 44: ~40 lines (1 component, alerts list with v-for)
  - Batch 45: ~17 lines (1 component, 1 banner)
  - Batch 46: ~10 lines (1 component, 1 alert)
- BaseModal adoptions: ~642 lines (batches 47-57)
  - Batch 47: ~182 lines (1 component, 4 modals)
  - Batch 48: ~54 lines (1 component, 1 modal)
  - Batch 49: ~65 lines (1 component, 3 modals)
  - Batch 50: ~87 lines (1 component, 3 modals)
  - Batch 51: ~73 lines (1 component, 2 modals)
  - Batch 52: ~53 lines (1 component, 1 modal)
  - Batch 53: ~62 lines (1 component, 1 modal)
  - Batch 54: ~15 lines (1 component, 1 modal)
  - Batch 55: ~0 lines (1 component, 1 modal - consistency gain)
  - Batch 56: ~-3 lines (1 component, 1 modal - consistency gain)
  - Batch 57: ~58 lines (1 component, 1 modal)
- BasePanel adoptions: ~176 lines (batches 58-65)
  - Batch 58: ~0 lines (1 component, 9 panels - consistency gain, CSS consolidation)
  - Batch 59: ~36 lines (1 component, 2 panels)
  - Batch 60: ~21 lines (1 component, 7 panels)
  - Batch 61: ~31 lines (1 component, 8 panels)
  - Batch 62: ~2 lines (1 component, 6 panels)
  - Batch 63: ~54 lines (1 component, 14 panels)
  - Batch 64: ~30 lines (1 component, 6 panels)
  - Batch 65: ~2 lines (1 component, 5 panels)
  - Batch 66: ~17 lines (1 component, 1 button - return to BaseButton migrations)
  - Batch 67: -15 lines (1 component, 4 buttons - consistency gain)
- **Total Progress**: ~3,552 lines / ~1,500-2,000 realistic target (178-237%) ✅ **TARGET EXCEEDED**
- **StatusBadge Milestone**: 15 instances across 11 components (650% increase from 2 baseline)
- **BaseButton Milestone**: 31 components using BaseButton (207 buttons consolidated)
- **BaseAlert Milestone**: 6 components using BaseAlert (10+ alerts consolidated)
- **BaseModal Milestone**: 16 components using BaseModal (2 baseline + 14 new, 19 modals consolidated)
- **BasePanel Milestone**: 8 components using BasePanel (0 baseline + 8 new, 57 panels consolidated)

**📊 Final Assessment: Underutilized Reusable Components** (January 2025):

During batch 14 final sweep, discovered several well-designed reusable components that exist but are **significantly underutilized**:

**1. BaseButton.vue** (`autobot-user-frontend/src/components/base/`)
- **Current Usage**: ✅ **MIGRATION ONGOING** - 31 components using BaseButton (batches 20-40, 66-67+)
  - First batches (20-24): ErrorBoundary, AsyncErrorFallback, PhaseStatusIndicator, dialogs, settings, research browser
  - Middle batches (25-40): Terminal, chat, knowledge, monitoring, phase progression
  - Return to BaseButton (Batch 66-67): MCPDashboard refresh button, ConnectionStatus (toggle, actions, close)
- **Features**: 11 variants (primary/secondary/success/danger/warning/info/light/dark/outline/ghost/link), 5 sizes (xs-xl), loading states, icon support, flexible rendering (button/link/custom tag), **✅ Optional touch optimization** (ripple effects, haptic feedback, 44px touch targets)
- **Status**: ✅ **CONTINUED ADOPTION** - 31 components, 207 buttons consolidated
- **Results**: ~1,819 lines saved (1,834 saved - 15 consistency gain) across 42 batches, 207 buttons consolidated across 31 components
- **Touch Integration**: ✅ **COMPLETED** - Extended with optional touchOptimized, touchFeedback, hapticFeedback props (backward compatible)
- **Achievement**: Successfully established BaseButton as the standard button pattern across entire frontend codebase
- **Remaining**: ~12 more buttons identified across 3 components (ErrorNotifications: 3, HistoryView: 3, LogViewer: 5, plus misc)

**2. TouchFriendlyButton.vue** (`autobot-user-frontend/src/components/ui/`)
- **Current Usage**: 0 components (no imports found)
- **Features**: Size variants (xs-xl), style variants (primary/secondary/outline/ghost/danger), loading states, touch feedback, haptic feedback, accessibility (dark mode, high contrast, reduced motion)
- **Status**: ✅ **OVERLAP RESOLVED** - All touch features integrated into BaseButton
- **Recommendation**: ⚠️ **Deprecation candidate** - Features now available in BaseButton via touchOptimized prop
- **Alternative**: Convert to lightweight wrapper around `<BaseButton touchOptimized>` for backward compatibility
- **Analysis**: BaseButton now has all TouchFriendlyButton features (11 variants + touch optimization) making this component redundant

**3. StatusBadge.vue** (`autobot-user-frontend/src/components/ui/`)
- **Current Usage**: ✅ **SUBSTANTIALLY COMPLETE** - 15 instances across 11 components (batches 15-19 migrations)
  - Original: VectorizationProgressModal, TreeNodeComponent
  - Batches 15-19: KnowledgePersistenceDialog, HostsManager, ResearchBrowser, MonitoringDashboard, SecretsManager, CommandPermissionDialog, ElevationDialog, KnowledgeStats, NPUWorkersSettings
- **Features**: Variant styles (success/danger/warning/info/primary/secondary), sizes (small/medium/large), icon support, dark mode
- **Recommendation**: ✅ **Enforcement complete** - Law of diminishing returns reached
- **Results**: ~197 lines saved (batches 15-19), 650% usage increase (2 → 15 instances)
- **Achievement**: Successfully established as standard badge pattern across diverse contexts

**3. useToast Composable** (`autobot-user-frontend/src/composables/useToast.js`)
- **Current Usage**: 2 components (KnowledgePersistenceDialog + examples)
- **Features**: Global toast state, type variants (info/success/warning/error), auto-dismiss, toast management
- **Recommendation**: ✅ **Good pattern but needs Toast UI component** - Many components implement inline alert/notification patterns
- **Estimated Potential**: ~50-150 lines if adopted for user feedback patterns

**Analysis**:
These components represent **prior investment in reusability infrastructure** that hasn't been fully leveraged. The challenge isn't creating new patterns - it's **adopting existing ones**.

**Why Low Adoption?**:
1. **Lack of awareness**: Developers may not know these components exist
2. **Migration friction**: Easier to copy existing inline patterns than refactor to use shared components
3. **Time constraints**: Quick inline solutions prioritized over proper architecture
4. **Missing documentation**: Components need usage examples and migration guides

**Recommended Path Forward**:
1. ✅ **Document existing components** in this guide with clear usage examples
2. ✅ **Create migration guides** showing before/after conversions
3. ⚠️ **Establish component adoption policy** - require use of shared components in new code
4. 📋 **Gradual migration** - target high-value files first (forms, modals, status displays)

**Revised Opportunity Assessment**:
- Direct code savings from existing patterns: ~200-400 lines (batch 14 baseline)
- **Additional savings from adopting existing components: ~200-450 lines**
- **Combined potential: ~400-850 lines** (aggressive adoption scenario)

### **Phase 3** (Recommended 📅):

**Priority 1: Leverage Existing Components** (High ROI)
- 📋 Adopt TouchFriendlyButton.vue in forms and modals (~100-200 lines)
- 📋 Adopt StatusBadge.vue for status indicators (~50-100 lines)
- 📋 Create Toast UI component to pair with useToast composable
- 📋 Document component usage patterns and migration examples

**Priority 2: New Presentational Components** (Medium ROI)
- 📋 Create FormInput reusable component (if truly generic pattern found)
- 📋 Create Card/Panel variants (evaluate against batch 13 contextual variation principle)

**Priority 3: Enforcement & Culture**
- 📋 Add pre-commit checks for inline patterns that should use shared components
- 📋 Update component contribution guidelines
- 📋 Create "component showcase" documentation

---

## 📚 Migration Examples

### Example 1: Using TouchFriendlyButton Component

**Location**: `autobot-user-frontend/src/components/ui/TouchFriendlyButton.vue`

**Before** (Inline button with custom styling):
```vue
<template>
  <button
    @click="handleSubmit"
    :disabled="isSubmitting"
    class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
  >
    {{ isSubmitting ? 'Saving...' : 'Save Changes' }}
  </button>
</template>
```

**After** (Using TouchFriendlyButton):
```vue
<script setup>
import TouchFriendlyButton from '@/components/ui/TouchFriendlyButton.vue'
</script>

<template>
  <TouchFriendlyButton
    variant="primary"
    size="md"
    :loading="isSubmitting"
    @click="handleSubmit"
  >
    Save Changes
  </TouchFriendlyButton>
</template>
```

**Benefits**:
- ✅ Touch feedback with ripple effect
- ✅ Haptic feedback on mobile
- ✅ Loading state with spinner
- ✅ Accessibility (dark mode, reduced motion)
- ✅ Consistent sizing (minimum 44px touch target)

**All Variants**:
```vue
<!-- Size variants -->
<TouchFriendlyButton size="xs">Extra Small</TouchFriendlyButton>
<TouchFriendlyButton size="sm">Small</TouchFriendlyButton>
<TouchFriendlyButton size="md">Medium</TouchFriendlyButton>
<TouchFriendlyButton size="lg">Large</TouchFriendlyButton>
<TouchFriendlyButton size="xl">Extra Large</TouchFriendlyButton>

<!-- Style variants -->
<TouchFriendlyButton variant="primary">Primary</TouchFriendlyButton>
<TouchFriendlyButton variant="secondary">Secondary</TouchFriendlyButton>
<TouchFriendlyButton variant="outline">Outline</TouchFriendlyButton>
<TouchFriendlyButton variant="ghost">Ghost</TouchFriendlyButton>
<TouchFriendlyButton variant="danger">Danger</TouchFriendlyButton>

<!-- With icon and loading -->
<TouchFriendlyButton :loading="true">
  <template #icon>
    <i class="fas fa-save"></i>
  </template>
  Save
</TouchFriendlyButton>
```

---

### Example 2: Using StatusBadge Component

**Location**: `autobot-user-frontend/src/components/ui/StatusBadge.vue`

**Before** (Inline badge):
```vue
<template>
  <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
    <i class="fas fa-check-circle mr-1"></i>
    Active
  </span>
</template>
```

**After** (Using StatusBadge):
```vue
<script setup>
import StatusBadge from '@/components/ui/StatusBadge.vue'
</script>

<template>
  <StatusBadge variant="success" icon="fas fa-check-circle">
    Active
  </StatusBadge>
</template>
```

**Benefits**:
- ✅ Consistent status colors across application
- ✅ Dark mode support
- ✅ Size variants (small/medium/large)
- ✅ Optional icon integration

**All Variants**:
```vue
<!-- Variant styles -->
<StatusBadge variant="success">Success</StatusBadge>
<StatusBadge variant="danger">Danger</StatusBadge>
<StatusBadge variant="warning">Warning</StatusBadge>
<StatusBadge variant="info">Info</StatusBadge>
<StatusBadge variant="primary">Primary</StatusBadge>
<StatusBadge variant="secondary">Secondary</StatusBadge>

<!-- Sizes -->
<StatusBadge size="small" variant="success">Small</StatusBadge>
<StatusBadge size="medium" variant="success">Medium</StatusBadge>
<StatusBadge size="large" variant="success">Large</StatusBadge>

<!-- With icons -->
<StatusBadge variant="success" icon="fas fa-check-circle">Active</StatusBadge>
<StatusBadge variant="danger" icon="fas fa-times-circle">Failed</StatusBadge>
<StatusBadge variant="warning" icon="fas fa-exclamation-triangle">Pending</StatusBadge>
```

---

### Example 3: Using useToast Composable

**Location**: `autobot-user-frontend/src/composables/useToast.js`

**Before** (Inline alert/notification):
```vue
<template>
  <div v-if="showSuccess" class="fixed top-4 right-4 bg-green-50 border border-green-200 rounded-lg p-4">
    <p class="text-green-800">File uploaded successfully!</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const showSuccess = ref(false)

const handleUpload = async () => {
  try {
    await uploadFile()
    showSuccess.value = true
    setTimeout(() => { showSuccess.value = false }, 3000)
  } catch (error) {
    // Handle error
  }
}
</script>
```

**After** (Using useToast):
```vue
<script setup>
import { useToast } from '@/composables/useToast'

const { showToast } = useToast()

const handleUpload = async () => {
  try {
    await uploadFile()
    showToast('File uploaded successfully!', 'success')
  } catch (error) {
    showToast('Upload failed. Please try again.', 'error')
  }
}
</script>
```

**Benefits**:
- ✅ Global toast management (no local state)
- ✅ Auto-dismiss after duration
- ✅ Type variants (info/success/warning/error)
- ✅ Stack multiple toasts
- ✅ Programmatic control

**All Usage Patterns**:
```javascript
import { useToast } from '@/composables/useToast'

const { showToast, removeToast, clearAllToasts, toasts } = useToast()

// Show toast with auto-dismiss (3 seconds default)
showToast('Operation successful!', 'success')

// Show toast with custom duration
showToast('Processing...', 'info', 5000)

// Show toast that persists (no auto-dismiss)
const toastId = showToast('Critical error', 'error', 0)

// Manually dismiss specific toast
removeToast(toastId)

// Clear all toasts
clearAllToasts()

// Access all active toasts (reactive)
console.log(toasts.value)
```

**Note**: Requires Toast UI component in App.vue or layout to display toasts. See `KnowledgePersistenceDialog.vue` for implementation example.

---

### Example 4: Migrating to EmptyState Component

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
   ./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/components/YourComponent.vue /home/autobot/autobot-user-frontend/src/components/YourComponent.vue
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

- [Format Helpers Source](../../autobot-user-frontend/autobot-user-backend/utils/formatHelpers.ts)
- [UI Components Directory](../../autobot-user-frontend/src/components/ui/)
- [Base Components Directory](../../autobot-user-frontend/src/components/base/)
- [Composables Directory](../../autobot-user-frontend/src/composables/)
- [Shared Styles Directory](../../autobot-user-frontend/src/styles/)

---

**For questions or suggestions**, contact the development team or open an issue in the repository.
