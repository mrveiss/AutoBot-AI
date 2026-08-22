// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Gantt rendering: axis tick culling (#14769) and PNG export fidelity (#14767).
 *
 * #14769 — `axisTicks` emitted one `<line>` + `<text>` pair for the WHOLE data
 *   range regardless of what was on screen. At `zoom: 'day'` the step is one
 *   day and `pxPerDay` is 40, so a multi-year range produced thousands of
 *   elements, each carrying its own `toLocaleDateString` call.
 * #14767 — the export sized its canvas in CSS px (1x, soft on every retina
 *   screen), leaked its object URL whenever the image failed to load, and
 *   painted a hardcoded white backdrop under dark-theme chrome.
 *
 * The interaction between the two is the interesting part and has its own
 * test: culling must be SUSPENDED during an export, or the PNG silently ships
 * without the gridlines and date labels outside the viewport.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({
  route: { params: {} as Record<string, string>, query: {} as Record<string, string> },
  router: { replace: vi.fn() },
  api: { get: vi.fn(), patch: vi.fn() },
}))

vi.mock('vue-router', () => ({ useRoute: () => h.route, useRouter: () => h.router }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => h.api }))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ showToast: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import GanttTimelineView from '../GanttTimelineView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

/** One item spanning two years, so a day-zoom axis would run to ~730 ticks. */
const LONG_TIMELINE = {
  project_id: 'p1',
  items: [
    {
      id: 'w1',
      identifier: 'WI-1',
      title: 'Long haul',
      type: 'task',
      status: 'todo',
      scheduled_start: '2026-01-01T00:00:00Z',
      scheduled_end: '2027-12-31T00:00:00Z',
      started_at: null,
      completed_at: null,
      on_critical_path: false,
    },
  ],
  edges: [],
}

function wireApi() {
  h.api.get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/projects') return Promise.resolve([{ id: 'p1', name: 'Proj 1' }])
    if (url === '/api/llc/projects/p1/timeline') return Promise.resolve(LONG_TIMELINE)
    return Promise.reject(new Error(`unexpected url ${url}`))
  })
}

async function mountView() {
  const w = mount(GanttTimelineView, { global: { plugins: [i18n] } })
  await flushPromises()
  await flushPromises()
  return w
}

/**
 * Give `.gantt-scroll` a measurable viewport. jsdom reports `clientWidth` as 0
 * for every element, and the component treats an unmeasured viewport as
 * "render everything" — so without this a culling test would pass for the
 * wrong reason.
 */
async function setViewport(w: Awaited<ReturnType<typeof mountView>>, width: number, scrollLeft = 0) {
  const el = w.get('.gantt-scroll').element as HTMLElement
  // jsdom reports 0 for both and its `scrollLeft` setter does not stick, so
  // both are defined outright rather than assigned.
  Object.defineProperty(el, 'clientWidth', { value: width, configurable: true })
  Object.defineProperty(el, 'scrollLeft', { value: scrollLeft, configurable: true, writable: true })
  await w.get('.gantt-scroll').trigger('scroll')
  return el
}

function tickCount(w: Awaited<ReturnType<typeof mountView>>) {
  return w.findAll('.gantt-gridline').length
}

beforeEach(() => {
  h.route.params = { companyId: 'c1' }
  h.route.query = {}
  wireApi()
})

