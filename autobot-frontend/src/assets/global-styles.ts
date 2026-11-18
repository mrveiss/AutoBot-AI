// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The app's global stylesheets, in load order (#18687).
 *
 * `main.ts` and Storybook's `.storybook/preview.ts` both import this module, so the
 * app and its stories load the same CSS from one list. They used to keep two lists:
 * when `assets/main.css` was folded away (#17613), Storybook kept importing it,
 * could no longer build, and visual regression compared nothing.
 * repo_tests/storybook_loads_the_app_styles_18687_test.py keeps the two importers.
 */
import './tailwind.css'
import './vue-notus.css'
// Fonts from local npm packages (avoid CDN tracking prevention warnings)
import '@fortawesome/fontawesome-free/css/all.min.css'
// Import only latin subset with weights actually used (400, 500, 600, 700)
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'

// Legacy view styles - loaded BEFORE the design system so its tokens win (theme.css retired into design-tokens.css, #14785)
import './styles/view.css'

// Import CSS Design System (Issue #704/#901) - SSOT - must come AFTER legacy to override
import './css/index.css'

// Interaction polish — shell press feedback + stronger easing (#10488 B2)
import './css/interaction-polish.css'

// Global reset (* { margin:0; padding:0; box-sizing:border-box }, body { margin:0;
// min-height:100vh }) — must load AFTER vue-notus and component packages so their
// leaked unscoped body{padding...} rules can't push the layout off-viewport.
// Without this, the page does not fill the viewport and views without
// .view-container don't scroll properly.
import './base.css'

// @autobot/ui shared kit: token contract fallbacks first, then the kit's one
// adapter (mapping --aui-* onto the shared semantic token names, which this app
// defines in the design-system CSS above). Loaded AFTER that CSS so the tokens
// the adapter references are already defined (#10750 C2c, #10860 Task-C).
import '@autobot/ui/tokens'
import '@autobot/ui/adapter'

// xterm's stylesheet, global so terminal views need no per-component import
import '@xterm/xterm/css/xterm.css'
