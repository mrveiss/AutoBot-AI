/**
 * Re-export shim — the implementation lives in `@autobot/vnc` (#12653).
 *
 * `useVncControls` existed three times: here, in autobot-slm-frontend, and in
 * the shared plugin. #12931 made the shared copy accept an injected transport
 * and migrated `DesktopInterface.vue` onto it, which left this file with no
 * caller — an orphan created by that change rather than pre-existing drift.
 *
 * Re-exported rather than deleted so any straggler import keeps working; what
 * goes is the fork, not the callers. Both apps already depend on `@autobot/vnc`
 * (`file:../autobot-plugins/vnc`), so this resolves in each.
 */
export {
  useVncControls,
  type VncRequest,
  type UseVncControlsOptions,
  type MouseClickParams,
  type MouseDragParams,
  type MouseScrollParams,
  type VncActionResponse,
} from '@autobot/vnc'
