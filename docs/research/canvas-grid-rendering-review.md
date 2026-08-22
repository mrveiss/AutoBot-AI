# Canvas & grid rendering review

A review of how AutoBot's grid-based drawing surfaces — the workflow/org node
canvas, the LLC Gantt, and the graph charts — hold up against established
techniques for interactive canvas rendering. Prompted by a study of an
external browser-based isometric grid renderer; that source is not named here
per the repo convention against external product and author names in docs. The
techniques below are general and are described on their own terms.

Every finding is filed. Issue links are at the bottom.

---

## The techniques worth measuring against

**Layered caching with version-counter invalidation.** Split the scene into
layers by how often each changes (static backdrop, static content, the one
thing currently moving). Rebuild a layer only when a monotonic version counter
on its data changes. Composite per frame. An idle scene then costs nothing.

**Pan/zoom as a pure transform.** If every world layer lives in one coordinate
frame, panning and zooming is a transform change plus a composite — no layer is
ever invalidated by camera movement. This only holds if everything that belongs
to the world is *inside* that transform, and only chrome is outside it.

**Derive resolution budgets from the worst case, then cap them.** Do not guess
a supersample factor. Compute it from `max_zoom x devicePixelRatio`, cap it
against the platform's real limit (canvas dimension ceilings), and write the
arithmetic into the comment so the number can be re-derived rather than
cargo-culted.

**Move per-frame work to load time.** Anything expensive and static — blurs,
silhouettes, resampling — is computed once and reduced to a transformed blit.
The corollary is that this becomes a load-bearing invariant, and needs a test,
not a comment asking contributors to respect it.

**Index the lookups on the hot path.** A per-item linear scan inside a
per-frame or per-drag computation is the classic O(N x M) trap. It is
invisible at demo scale and dominant at real scale.

**Quantise placement to the grid you draw.** A grid that positions nothing is
decoration. Snapping makes it load-bearing.

**Infer missing metadata by measurement.** Where generated or third-party
assets carry no geometry metadata, measure it from the pixels and normalise
away whatever will not tile — rather than trusting the producer to be
consistent.

---

## Where AutoBot draws on a grid

| Surface | File | Technique |
|---|---|---|
| Workflow / org node canvas | `autobot-frontend/src/components/workflow/WorkflowCanvas.vue` | Absolutely-positioned DOM nodes, SVG bezier edges, CSS-transform pan/zoom, CSS grid background |
| Shared canvas geometry | `autobot-frontend/src/components/workflow/canvasNode.ts` | Constants SSOT |
| Org graph host | `autobot-frontend/src/views/llc/OrgChart.vue` | Owns node positions |
| LLC Gantt | `autobot-frontend/src/views/llc/GanttTimelineView.vue` | Hand-built SVG grid + canvas PNG export |
| Call / knowledge graphs | `autobot-frontend/src/components/charts/FunctionCallGraph.vue`, `components/knowledge/KnowledgeGraph.vue` | Cytoscape |

`WorkflowCanvas.vue` is the surface these techniques bear on most directly: our
own grid, our own pan/zoom, our own hit-testing, our own edge geometry.

---

## What we already do as well or better

