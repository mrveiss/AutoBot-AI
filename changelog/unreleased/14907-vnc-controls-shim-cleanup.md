---
type: chore
scope: frontend
issue: 14907
pr: 0
---
`useVncControls` was already consolidated into one implementation (`autobot-plugins/vnc`,
#12931/#12653) — #14907's AC1 named the wrong target package (`@autobot/ui`), which is the only
reason it read as unmet. The two app-local files were thin re-export shims with zero callers
(#12978 had already migrated `DesktopInterface.vue` onto the shared copy directly, orphaning
them); removed both, plus the regression test whose entire subject was the shim (asserting it
re-exported the same function object as the canonical package) — the fork it guarded against is
now structurally impossible with one implementation, not two. `docs/adr/008` updated so its
citation of the two shim files' line numbers doesn't go stale.
