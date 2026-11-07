---
type: fix
scope: frontend
issue: 20425
---
Labels painted on a `--color-primary` fill read `--text-on-primary` instead of a literal white (chat image-generate button, work-item actions, SLM setup wizard step indicator), and a shrink-only ratchet in the hardcoded-colour guard fails on a new literal white label on a primary fill.
