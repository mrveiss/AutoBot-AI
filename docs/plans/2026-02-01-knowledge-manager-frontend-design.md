# Knowledge Manager Frontend Completion Design

**Issue**: #747
**Date**: 2026-02-01
**Status**: Approved
**Approach**: Component-per-Feature (Extend modular architecture)

---

## Overview

Complete the Knowledge Manager frontend to restore critical administrative capabilities for the knowledge base. The implementation extends the existing modular architecture in `autobot-vue/src/components/knowledge/`.

## Component Architecture

### Tab Structure (8 tabs total)

| Tab | Component | Status |
|-----|-----------|--------|
| Search | `KnowledgeSearch.vue` | Exists |
| Categories | `KnowledgeCategories.vue` | Enhance (add edit/delete) |
| Upload | `KnowledgeUpload.vue` | Enhance (drag-drop, batch) |
| Manage | `KnowledgeEntries.vue` | Enhance (bulk operations) |
| **System Docs** | `KnowledgeSystemDocs.vue` | **New** |
| **Prompts** | `KnowledgePromptEditor.vue` | **New** |
| Statistics | `KnowledgeStats.vue` | Exists |
| Advanced | `KnowledgeAdvanced.vue` | Exists |

### New Files to Create

```
autobot-vue/src/components/knowledge/
├── KnowledgeSystemDocs.vue        # System documentation viewer/exporter
├── KnowledgePromptEditor.vue      # System & agent prompt editor
├── modals/
│   ├── CategoryEditModal.vue      # Edit/delete category dialog
│   ├── DocumentExportModal.vue    # Export options dialog
│   └── PromptHistoryModal.vue     # Version history for prompts
├── panels/
│   └── SourcePreviewPanel.vue     # Side panel for chat source preview
```

### Store Updates (`useKnowledgeStore.ts`)

```typescript
// New state
systemDocs: SystemDoc[]
prompts: Prompt[]
selectedDocumentId: string | null
categoryEditModal: { open: boolean; category: Category | null }
sourcePanel: { open: boolean; document: SystemDoc | null }

// New actions
loadSystemDocs(): Promise<void>
loadPrompts(): Promise<void>
updateCategory(id: string, data: CategoryUpdate): Promise<void>
deleteCategory(id: string): Promise<void>
updatePrompt(id: string, content: string): Promise<void>
revertPrompt(id: string, version: string): Promise<void>
setSelectedDocument(id: string): void
openSourcePanel(doc: SystemDoc): void
closeSourcePanel(): void
```

---

## Feature 1: Category Management (Edit/Delete)

### Enhancement to `KnowledgeCategories.vue`

Add edit/delete actions to each category card via dropdown menu.

### CategoryEditModal.vue

**Features:**
- Edit category name, description, icon, color
- Delete category (with confirmation)
- Move category to different parent
- View category statistics (fact count, last updated)

**Safety Rules:**
- Cannot delete categories with children (backend enforces)
- Cannot delete system-protected categories
- Show fact count before delete to warn user

### API Endpoints (existing)

```
PUT    /api/knowledge_base/categories/{category_id}
DELETE /api/knowledge_base/categories/{category_id}
GET    /api/knowledge_base/categories/tree
```

---

## Feature 2: System Documentation Viewer

### KnowledgeSystemDocs.vue

**Data Sources:**
- Documentation from knowledge base collection `autobot-documentation`
- System knowledge entries

**UI Layout:**
```
┌─────────────────────────────────────────────────┐
│ [Search docs...] [Filter: All ▼] [Export All ▼] │
├─────────────────────────────────────────────────┤
│ 📁 API Documentation          │ Document Preview │
│   ├── endpoints.md            │                  │
│   ├── authentication.md       │ # API Endpoints  │
│ 📁 Developer Guides           │                  │
│   ├── setup.md                │ Content here...  │
│   └── contributing.md         │                  │
│ 📁 Architecture               │ [View] [Export]  │
└─────────────────────────────────────────────────┘
```

**Features:**
- Tree view of documentation categories
- Markdown preview with syntax highlighting
- Export single doc or bulk export (JSON, Markdown, PDF)
- Search within documents
- Copy to clipboard

### DocumentExportModal.vue

**Options:**
- Format: Markdown / JSON / PDF
- Scope: Single document / Category / All
- Include metadata: Yes/No

---

## Feature 3: Source Attribution (Dual Access)

When chat retrieves information from knowledge base, show clickable sources with two access methods:

### Method 1: Side Panel (Stay in Chat)

Click source link opens `SourcePreviewPanel.vue` alongside chat.

```
┌────────────────────────────┬─────────────────────┐
│ Chat                       │ 📄 authentication.md│
│                            │ ─────────────────── │
│ 🤖 The API uses JWT...     │ # Authentication    │
│                            │                     │
│ 📚 Sources:                │ JWT tokens are...   │
│   • authentication.md ←    │                     │
│                            │ [Open Full] [Copy]  │
└────────────────────────────┴─────────────────────┘
```

### Method 2: Deep-Link (Navigate to Knowledge Manager)

"Open in Knowledge Manager" button navigates with document pre-selected.