describe('axis ticks are culled to the viewport (#14769)', () => {
  it('renders the FULL range when the viewport cannot be measured', async () => {
    // The fallback, asserted first because it is the dangerous direction: an
    // unmeasurable viewport must not read as "nothing is visible". A chart
    // with no axis at all looks identical to a chart with no data.
    const w = await mountView()

    expect(tickCount(w)).toBeGreaterThan(50)
  })

  it('renders far fewer ticks once the viewport is known', async () => {
    const w = await mountView()
    const uncounted = tickCount(w)

    await setViewport(w, 1000)

    expect(tickCount(w)).toBeLessThan(uncounted)
    // Bounded by the window, not by the two-year range behind it.
    expect(tickCount(w)).toBeLessThan(50)
  })

  it('shows a different slice of the axis after scrolling', async () => {
    const w = await mountView()
    await setViewport(w, 1000, 0)
    const atStart = w.findAll('.gantt-axis-label').map((n) => n.text())

    await setViewport(w, 1000, 6000)
    const scrolled = w.findAll('.gantt-axis-label').map((n) => n.text())

    expect(scrolled.length).toBeGreaterThan(0)
    expect(scrolled).not.toEqual(atStart)
  })

  it('puts a tick on the same date whether or not culling is on', async () => {
    // Culling snaps its start back onto the step lattice, so a visible tick
    // must land on a date the unculled axis would also have produced.
    const w = await mountView()
    const all = new Set(w.findAll('.gantt-axis-label').map((n) => n.text()))

    await setViewport(w, 1000, 0)
    const visible = w.findAll('.gantt-axis-label').map((n) => n.text())

    expect(visible.length).toBeGreaterThan(0)
    expect(visible.every((label) => all.has(label))).toBe(true)
  })
})

