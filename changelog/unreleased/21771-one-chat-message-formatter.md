---
type: fix
scope: frontend
issue: 21771
pr: 21774
---
Chat messages render through one shared formatter; a link at a line end no longer swallows the line break and next word into its href.
