---
type: fix
scope: frontend
issue: 16888
pr: 0
---
`AdminMcpServersView.vue`'s two checkboxes used `class="checkbox-input"`, paired with the
existing `.checkbox-label` wrapper, but no rule for `.checkbox-input` existed anywhere --
`components.css` had the label half of the pair without the input half, so the checkboxes fell
back to unstyled native rendering. Added the missing rule to `components.css` (shared, so any
other admin view can adopt the same `.checkbox-label`/`.checkbox-input` pairing), matching the
`accent-color: var(--color-primary)` convention already used for checkboxes in
`AuditLogsView.vue` and `EvolutionView.vue`.
