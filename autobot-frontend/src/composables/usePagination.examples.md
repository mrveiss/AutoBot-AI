# usePagination Examples

Comprehensive migration guide and examples for the `usePagination` composable.

## Table of Contents
- [Basic Pagination](#basic-pagination)
- [Migration Examples](#migration-examples)
- [Simple Pagination Patterns](#simple-pagination-patterns)
- [Show All Toggle](#show-all-toggle)
- [Server-Side Pagination](#server-side-pagination)
- [Advanced Features](#advanced-features)

---

## Basic Pagination

### Example 1: Basic Client-Side Pagination

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { usePagination } from '@/composables/usePagination'

interface Document {
  id: string
  title: string
  content: string
}

const documents = ref<Document[]>([
  { id: '1', title: 'Doc 1', content: 'Content 1' },
  { id: '2', title: 'Doc 2', content: 'Content 2' },
  // ... 100 documents
])

const {
  paginatedData,
  currentPage,
  totalPages,
  hasNext,
  hasPrev,
  next,
  prev,
  goToPage
} = usePagination(documents, {
  itemsPerPage: 20,
  initialPage: 1
})
</script>

<template>
  <div class="pagination-container">
    <!-- Items -->
    <div class="items">
      <div v-for="doc in paginatedData" :key="doc.id" class="item">
        <h3>{{ doc.title }}</h3>
        <p>{{ doc.content }}</p>
      </div>
    </div>

    <!-- Pagination Controls -->
    <div class="pagination-controls">
      <button @click="prev" :disabled="!hasPrev">
        <i class="fas fa-chevron-left"></i>
      </button>

      <span class="page-info">
        Page {{ currentPage }} of {{ totalPages }}
      </span>

      <button @click="next" :disabled="!hasNext">
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>
  </div>
</template>
```

---

## Migration Examples

### Migration 1: KnowledgeEntries.vue - Full Pagination

**BEFORE (Manual Pagination - 70 lines):**

```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue'

// Manual state management
const currentPage = ref(1)
const itemsPerPage = 20  // Hardcoded, not configurable

// Manual computed properties
const totalPages = computed(() =>
  Math.ceil(filteredDocuments.value.length / itemsPerPage)
)

const paginatedEntries = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return filteredDocuments.value.slice(start, end)
})

// Manual navigation (no bounds checking)
const nextPage = () => {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
  }
}

const prevPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

// Manual reset on filter change
const filterEntries = () => {
  currentPage.value = 1  // Must remember to reset
}

const clearFilters = () => {
  searchQuery.value = ''
  filterCategory.value = ''
  filterType.value = ''
  sortBy.value = 'updatedAt'
  currentPage.value = 1  // Must remember to reset
}

// Manual watch for auto-reset
watch([searchQuery, filterCategory, filterType], () => {
  currentPage.value = 1
})
</script>

<template>
  <div class="entries-list">
    <!-- Entries -->
    <div v-for="entry in paginatedEntries" :key="entry.id">
      {{ entry.title }}
    </div>

    <!-- Pagination Controls -->
    <div class="pagination">
      <button @click="prevPage" :disabled="currentPage === 1">
        <i class="fas fa-chevron-left"></i>
      </button>

      <span class="page-info">
        Page {{ currentPage }} of {{ totalPages }}
        ({{ filteredDocuments.length }} entries)
      </span>

      <button @click="nextPage" :disabled="currentPage === totalPages">
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>
  </div>
</template>
```

**AFTER (Using usePagination - 30 lines):**

```vue
<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePagination } from '@/composables/usePagination'

// All pagination logic in one composable
const {
  paginatedData: paginatedEntries,
  currentPage,
  totalPages,
  totalItems,
  hasNext,
  hasPrev,
  next,
  prev
} = usePagination(filteredDocuments, {
  itemsPerPage: 20,
  autoResetOnDataChange: true  // Auto-resets when filteredDocuments changes
})

// No manual reset needed - handled automatically
const filterEntries = () => {
  // Pagination auto-resets when filteredDocuments changes
}

const clearFilters = () => {
  searchQuery.value = ''
  filterCategory.value = ''
  filterType.value = ''
  sortBy.value = 'updatedAt'
  // No manual reset needed
}

// No manual watch needed - autoResetOnDataChange handles this
</script>

<template>
  <div class="entries-list">
    <!-- Entries -->
    <div v-for="entry in paginatedEntries" :key="entry.id">
      {{ entry.title }}
    </div>

    <!-- Pagination Controls -->
    <div class="pagination">
      <button @click="prev" :disabled="!hasPrev">
        <i class="fas fa-chevron-left"></i>
      </button>

      <span class="page-info">
        Page {{ currentPage }} of {{ totalPages }}
        ({{ totalItems }} entries)
      </span>

      <button @click="next" :disabled="!hasNext">
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>
  </div>
</template>
```

**Improvements:**
- ✅ Reduced from ~70 lines to ~30 lines (57% reduction)
- ✅ No manual state management
- ✅ No manual computed properties
- ✅ Automatic reset on data changes (no watch needed)
- ✅ Built-in navigation with bounds checking
- ✅ Configurable items per page

---

## Simple Pagination Patterns

### Migration 2: Show First N Items

**BEFORE (Manual .slice() - Multiple Files):**

```vue
<script setup lang="ts">
const activeIssues = ref([...])

// Hardcoded slice
const visibleIssues = computed(() => activeIssues.value.slice(0, 3))
</script>

<template>
  <div v-for="issue in visibleIssues" :key="issue.id">
    {{ issue.title }}
  </div>
</template>
```

**AFTER (Using useSimplePagination):**

```vue
<script setup lang="ts">
import { useSimplePagination } from '@/composables/usePagination'

const activeIssues = ref([...])

// Reusable helper
const visibleIssues = useSimplePagination(activeIssues, 3, 'first')
</script>

<template>
  <div v-for="issue in visibleIssues" :key="issue.id">
    {{ issue.title }}
  </div>
</template>
```

**Benefits:**
- Self-documenting intent (showing first 3)
- Reusable pattern
- Null-safe (handles empty arrays)

### Migration 3: Show Last N Items

**BEFORE:**

```vue
<script setup lang="ts">
const notifications = ref([...])

// Hardcoded negative slice
const recentNotifications = computed(() =>
  notifications.value.filter(n => n.visible).slice(-5)
)
</script>

<template>
  <div v-for="notif in recentNotifications" :key="notif.id">
    {{ notif.message }}
  </div>
</template>
```

**AFTER:**

```vue
<script setup lang="ts">
import { useSimplePagination } from '@/composables/usePagination'

const notifications = ref([...])

// Filter first, then show last 5
const visibleNotifications = computed(() =>
  notifications.value.filter(n => n.visible)
)

const recentNotifications = useSimplePagination(
  visibleNotifications,
  5,
  'last'
)
</script>

<template>
  <div v-for="notif in recentNotifications" :key="notif.id">
    {{ notif.message }}
  </div>
</template>
```

---

## Show All Toggle

### Migration 4: CodebaseAnalytics.vue - Toggle Pattern

**BEFORE (Manual Toggle):**

```vue
<script setup lang="ts">
const showAllProblems = ref(false)
const problemsReport = ref([...])

// Manual slice with ternary
const visibleProblems = computed(() =>
  showAllProblems.value
    ? problemsReport.value
    : problemsReport.value.slice(0, 10)
)
</script>

<template>
  <div v-for="problem in visibleProblems" :key="problem.id">
    {{ problem.description }}
  </div>

  <button @click="showAllProblems = !showAllProblems">
    {{ showAllProblems ? 'Show Less' : 'Show All' }}
  </button>
</template>
```

**AFTER (Using useShowAllToggle):**

```vue
<script setup lang="ts">
import { useShowAllToggle } from '@/composables/usePagination'

const showAllProblems = ref(false)
const problemsReport = ref([...])

// Clean helper
const visibleProblems = useShowAllToggle(
  problemsReport,
  showAllProblems,
  10
)
</script>

<template>
  <div v-for="problem in visibleProblems" :key="problem.id">
    {{ problem.description }}
  </div>

  <button @click="showAllProblems = !showAllProblems">
    {{ showAllProblems ? 'Show Less' : 'Show All' }}
  </button>
</template>
```

### Alternative: Full Pagination with Show All

```vue
<script setup lang="ts">
import { usePagination } from '@/composables/usePagination'

const problemsReport = ref([...])

const {
  paginatedData: visibleProblems,
  currentPage,
  totalPages,
  isShowingAll,
  toggleShowAll,
  next,
  prev
} = usePagination(problemsReport, {
  itemsPerPage: 10
})
</script>

<template>
  <div v-for="problem in visibleProblems" :key="problem.id">
    {{ problem.description }}
  </div>

  <!-- Enhanced Controls -->
  <div class="controls">
    <button @click="toggleShowAll">
      {{ isShowingAll ? 'Show Paginated' : 'Show All' }}
    </button>

    <div v-if="!isShowingAll" class="pagination">
      <button @click="prev">Previous</button>
      <span>Page {{ currentPage }} of {{ totalPages }}</span>
      <button @click="next">Next</button>
    </div>
  </div>
</template>
```

---

## Server-Side Pagination

### Example 5: API-Driven Pagination

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { usePagination } from '@/composables/usePagination'

interface ApiResponse {
  data: Document[]
  total: number
  page: number
  perPage: number
}

const documents = ref<Document[]>([])
const loading = ref(false)

// Fetch function
const fetchDocuments = async (page: number, perPage: number) => {
  loading.value = true
  try {
    const response = await fetch(
      `/api/documents?page=${page}&per_page=${perPage}`
    )
    const data: ApiResponse = await response.json()

    documents.value = data.data
  } catch (error) {
    console.error('Failed to fetch documents:', error)
  } finally {
    loading.value = false
  }
}

// Server-side pagination
const pagination = usePagination(documents, {
  serverTotalItems: 1000,  // Total from API
  itemsPerPage: 20,
  onPageChange: async (page, perPage) => {
    await fetchDocuments(page, perPage)
  }
})

// Initial load
await fetchDocuments(1, 20)
</script>

<template>
  <div class="server-pagination">
    <!-- Loading State -->
    <LoadingSpinner v-if="loading" />

    <!-- Items -->
    <div v-else>
      <div v-for="doc in pagination.paginatedData.value" :key="doc.id">
        {{ doc.title }}
      </div>
    </div>

    <!-- Pagination Controls -->
    <div class="pagination">
      <button
        @click="pagination.prev()"
        :disabled="!pagination.hasPrev.value || loading"
      >
        Previous
      </button>

      <span>
        Page {{ pagination.currentPage.value }}
        of {{ pagination.totalPages.value }}
      </span>

      <button
        @click="pagination.next()"
        :disabled="!pagination.hasNext.value || loading"
      >
        Next
      </button>
    </div>
  </div>
</template>
```

---

## Advanced Features

### Example 6: Dynamic Items Per Page

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { usePagination } from '@/composables/usePagination'

const items = ref([...])

const pagination = usePagination(items, {
  itemsPerPage: 20
})

const pageSizeOptions = [10, 20, 50, 100]

const handlePageSizeChange = (size: number) => {
  pagination.setItemsPerPage(size)
}
</script>

<template>
  <div>
    <!-- Items -->
    <div v-for="item in pagination.paginatedData.value" :key="item.id">
      {{ item.title }}
    </div>

    <!-- Controls -->
    <div class="controls">
      <!-- Page Size Selector -->
      <select
        :value="pagination.itemsPerPage.value"
        @change="handlePageSizeChange($event.target.value)"
      >
        <option v-for="size in pageSizeOptions" :key="size" :value="size">
          {{ size }} per page
        </option>
      </select>

      <!-- Pagination -->
      <button @click="pagination.prev()">Previous</button>
      <span>{{ pagination.currentPage.value }} / {{ pagination.totalPages.value }}</span>
      <button @click="pagination.next()">Next</button>
    </div>
  </div>
</template>
```

### Example 7: Page Number Inputs

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { usePagination } from '@/composables/usePagination'

const items = ref([...])
const pagination = usePagination(items, { itemsPerPage: 20 })

const pageInput = ref<number>(pagination.currentPage.value)

const handleGoToPage = () => {
  if (pageInput.value >= 1 && pageInput.value <= pagination.totalPages.value) {
    pagination.goToPage(pageInput.value)
  } else {
    alert(`Please enter a page between 1 and ${pagination.totalPages.value}`)
  }
}

// Sync input with current page
watch(() => pagination.currentPage.value, (newPage) => {
  pageInput.value = newPage
})
</script>

<template>
  <div class="pagination-controls">
    <!-- First Page -->
    <button
      @click="pagination.goToFirst()"
      :disabled="pagination.isFirstPage.value"
    >
      <i class="fas fa-angle-double-left"></i>
    </button>

    <!-- Previous -->
    <button
      @click="pagination.prev()"
      :disabled="!pagination.hasPrev.value"
    >
      <i class="fas fa-chevron-left"></i>
    </button>

    <!-- Page Input -->
    <div class="page-input">
      <input
        v-model.number="pageInput"
        type="number"
        min="1"
        :max="pagination.totalPages.value"
        @keyup.enter="handleGoToPage"
      />
      <span>of {{ pagination.totalPages.value }}</span>
      <button @click="handleGoToPage">Go</button>
    </div>

    <!-- Next -->
    <button
      @click="pagination.next()"
      :disabled="!pagination.hasNext.value"
    >
      <i class="fas fa-chevron-right"></i>
    </button>

    <!-- Last Page -->
    <button
      @click="pagination.goToLast()"
      :disabled="pagination.isLastPage.value"
    >
      <i class="fas fa-angle-double-right"></i>
    </button>
  </div>
</template>
```

### Example 8: Page Range Display

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import { usePagination } from '@/composables/usePagination'

const items = ref([...])
const pagination = usePagination(items, { itemsPerPage: 20 })

// Generate page numbers to show (e.g., "1 ... 5 6 7 ... 20")
const pageNumbers = computed(() => {
  const current = pagination.currentPage.value
  const total = pagination.totalPages.value
  const delta = 2  // Pages to show on each side of current

  const range: (number | string)[] = []

  for (let i = 1; i <= total; i++) {
    if (
      i === 1 ||  // First page
      i === total ||  // Last page
      (i >= current - delta && i <= current + delta)  // Near current
    ) {
      range.push(i)
    } else if (range[range.length - 1] !== '...') {
      range.push('...')
    }
  }

  return range
})
</script>

<template>
  <div class="pagination">
    <button @click="pagination.prev()" :disabled="!pagination.hasPrev.value">
      Previous
    </button>

    <button
      v-for="(page, index) in pageNumbers"
      :key="index"
      @click="typeof page === 'number' && pagination.goToPage(page)"
      :class="{
        'active': page === pagination.currentPage.value,
        'ellipsis': page === '...'
      }"
      :disabled="page === '...'"
    >
      {{ page }}
    </button>

    <button @click="pagination.next()" :disabled="!pagination.hasNext.value">
      Next
    </button>
  </div>
</template>

<style scoped>
.pagination button.active {
  background-color: #4f46e5;
  color: white;
  font-weight: bold;
}

.pagination button.ellipsis {
  cursor: default;
  opacity: 0.5;
}
</style>
```

---

## Performance Considerations

### Large Data Sets (10,000+ items)

```vue
<script setup lang="ts">
import { ref, shallowRef } from 'vue'
import { usePagination } from '@/composables/usePagination'

// Use shallowRef for large arrays to avoid deep reactivity
const largeDataset = shallowRef<Item[]>([...])

const pagination = usePagination(largeDataset, {
  itemsPerPage: 50,
  autoResetOnDataChange: false  // Disable auto-watch for performance
})

// Manual reset when needed
const resetPagination = () => {
  pagination.reset()
}
</script>
```

### Virtual Scrolling Alternative

For extremely large datasets (100,000+ items), consider using virtual scrolling instead of pagination:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useVirtualList } from '@vueuse/core'

const largeDataset = ref([...100000 items...])

const { list, containerProps, wrapperProps } = useVirtualList(
  largeDataset,
  { itemHeight: 50 }
)
</script>

<template>
  <div v-bind="containerProps" style="height: 600px; overflow: auto;">
    <div v-bind="wrapperProps">
      <div v-for="{ data, index } in list" :key="index" style="height: 50px;">
        {{ data.title }}
      </div>
    </div>
  </div>
</template>
```

---

## Summary

### When to Use Each Pattern

| Pattern | Use Case | Example |
|---------|----------|---------|
| `usePagination` | Full pagination with navigation | Large lists, tables, search results |
| `useSimplePagination` | Show first/last N items | Dashboards, recent activity, top items |
| `useShowAllToggle` | Toggle between limited and full view | Reports, logs, expandable sections |
| Server-side pagination | Large datasets from API | Database queries, search engines |
| Virtual scrolling | Extremely large in-memory datasets | Real-time logs, large data grids |

### Migration Checklist

- [ ] Identify pagination patterns in component
- [ ] Choose appropriate helper (usePagination, useSimplePagination, useShowAllToggle)
- [ ] Replace manual state management with composable
- [ ] Remove manual computed properties
- [ ] Remove manual watch/reset logic
- [ ] Update template to use composable properties
- [ ] Test pagination behavior
- [ ] Verify auto-reset works correctly
- [ ] Check edge cases (empty data, single page, etc.)
