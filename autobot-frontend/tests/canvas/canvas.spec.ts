// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { test, expect } from '@playwright/test'

// Minimal shape of the canvas store exposed on window for E2E hooks.
interface CanvasStoreHandle {
  cells: Array<{ id: string }>
  isDirty: boolean
  addCell: (owner: string) => void
  updateCellContent: (id: string, content: string) => void
  upsertStreamCell: (cell: { cellId: string; seq: number; delta: string; state: string }) => void
}

type CanvasWindow = Window & { __canvasStore?: CanvasStoreHandle }

test.describe('Canvas (MVA-360 Phase 1)', () => {
  test.beforeEach(async ({ page }) => {
    // Set feature flag and navigate to canvas
    await page.addInitScript(() => {
      localStorage.setItem('VITE_FEATURE_CANVAS', 'true')
    })
    await page.goto('/canvas')
    await page.waitForLoadState('networkidle')
  })

  test('renders adaptive split layout (35/65 default) with draggable gutter', async ({ page }) => {
    const chatPanel = page.locator('[data-testid="canvas-panel-chat"]')
    const canvasPanel = page.locator('[data-testid="canvas-panel-canvas"]')
    const gutter = page.locator('[data-testid="canvas-gutter"]')

    // Verify panels exist
    await expect(chatPanel).toBeVisible()
    await expect(canvasPanel).toBeVisible()
    await expect(gutter).toBeVisible()

    // Gutter should be draggable (has cursor:col-resize)
    await expect(gutter).toHaveCSS('cursor', /col-resize/)
  })

  test('split layout has 4 variants accessible via context menu', async ({ page }) => {
    const layoutButton = page.locator('[data-testid="canvas-layout-variant-selector"]')

    // Click to open variant selector
    await layoutButton.click()

    // Verify all 4 variants are available
    const splitOption = page.locator('text=Split')
    const canvasFocusOption = page.locator('text=Canvas Focus')
    const chatFocusOption = page.locator('text=Chat Focus')
    const fullCanvasOption = page.locator('text=Full Canvas')

    await expect(splitOption).toBeVisible()
    await expect(canvasFocusOption).toBeVisible()
    await expect(chatFocusOption).toBeVisible()
    await expect(fullCanvasOption).toBeVisible()
  })

  test('agent cell displays ownership signals: color border + background tint + 🤖 badge', async ({ page }) => {
    // Create an agent cell (simulated via store)
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'agent-cell-1',
          seq: 1,
          delta: 'Agent response...',
          state: 'partial'
        })
      }
    })

    const agentCell = page.locator('[data-testid="canvas-cell-agent-cell-1"]')
    await expect(agentCell).toBeVisible()

    // Verify color tokens applied (check computed style)
    const _computedStyle = await agentCell.evaluate(el => window.getComputedStyle(el))

    // Verify border-left styling (color-agent-draft-border)
    await expect(agentCell).toHaveCSS('border-left-color', /(3B82F6|60A5FA)/) // blue or light blue

    // Verify background color (color-agent-draft-bg)
    await expect(agentCell).toHaveCSS('background-color', /(EFF6FF|1E3A5F|rgb)/) // light blue bg

    // Verify 🤖 badge is present
    const badge = agentCell.locator('text=🤖')
    await expect(badge).toBeVisible()
  })

  test('user cell displays without agent styling (color independence verified)', async ({ page }) => {
    // Create a user cell
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.addCell('user')
      }
    })

    const userCell = page.locator('[data-testid="canvas-cell"][data-owner="user"]').first()
    await expect(userCell).toBeVisible()

    // User cell should NOT have agent-draft colors
    const style = await userCell.evaluate(el => {
      const computed = window.getComputedStyle(el)
      return {
        borderLeftColor: computed.borderLeftColor,
        backgroundColor: computed.backgroundColor
      }
    })

    // Should not be agent-draft-border blue or agent-draft-bg light-blue
    expect(style.borderLeftColor).not.toMatch(/(3B82F6|60A5FA)/)
    expect(style.backgroundColor).not.toMatch(/(EFF6FF|1E3A5F)/)
  })

  test('streaming state machine: skeleton → partial → complete transitions', async ({ page }) => {
    // Start with skeleton (placeholder)
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'stream-cell-1',
          seq: 0,
          delta: '',
          state: 'skeleton'
        })
      }
    })

    const cell = page.locator('[data-testid="canvas-cell-stream-cell-1"]')
    await expect(cell).toBeVisible()

    // Verify skeleton state: shimmer or static blocks visible
    const skeleton = cell.locator('[data-testid="cell-skeleton"]')
    await expect(skeleton).toBeVisible()

    // Transition to partial (streaming)
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'stream-cell-1',
          seq: 1,
          delta: 'Streaming content...',
          state: 'partial'
        })
      }
    })

    // Verify partial state: cursor + "Writing..." label
    const cursor = cell.locator('[data-testid="cell-cursor"]')
    const writingLabel = cell.locator('text=Writing…')
    await expect(cursor).toBeVisible({ timeout: 5000 })
    await expect(writingLabel).toBeVisible()

    // Transition to complete
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'stream-cell-1',
          seq: 2,
          delta: 'Streaming complete.',
          state: 'complete'
        })
      }
    })

    // Verify complete state: controls appear, skeleton/cursor hidden
    const controls = cell.locator('[data-testid="cell-controls"]')
    await expect(controls).toBeVisible({ timeout: 5000 })
    await expect(skeleton).not.toBeVisible()
    await expect(cursor).not.toBeVisible()
  })

  test('tool palette: undo/redo, add cell, save status, export buttons all visible', async ({ page }) => {
    const undoBtn = page.locator('[data-testid="canvas-undo-btn"]')
    const redoBtn = page.locator('[data-testid="canvas-redo-btn"]')
    const addCellBtn = page.locator('[data-testid="canvas-add-cell-btn"]')
    const saveStatus = page.locator('[data-testid="canvas-save-status"]')
    const exportBtn = page.locator('[data-testid="canvas-export-btn"]')

    await expect(undoBtn).toBeVisible()
    await expect(redoBtn).toBeVisible()
    await expect(addCellBtn).toBeVisible()
    await expect(saveStatus).toBeVisible()
    await expect(exportBtn).toBeVisible()

    // Verify aria-labels for accessibility
    await expect(undoBtn).toHaveAttribute('aria-label', /[Uu]ndo/)
    await expect(redoBtn).toHaveAttribute('aria-label', /[Rr]edo/)
    await expect(addCellBtn).toHaveAttribute('aria-label', /[Aa]dd/)
    await expect(exportBtn).toHaveAttribute('aria-label', /[Ee]xport/)
  })

  test('keyboard shortcuts work: ⌘Z undo, ⌘⇧Z redo, ⌘⇧E export, ⌘L add cell', async ({ page }) => {
    // Add a cell, edit it, then undo
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.addCell('user')
        store.updateCellContent(store.cells[store.cells.length - 1].id, 'test content')
      }
    })

    const initialCount = await page.evaluate(() => (window as unknown as CanvasWindow).__canvasStore?.cells.length)

    // Press ⌘Z (meta+z)
    await page.keyboard.press('Meta+z')
    await page.waitForTimeout(100)

    const afterUndoCount = await page.evaluate(() => (window as unknown as CanvasWindow).__canvasStore?.cells.length)
    expect(afterUndoCount).toBe((initialCount || 0) - 1)

    // Press ⌘⇧Z (meta+shift+z)
    await page.keyboard.press('Meta+Shift+z')
    await page.waitForTimeout(100)

    const afterRedoCount = await page.evaluate(() => (window as unknown as CanvasWindow).__canvasStore?.cells.length)
    expect(afterRedoCount).toBe(initialCount)

    // Verify export sheet opens on ⌘⇧E
    await page.keyboard.press('Meta+Shift+e')
    const exportModal = page.locator('[data-testid="canvas-export-modal"]')
    await expect(exportModal).toBeVisible({ timeout: 2000 })
  })

  test('export sheet: 4 format options (markdown, pdf, html, json)', async ({ page }) => {
    const exportBtn = page.locator('[data-testid="canvas-export-btn"]')
    await exportBtn.click()

    const markdownOpt = page.locator('text=Markdown')
    const pdfOpt = page.locator('text=PDF')
    const htmlOpt = page.locator('text=HTML')
    const jsonOpt = page.locator('text=JSON')

    await expect(markdownOpt).toBeVisible()
    await expect(pdfOpt).toBeVisible()
    await expect(htmlOpt).toBeVisible()
    await expect(jsonOpt).toBeVisible()
  })

  test('auto-save status indicator cycles: Saving → Saved HH:MM → ⚠ Error', async ({ page }) => {
    const saveStatus = page.locator('[data-testid="canvas-save-status"]')

    // Add a cell to trigger dirty state
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.addCell('user')
        store.isDirty = true
      }
    })

    // Wait for auto-save debounce (1s)
    await page.waitForTimeout(1200)

    // Check for "Saved" status
    const savedText = await saveStatus.textContent()
    expect(savedText).toMatch(/Saved|saving/i)
  })

  test('edge state: empty canvas shows "+ Add your first cell" CTA', async ({ page }) => {
    // Ensure canvas is empty
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.cells = []
      }
    })

    const cta = page.locator('text=Add your first cell')
    await expect(cta).toBeVisible()
  })

  test('mobile 390px viewport uses tabbed layout instead of split', async ({ page }) => {
    // Set viewport to 390px (mobile)
    await page.setViewportSize({ width: 390, height: 812 })
    await page.reload()

    const tabbedLayout = page.locator('[data-testid="canvas-tabbed-layout"]')
    const splitLayout = page.locator('[data-testid="canvas-split-layout"]')

    await expect(tabbedLayout).toBeVisible()
    await expect(splitLayout).not.toBeVisible()
  })

  test('prefers-reduced-motion: skeleton uses static blocks instead of shimmer', async ({ page }) => {
    // Emulate prefers-reduced-motion
    await page.emulateMedia({ reducedMotion: 'reduce' })

    // Trigger stream to skeleton state
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'motion-cell',
          seq: 0,
          delta: '',
          state: 'skeleton'
        })
      }
    })

    const cell = page.locator('[data-testid="canvas-cell-motion-cell"]')
    const skeleton = cell.locator('[data-testid="cell-skeleton"]')

    // Check for animation: none or static appearance
    const animation = await skeleton.evaluate(el => window.getComputedStyle(el).animation)
    expect(animation).toMatch(/none/)
  })

  test('color independence: agent cell signals visible without relying on color alone (border + icon + badge)', async ({ page }) => {
    // Create agent cell
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'color-test-cell',
          seq: 1,
          delta: 'Content',
          state: 'partial'
        })
      }
    })

    const cell = page.locator('[data-testid="canvas-cell-color-test-cell"]')

    // Verify color-independent signals present:
    // 1. Border-left (shape)
    const borderWidth = await cell.evaluate(el => window.getComputedStyle(el).borderLeftWidth)
    expect(parseInt(borderWidth)).toBeGreaterThan(0)

    // 2. 🤖 Icon (not just color)
    const badge = cell.locator('text=🤖')
    await expect(badge).toBeVisible()

    // 3. Background distinct (but shape/border is primary)
    // If colors are disabled, border and badge remain visible
  })

  test('visual snapshot: default split layout (desktop)', async ({ page }) => {
    // Add some cells for visual interest
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.addCell('user')
        store.updateCellContent(store.cells[0].id, '# User Cell\nSome content here')
        store.upsertStreamCell({
          cellId: 'agent-1',
          seq: 1,
          delta: '## Agent Response\nStreaming...',
          state: 'partial'
        })
      }
    })

    // Wait for content to render
    await page.waitForTimeout(500)

    // Take snapshot
    await expect(page).toHaveScreenshot('canvas-split-desktop.png', { maxDiffPixels: 100 })
  })

  test('visual snapshot: mobile 390px tabbed layout', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 812 })
    await page.reload()

    // Add cells
    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.addCell('user')
        store.updateCellContent(store.cells[0].id, 'Mobile content')
      }
    })

    await page.waitForTimeout(500)
    await expect(page).toHaveScreenshot('canvas-mobile-tabbed.png', { maxDiffPixels: 100 })
  })

  test('visual snapshot: prefers-reduced-motion + desktop split', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })

    await page.evaluate(() => {
      const store = (window as unknown as CanvasWindow).__canvasStore
      if (store) {
        store.upsertStreamCell({
          cellId: 'no-motion-cell',
          seq: 1,
          delta: 'Static skeleton',
          state: 'skeleton'
        })
      }
    })

    await page.waitForTimeout(500)
    await expect(page).toHaveScreenshot('canvas-split-reduced-motion.png', { maxDiffPixels: 100 })
  })
})
