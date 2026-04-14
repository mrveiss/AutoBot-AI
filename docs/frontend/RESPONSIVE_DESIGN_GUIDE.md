# Responsive Design Guide

> Implemented in issue #1804. Reference files: `autobot-frontend/src/assets/main.css`,
> `autobot-frontend/src/components/chat/ChatInterface.vue`,
> `autobot-frontend/src/components/chat/ChatHeader.vue`.

---

## Breakpoints

AutoBot uses Tailwind CSS's default breakpoint scale. All breakpoints apply
upward (mobile-first).

| Prefix | Min-width | Typical target |
|--------|-----------|----------------|
| (none) | 0 px | Phones in portrait |
| `sm` | 640 px | Phones in landscape, small tablets |
| `md` | 768 px | Tablets |
| `lg` | 1024 px | Laptops, desktops |
| `xl` | 1280 px | Wide desktop monitors |
| `2xl` | 1536 px | Extra-wide monitors |

The most load-bearing breakpoint in the chat UI is `lg` (1024 px). Below `lg`
the sidebar is hidden and replaced by the mobile overlay; above `lg` it is
always visible inline.

An extra-small cutoff at `480 px` tightens `.page-header` padding in
`main.css` for very narrow phones.

---

## Mobile Navigation

### Pattern

On screens narrower than `lg`, the chat sidebar is hidden from the normal
document flow (`hidden lg:block`). A hamburger button in `ChatHeader` emits
`toggle-mobile-sidebar`. `ChatInterface` toggles the `showMobileSidebar`
boolean, which controls both the slide-in sidebar overlay and the backdrop.

### showMobileSidebar State

