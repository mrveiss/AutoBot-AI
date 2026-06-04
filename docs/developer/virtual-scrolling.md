---
tags: [type/reference, status/current, component/frontend]
date: 2026-06-04
issue: 4037
---

# Virtual Scrolling

How to use the `useVirtualList` composable to render large lists efficiently.

> **Status:** Composable is implemented and ready. Integration into `ParticipantList`, `SecretsManager`, and `AuditLogTable` is deferred — see [Frontend Optimization Opportunities](../architecture/frontend-optimization.md) for context.

---

## Basic Pattern

```typescript
import { useVirtualList } from '@/composables/useVirtualList'

const { containerRef, visibleItems, totalHeight } = useVirtualList(
    items,       // Ref<T[]> or ComputedRef<T[]>
    56,          // item height in px (must be fixed)
    10,          // overscan — extra items rendered outside viewport (default 3)
)
```

Template:

```vue
<div
    ref="containerRef"
    style="height: 400px; overflow-y: auto; position: relative;"
>
    <div :style="{ height: totalHeight + 'px', position: 'relative' }">
        <div
            v-for="virtualItem in visibleItems"
            :key="virtualItem.data.id"
            :style="{
                transform: `translateY(${virtualItem.offset}px)`,
                position: 'absolute',
                width: '100%',
            }"
        >
            <!-- use virtualItem.data instead of item -->
        </div>
    </div>
</div>
```

---

## Component-Specific Heights

| Component | Item height | List ref |
|---|---|---|
| `ParticipantList.vue` | 56 px | `participantsWithRoles` |
| `SecretsManager.vue` | 48 px | `filteredSecrets` |
| `AuditLogTable.vue` | 40 px | `sortedEntries` |

---

## Scroll to a Specific Item

```typescript
const scrollToItem = (index: number, itemHeightPx: number) => {
    if (containerRef.value) {
        containerRef.value.scrollTop = index * itemHeightPx
    }
}
```

---

## Performance Gains (Expected)

| Metric | Improvement |
|---|---|
| Initial render | 20–30% faster |
| Scroll smoothness | 60–80% improvement |
| DOM node count | 70–80% reduction |
| Filter/sort on filtered result | Near-instant |

---

## Constraints

- **Fixed item height required.** Variable-height rows need a different approach.
- **Container height must be set.** 400–600 px is the recommended range — too small adds unnecessary scrollbars, too large defeats virtualization.
- **Filter resets scroll.** When the item list changes, scroll position may be invalid; reset to 0 if needed.

---

## Checklist After Integration

- [ ] All items reachable by scrolling
- [ ] Filter/search updates visible items correctly
- [ ] Click handlers work on virtual items
- [ ] 60 FPS scroll in Chrome DevTools performance panel
- [ ] Memory usage stable under continuous scroll
