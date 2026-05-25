# Live Canvas

The Live Canvas is an agent-controlled workspace that renders structured artifacts alongside the chat panel. Agents can stream rich content blocks — markdown, code, charts, and images — directly into the canvas where you can view, edit, and export them.

## Opening the Canvas

Navigate to **Canvas** in the sidebar, or use the keyboard shortcut **⌘L** (or **Ctrl+L**) from within the canvas view to toggle focus between chat and canvas.

## Layout modes

The canvas supports four layout modes, toggled by double-clicking the divider or using the toolbar:

| Mode | Description |
|------|-------------|
| **Split** (default) | Chat (35%) and canvas (65%) side by side |
| **Canvas focus** | Canvas expanded, chat minimised |
| **Chat focus** | Chat expanded, canvas hidden |
| **Full canvas** | Canvas fills the full width |

On narrow viewports (≤390 px), the layout switches to a tab bar so you can switch between Chat and Canvas.

Drag the divider to set a custom split ratio.

## Cell types

Each piece of content the agent writes is a **cell**. Cells come in three types:

| Type | Content |
|------|---------|
| **Markdown** | Formatted text with bold, italics, headings, and inline code |
| **Code** | Syntax-highlighted code block with a one-click copy button |
| **Chart** | Interactive Vega-Lite chart with a data table fallback for screen readers |

## Streaming states

While the agent is writing, cells show a live streaming state:

- **Skeleton** — agent has started, content loading
- **Partial** — content streaming in with a blinking cursor
- **Complete** — agent finished; you can Accept, Edit, or Discard
- **Error** — stream failed; you can Keep, Retry, or Discard

## Accepting and editing agent output

Agent cells appear with a coloured left border and a 🤖 badge. When the agent finishes writing a cell you can:

- **Accept (⌥Enter)** — promote the cell to user-owned content
- **Edit (Enter)** — open the cell for editing and take ownership
- **Discard (Esc)** — remove the cell

Use **⌘↑** / **⌘↓** to reorder any focused cell, and use the cell toolbar (visible on hover) to duplicate, copy, or delete.

## Conflict resolution

If you edit a cell while the agent is still writing it, the agent automatically continues in a new cell below. A **Conflict** banner appears at the top of the canvas — click **Resume** to keep both versions, or **Dismiss** to discard the agent continuation.

## Undo / Redo

Use **⌘Z** / **⌘⇧Z** to step through the edit history. Up to 100 history states are kept per session.

## Auto-save

Canvas content saves automatically one second after each edit. The toolbar shows the save status:

- ✓ Saved *HH:MM* — last successful save
- 💾 Saving… — save in progress
- ⚠ Save failed — tap **Retry** in the toolbar

## Exporting

Click **Export** in the toolbar (or press **⌘⇧E**) to open the export sheet. Choose a format and which cell types to include:

| Format | Output |
|--------|--------|
| Markdown | `.md` file |
| HTML | `.html` file |
| JSON | `.json` file (full cell objects) |
| PDF | `.txt` fallback (browser PDF via print) |

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| ⌘Z | Undo |
| ⌘⇧Z | Redo |
| ⌘L | Focus chat panel |
| ⌥Enter | Accept focused agent cell |
| Enter | Edit focused agent cell |
| Esc | Discard focused agent cell |
| ⌘↑ | Move focused cell up |
| ⌘↓ | Move focused cell down |

## Feature flag

The canvas is gated behind the `VITE_FEATURE_CANVAS=true` environment variable. When the flag is not set the `/canvas` route is still reachable but the nav item respects the flag if filtered server-side.

## Related

- [GH#7425](https://github.com/mrveiss/AutoBot-AI/issues/7425) — implementation issue
- [GH#5136](https://github.com/mrveiss/AutoBot-AI/issues/5136) — browser panel integration (phases 3-5)