`showMobileSidebar` is a `ref<boolean>` owned by `ChatInterface.vue`.
It is set to `false` on initial mount and has no reset logic tied to viewport
resize (see open issue #4446).

| Action | Result |
|--------|--------|
| Tap hamburger button | `showMobileSidebar = !showMobileSidebar` |
| Tap backdrop | `showMobileSidebar = false` |
| Sidebar emits `close-mobile` | `showMobileSidebar = false` |

---

## Chat Interface on Mobile

### Backdrop Overlay

```html
<div
  v-if="showMobileSidebar"
  class="lg:hidden fixed inset-0 bg-black/40 z-40"
  @click="showMobileSidebar = false"
  aria-hidden="true"
></div>
```

- `fixed inset-0` covers the full viewport.
- `bg-black/40` dims the chat area at 40% opacity.
- `z-40` sits above normal content but below the sidebar (`z-50` if needed).
- `aria-hidden="true"` hides the overlay from assistive technology.
- A click anywhere on the backdrop closes the sidebar.

### Sidebar Slide-In Transition

Vue's `<Transition>` component wraps the mobile sidebar overlay:

```html
<Transition
  enter-active-class="transition duration-250 ease-out"
  enter-from-class="-translate-x-full"
  enter-to-class="translate-x-0"
  leave-active-class="transition duration-200 ease-in"
  leave-from-class="translate-x-0"
  leave-to-class="-translate-x-full"
>
  <div
    v-if="showMobileSidebar"
    class="lg:hidden fixed top-0 left-0 h-full w-80 max-w-[85vw] z-40 shadow-2xl overflow-hidden"
  >
    <ChatSidebar @close-mobile="showMobileSidebar = false" />
  </div>
</Transition>
```

Key sizing decisions:
- `w-80` (320 px) is the fixed width on `sm`+.
- `max-w-[85vw]` prevents the sidebar from consuming the full screen width on
  very narrow phones, leaving a visible sliver of backdrop for easy dismissal.
- Duration: 250 ms open, 200 ms close — asymmetric to feel snappy on dismiss.

Note: `main.css` includes `@media (prefers-reduced-motion: reduce)` which
collapses all transition durations to `0.01ms`, so the slide animation is
suppressed for users who have requested reduced motion at the OS level.

### ChatHeader Hamburger

`ChatHeader.vue` renders the hamburger only below `lg`:

```html
<button
  class="header-btn lg:hidden shrink-0"
  :aria-label="$t('chat.sidebar.expandSidebar')"
  @click="$emit('toggle-mobile-sidebar')"
>
  <i class="fas fa-bars"></i>
</button>
```

`lg:hidden` means the button is absent from the DOM on desktop, so there is no
risk of triggering the mobile overlay on large screens.

The session title and subtitle use responsive sizing:

```html
<h1 class="text-sm sm:text-lg font-semibold truncate">{{ currentSessionTitle }}</h1>
<p class="text-xs sm:text-sm text-autobot-text-muted truncate hidden sm:block">
  {{ sessionInfo }}
</p>
```

The subtitle (`sessionInfo`) is hidden below `sm` (640 px) to avoid cramping
the header. The connection status shows icon-only below `sm` and adds the text
label at `sm:inline`.

---

## Touch Targets

WCAG 2.5.5 requires interactive elements to have a minimum tap area of 44 x 44
logical pixels. `main.css` applies this globally below `lg`:

```css
@media (max-width: 1024px) {
  button,
  [role="button"],
  a {
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
  }
}
```

`touch-action: manipulation` disables the 300 ms double-tap delay that legacy
mobile browsers insert before firing a click. `-webkit-tap-highlight-color:
transparent` removes the default blue flash on iOS/Android.

For components that render small icon buttons (e.g., header action buttons in
`ChatHeader`), ensure the rendered hit area is at least 44 x 44 px by adding
padding rather than relying on the icon glyph size alone. The `.header-btn`
class in `ChatHeader.vue` achieves this via padding.

---

## CSS Utilities

Defined in `autobot-frontend/src/assets/main.css`.

### touch-action: manipulation

Applied to all `button`, `[role="button"]`, and `a` elements at `max-width:
1024px`. Eliminates double-tap delay and prevents unintended zoom on tap.

### -webkit-overflow-scrolling: touch

```css
@media (max-width: 1024px) {
  .overflow-y-auto,
  .overflow-x-auto {
    -webkit-overflow-scrolling: touch;
  }
}
```

Enables momentum-based (inertia) scrolling on iOS for any element with Tailwind
scroll classes. Without this, scrollable areas on iOS scroll at a fixed speed
with no deceleration.

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

This blanket rule covers all Vue `<Transition>` animations and CSS `transition`
properties. No per-component opt-out is needed; the OS preference is respected
automatically.

### Extra-Small Viewport Padding

```css
@media (max-width: 480px) {
  .page-header { padding: var(--spacing-3) var(--spacing-3) var(--spacing-2); }
  .page-actions { flex-wrap: wrap; }
}
```

Reduces page-header padding and wraps action bars on very small phones
(below 480 px). Apply `.page-header` and `.page-actions` to any new page-level
header/actions section to inherit this behaviour.

### RTL Support

The chat sidebar border flips for right-to-left layouts:

```css
[dir="rtl"] .chat-sidebar {
  border-right: none;
  border-left: 1px solid var(--border-color);
}
```

Code blocks always render left-to-right regardless of `dir` to preserve
indentation alignment.

---

## Component Checklist

Use the following checklist when making a new component mobile-responsive.

1. **Hide desktop-only elements below `lg`**: use `hidden lg:block` or
   `lg:hidden` as appropriate.
2. **Responsive text sizes**: use size pairs like `text-sm sm:text-lg` and
   `hidden sm:block` to progressively reveal detail.
3. **Responsive spacing**: use pairs like `px-3 sm:px-6` and `py-3 sm:py-4`
   to tighten gutters on small screens.
4. **Mobile overlay pattern** (if the component has a collapsible panel):
   - Backdrop: `fixed inset-0 bg-black/40 z-30`, `aria-hidden="true"`, tap to close.
   - Slide-in: `fixed top-0 left-0 h-full w-80 max-w-[85vw] z-40`.
   - Wrap with `<Transition>` using `-translate-x-full` / `translate-x-0`.
5. **Touch targets**: ensure all interactive elements have at least 44 x 44 px
   tap area. Prefer `padding` over margins; rely on the global `main.css` rule
   for `touch-action` and tap-highlight suppression.
6. **Scrollable containers**: use Tailwind `overflow-y-auto` / `overflow-x-auto`
   so the global `main.css` rule applies `-webkit-overflow-scrolling: touch`.
7. **No transition in `prefers-reduced-motion`**: the global CSS rule handles
   this automatically; do not add `@media (prefers-reduced-motion)` overrides
   inside scoped component styles.
8. **Test at 375 px, 640 px, and 1024 px** — the three critical widths for
   phone, small tablet, and the `lg` desktop breakpoint.

---

## Testing Mobile

### Browser DevTools Device Emulation

1. Open DevTools (F12) and click the device-toolbar icon (or Ctrl+Shift+M /
   Cmd+Shift+M).
2. Select a preset device or set a custom width.
3. Key widths to test:

| Width | Reason |
|-------|--------|
| 375 px | iPhone SE / most small phones |
| 390 px | iPhone 14 Pro |
| 430 px | iPhone 14 Pro Max |
| 480 px | `main.css` extra-small breakpoint |
| 640 px | Tailwind `sm` breakpoint — subtitle and connection-status text appear |
| 768 px | Tailwind `md` breakpoint |
| 1023 px | One pixel below `lg` — last state where mobile nav is active |
| 1024 px | Tailwind `lg` breakpoint — sidebar becomes inline, hamburger disappears |

4. Verify the hamburger appears below 1024 px and is absent at 1024 px+.
5. Tap the hamburger; confirm the sidebar slides in, the backdrop appears, and
   tapping the backdrop closes both.
6. Resize the window across the `lg` threshold while the sidebar is open;
   confirm no visual glitch (note: `showMobileSidebar` is not reset on resize —
   see issue #4446 for the fix backlog item).
7. Enable "Touch" emulation in DevTools to verify `touch-action: manipulation`
   eliminates the 300 ms click delay.