- **Narrow-dependency invalidation beats a hand-maintained counter.**
  `OrgChart.vue`'s `layoutKey` is a computed built from an explicit, shallow
  projection of ids/nesting/labels and deliberately *not* `status`. Because it
  is derived, no mutation path can forget to bump it — the failure mode a
  manual version integer always carries. It exists because a status write once
  rebuilt the graph and discarded every dragged position (#13996).

- **Derived geometry constants, with the failure recorded.**
  `CANVAS_NODE_PORT_Y = CANVAS_NODE_HEIGHT / 2` is derived rather than written
  as `50`, because the two were independent literals and changing the height
  detached every edge from its node while failing no test (#14690).

- **A deliberate chrome boundary.** Pan/zoom is transform-only, and the legend,
  minimap and instructions block are documented as intentionally outside the
  transform. Most canvas code does not reason about that line at all.

- **Undo/redo at gesture granularity.** A whole drag is one history entry, not
  one per pointer tick (#14612).

- **Accessibility and i18n.** Roving tabindex, focus trap/restore, keyboard
  node movement, every string through `$t`. A canvas-only surface has none of
  this for free.

- **Interaction test coverage.** 20+ test files for `WorkflowCanvas` alone.

---

## What was missing, and is now fixed

**The grid was chrome, not world content** (#14765). It was painted on
`.canvas-area` — the fixed viewport — while the pan/zoom transform lived on its
child `.canvas-content`. At 2x zoom the squares stayed 20 screen px while every
node doubled, and panning slid nodes across a stationary backdrop. The file
already reasoned about that boundary correctly for the legend and minimap; the
grid was grouped with them by accident. Now bound to `zoom`/`pan`.

**Nothing snapped to the grid we drew** (#14768). Positions were arbitrary
floats. `CANVAS_GRID_SIZE` is now the single definition behind the CSS
background, the drag snap, and the keyboard step. Two decisions worth
recording:

- A drop snaps *both* axes, including one the pointer did not move. Exempting
  an unmoved axis leaves nodes half-aligned indefinitely.
- Keyboard is deliberately not symmetric: an arrow press aligns to the
  *adjacent* gridline and leaves the idle axis alone. `snap(position + step)`
  overshoots the line it was reaching for.

**Node width was defined in CSS and predicted in TypeScript** (#14726). Four
functions guessed at a value only the CSS actually set. `nodeStyle()` now
supplies it from the constant.

**Edge targets were resolved by scanning** (#14766). `connections` ran
`props.nodes.find(...)` per edge — O(N x E) on the drag hot path, where a
pointer tick triggers a position write which re-triggers the computed. Now
indexed, first-wins so a duplicate id resolves exactly as `find` did.

**The Gantt export was 1x, leaked its blob URL, and hardcoded white** (#14767).
Now scaled from `devicePixelRatio` with a canvas-dimension cap, revoked in a
`finally`, and painted with the active theme's surface token.

**Gantt axis ticks ignored the viewport** (#14769). One tick per step across
the whole range; at day zoom over a multi-year range, thousands of SVG elements
each with a `toLocaleDateString` call. Now culled to the visible window — with
the fallback that an *unmeasurable* viewport renders the full range, because an
empty axis is indistinguishable from a chart with no data.

---

## Still open

**JS-driven motion ignores `prefers-reduced-motion`** (#14770). The CSS side is
global — a universal kill switch in `assets/base.css`. A media query cannot
reach motion a script starts: smooth scroll fires on every route navigation,
and both graph components run their layout with `animate: true`. A force layout
animating to equilibrium on every load is the largest piece of uncontrolled
motion in the app, and it fires for the users who asked for less of it.

**No safe-area inset handling anywhere** (#14771). Zero occurrences across the
frontend, and the viewport meta lacks `viewport-fit=cover` — while 123 files
carry breakpoint logic, a dedicated touch control exists, and the canvas has a
full pinch/long-press gesture stack. Bottom-anchored fixed chrome sits under
the home indicator; toasts are the sharpest case.

---

## Considered and rejected

**Splitting static from moving during a drag.** Only edges incident to the
dragged nodes change, so a static/live split would cut per-move cost. It also
means two code paths producing edge geometry that must agree — precisely the
drift failure `CANVAS_NODE_PORT_Y` exists to prevent. Deferred until a profile
taken *after* #14766 shows the pressure is still there.

**rAF-coalescing pointer moves.** Would cap work at the refresh rate rather
than the pointer rate. But the gesture logic reads the live event per tick, and
the semantics of several fixes are encoded in *when* the threshold checks fire;
deferring the emit without deferring the bookkeeping would resurrect those
bugs. Coalesce the emit only, if at all.

**Per-material interaction feedback.** Not a fit for this product. The
transferable half — debounce per channel rather than globally — is only worth
revisiting if canvas actions ever flood the toast bus.

---

## Not gaps

Recorded so the same ground is not re-searched: determinate progress
(`ProgressBar.vue` with percentages, skeletons across 16 components), CSS-side
reduced-motion, theming with a reactive `prefers-color-scheme` listener, i18n
across 11 locales, and offline/permission degradation paths. These are all
places our surfaces are ahead of the general pattern, not behind it.

---

## Issues

| # | Status |
|---|---|
| #14765 grid does not pan or zoom with the graph | closed |
| #14768 grid drawn but nothing snaps to it | closed |
| #14726 node size in CSS and in the test's own math | closed |
| #13961 literal colours bypassing theme tokens | closed |
| #14103 order-dependent RTL pan assertion | closed |
| #14766 edge targets resolved by an O(N) scan | closed |
| #14767 PNG export is 1x, leaks its blob URL, hardcodes white | open |
| #14769 axis ticks generated for the whole range | open |
| #14770 JS-driven motion ignores `prefers-reduced-motion` | open |
| #14771 no safe-area inset handling | open |