describe('PNG export (#14767)', () => {
  const origCreate = URL.createObjectURL
  const origRevoke = URL.revokeObjectURL
  let revoked: string[]

  beforeEach(() => {
    revoked = []
    URL.createObjectURL = vi.fn(() => 'blob:gantt-test')
    URL.revokeObjectURL = vi.fn((u: string) => void revoked.push(u))
  })
  afterEach(() => {
    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
    vi.unstubAllGlobals()
    // `stubCanvas` spies on `document.createElement`; leaving that installed
    // would hand the next file's mounts a fake canvas.
    vi.restoreAllMocks()
  })

  /**
   * Replace the off-DOM canvas and anchor with inspectable stubs.
   *
   * jsdom's `getContext('2d')` returns null without the native `canvas`
   * package, and the export bails on a null context — so without this the
   * happy path cannot be reached at all and every assertion below would pass
   * vacuously. Any other tag falls through to the real implementation, so
   * Vue's own rendering is untouched.
   */
  function stubCanvas() {
    const ctx = {
      fillStyle: '',
      scale: vi.fn(),
      fillRect: vi.fn(),
      drawImage: vi.fn(),
    }
    const canvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ctx),
      toDataURL: vi.fn(() => 'data:image/png;base64,STUB'),
    }
    const link = { download: '', href: '', click: vi.fn() }
    const real = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      if (tag === 'canvas') return canvas as unknown as HTMLCanvasElement
      if (tag === 'a') return link as unknown as HTMLAnchorElement
      return real(tag)
    }) as typeof document.createElement)
    return { ctx, canvas, link }
  }

  /** Let the off-DOM `new Image()` resolve, exercising the success path. */
  function passImageLoad() {
    vi.stubGlobal(
      'Image',
      class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        set src(_v: string) {
          setTimeout(() => this.onload?.(), 0)
        }
      },
    )
  }

  /**
   * Pin the SVG's reported CSS size.
   *
   * jsdom's SVG support does not reliably provide `width.baseVal`, so the
   * dimensions the export reads are defined outright. This also makes the
   * scale assertions exact rather than dependent on layout maths that jsdom
   * would not perform anyway.
   */
  function pinSvgSize(w: Awaited<ReturnType<typeof mountView>>, cssW: number, cssH: number) {
    const svg = w.get('svg.gantt-svg').element
    Object.defineProperty(svg, 'width', { value: { baseVal: { value: cssW } }, configurable: true })
    Object.defineProperty(svg, 'height', { value: { baseVal: { value: cssH } }, configurable: true })
  }

  /** Resolve `--bg-surface` to `value` for the duration of a test. */
  function stubToken(value: string) {
    vi.stubGlobal(
      'getComputedStyle',
      () => ({ getPropertyValue: () => value }) as unknown as CSSStyleDeclaration,
    )
  }

  async function runExport(w: Awaited<ReturnType<typeof mountView>>) {
    await w.get('[data-testid="gantt-export-png"]').trigger('click')
    await flushPromises()
    await new Promise((r) => setTimeout(r, 5))
    await flushPromises()
  }

  /** Make the off-DOM `new Image()` reject, exercising the failure path. */
  function failImageLoad() {
    vi.stubGlobal(
      'Image',
      class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        set src(_v: string) {
          setTimeout(() => this.onerror?.(), 0)
        }
      },
    )
  }

  it('releases the object URL even when the image fails to load', async () => {
    // Before #14767 the revoke sat after the `await`, so a rejection jumped
    // straight to the catch and the blob leaked for the life of the document.
    failImageLoad()
    const w = await mountView()

    await runExport(w)

    expect(revoked).toContain('blob:gantt-test')
  })

  it('sizes the canvas by devicePixelRatio rather than exporting at 1x', async () => {
    // The defect: the canvas was sized in CSS px, so every export was 1x and
    // soft on any retina screen. With DPR 2 and an oversample of 2 the chart
    // should come out at 4x its CSS size.
    vi.stubGlobal('devicePixelRatio', 2)
    stubToken('#101010')
    passImageLoad()
    const { ctx, canvas, link } = stubCanvas()
    const w = await mountView()
    pinSvgSize(w, 440, 66)

    await runExport(w)

    expect(canvas.width).toBe(440 * 4)
    expect(canvas.height).toBe(66 * 4)
    // The context is scaled to match, so every drawing coordinate below stays
    // in CSS units — otherwise the chart would be drawn into one quadrant.
    expect(ctx.scale).toHaveBeenCalledWith(4, 4)
    expect(ctx.drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 440, 66)
    expect(link.click).toHaveBeenCalled()
  })

  it('never scales below 1x, so a very wide chart exports whole rather than cropped', async () => {
    // The cap exists because browsers refuse canvases past a dimension limit.
    // Clamping must floor at 1x: a soft complete export beats a sharp
    // truncated one.
    vi.stubGlobal('devicePixelRatio', 3)
    stubToken('#101010')
    passImageLoad()
    const { canvas } = stubCanvas()
    const w = await mountView()
    pinSvgSize(w, 40000, 66)

    await runExport(w)

    expect(canvas.width).toBe(40000)
    expect(canvas.height).toBe(66)
  })

  it('paints the active theme surface, not a hardcoded white', async () => {
    vi.stubGlobal('devicePixelRatio', 1)
    stubToken('#123456')
    passImageLoad()
    const { ctx } = stubCanvas()
    const w = await mountView()
    pinSvgSize(w, 440, 66)

    await runExport(w)

    expect(ctx.fillStyle).toBe('#123456')
  })

  it('falls back to white when the theme token resolves to nothing', async () => {
    vi.stubGlobal('devicePixelRatio', 1)
    stubToken('')
    passImageLoad()
    const { ctx } = stubCanvas()
    const w = await mountView()
    pinSvgSize(w, 440, 66)

    await runExport(w)

    expect(ctx.fillStyle).toBe('#ffffff')
  })

  it('serialises the WHOLE axis, not the culled slice', async () => {
    // The interaction between the two issues in this PR. With culling active,
    // an export that did not suspend it would ship a PNG missing every
    // gridline outside the viewport — and both a complete and a gutted export
    // look identical from the outside, so only a test catches it.
    vi.stubGlobal('devicePixelRatio', 1)
    stubToken('#101010')
    let ticksAtSerialise = -1
    vi.stubGlobal(
      'XMLSerializer',
      class {
        serializeToString(node: Node) {
          ticksAtSerialise = (node as Element).querySelectorAll('.gantt-gridline').length
          return '<svg/>'
        }
      },
    )
    passImageLoad()
    stubCanvas()
    const w = await mountView()
    const uncounted = tickCount(w)
    await setViewport(w, 1000)
    expect(tickCount(w)).toBeLessThan(uncounted)
    pinSvgSize(w, 440, 66)

    await runExport(w)

    expect(ticksAtSerialise).toBe(uncounted)
  })

  it('restores tick culling after a failed export rather than leaving the axis unculled', async () => {
    // `exporting` suspends culling; if it were only reset on the happy path a
    // failed export would silently leave every tick rendered from then on.
    failImageLoad()
    const w = await mountView()
    await setViewport(w, 1000)
    const culled = tickCount(w)

    await runExport(w)

    expect(tickCount(w)).toBe(culled)
  })
})