**Route Structure:**
```
/knowledge?tab=system-docs&doc={documentId}
/knowledge?tab=system-docs&path={encodedPath}
```

### SourcePreviewPanel.vue

**Features:**
- Document title and metadata
- Full content preview with markdown rendering
- "Open in Knowledge Manager" button (deep-link)
- "Copy content" button
- Close button
- Resizable width

---

## Feature 4: Prompt Editor

### KnowledgePromptEditor.vue

**UI Layout:**
```
┌─────────────────────────────────────────────────────┐
│ [Search...] [Type: All ▼] [+ New Prompt]            │
├──────────────────┬──────────────────────────────────┤
│ 📋 System        │ system_main_prompt               │
│   • main_prompt  │ ──────────────────────────────── │
│   • safety       │ You are AutoBot, an AI assistant │
│ 📋 Agents        │ designed to help with...         │
│   • research     │                                  │
│   • code_review  │ ┌──────────────────────────────┐ │
│   • planning     │ │ Monaco Editor                │ │
│ 📋 Templates     │ │ with syntax highlighting     │ │
│   • task_breakdown│ │                              │ │
│                  │ └──────────────────────────────┘ │
│                  │                                  │
│                  │ [History] [Test] [Save] [Revert] │
└──────────────────┴──────────────────────────────────┘
```

**Features:**
- Categorized prompt list (System, Agents, Templates)
- Monaco editor with markdown/text highlighting
- Version history modal (view diffs, revert)
- "Test Prompt" - sends test message to see output
- Unsaved changes warning
- Prompt variables highlighting (`{{variable}}`)

### PromptHistoryModal.vue

**Features:**
- List of previous versions with timestamps
- Side-by-side diff view
- One-click revert with confirmation

### API Endpoints (existing)

```
GET    /api/prompts              # List all prompts
GET    /api/prompts/{id}         # Get full content
PUT    /api/prompts/{id}         # Update prompt
POST   /api/prompts/{id}/revert  # Revert to previous version
```

---

## Feature 5: Document Management Enhancements

### Upload Improvements (`KnowledgeUpload.vue`)

- Drag-and-drop zone with visual feedback
- Upload progress with percentage
- Preview file content before upload
- Batch upload multiple files
- Auto-detect category from file path/content

```
┌─────────────────────────────────────────┐
│  ┌─────────────────────────────────┐    │
│  │     📁 Drop files here          │    │
│  │     or click to browse          │    │
│  └─────────────────────────────────┘    │
│                                         │
│  Queued Files:                          │
│  ├── readme.md ✅ Ready    [Preview] [X]│
│  ├── api.json  ✅ Ready    [Preview] [X]│
│  └── notes.txt ⏳ Processing...         │
│                                         │
│  Category: [Auto-detect ▼]              │
│  Tags: [api, documentation]             │
│                                         │
│  [Upload All]                           │
└─────────────────────────────────────────┘
```

### Bulk Operations (`KnowledgeEntries.vue`)

- Checkbox selection on entries
- "Select All" / "Select None"
- Bulk actions toolbar: Delete, Move to Category, Export, Re-vectorize

```
┌─────────────────────────────────────────┐
│ ☑ 3 selected  [Delete] [Move] [Export]  │
├─────────────────────────────────────────┤
│ ☑ Document 1                            │
│ ☑ Document 2                            │
│ ☐ Document 3                            │
│ ☑ Document 4                            │
└─────────────────────────────────────────┘
```

---

## Feature 6: Loading States & Error Handling

Consistent patterns across all components:

- **Skeleton loaders** during data fetch
- **Toast notifications** for success/error feedback
- **Retry buttons** on network failures
- **Empty states** with helpful actions and icons
- **Unsaved changes warnings** before navigation

---

## Implementation Order

1. **Store updates** - Add new state and actions to `useKnowledgeStore.ts`
2. **CategoryEditModal** - Enable category edit/delete
3. **KnowledgeSystemDocs** - New tab with doc viewer
4. **SourcePreviewPanel** - Side panel for chat integration
5. **KnowledgePromptEditor** - New tab with editor
6. **Upload enhancements** - Drag-drop and batch
7. **Bulk operations** - Multi-select in entries
8. **Polish** - Loading states, error handling, responsive design

---

## Related Files

**Frontend:**
- `autobot-vue/src/components/knowledge/KnowledgeManager.vue`
- `autobot-vue/src/stores/useKnowledgeStore.ts`
- `autobot-vue/src/components/ChatInterface.vue` (source attribution)

**Backend (existing, stable):**
- `backend/api/knowledge_categories.py`
- `backend/api/prompts.py`
- `backend/api/knowledge_search.py`
- `backend/api/chat_knowledge.py`

---

## Success Criteria

- [ ] Users can create, edit, and delete knowledge categories
- [ ] Users can view and export system documentation
- [ ] Users can edit system and agent prompts with version history
- [ ] Chat sources link to documents via side panel or deep-link
- [ ] Drag-drop upload with batch support works
- [ ] Bulk operations on entries work
- [ ] All operations properly integrated with backend
- [ ] Loading states and error handling consistent
- [ ] Responsive design for mobile/tablet

---

*Generated for Issue #747 - Knowledge Manager Frontend Completion*
