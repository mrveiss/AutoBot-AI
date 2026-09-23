---
type: fix
scope: ci
issue: 16812
pr: 0000
---
install-git-hooks.sh now removes core.hooksPath whenever it is set, instead of only when its value fails to resolve to the default hooks dir. git behaves identically with or without the key, but pre-commit refuses to install while it merely exists ("Cowardly refusing to install hooks with core.hooksPath set"), so a redundant key pointing at the default silently disabled every hook declared in .pre-commit-config.yaml while reading as configuration hygiene. The lookup also moves to --get-all/--unset-all, since --unset fails on a multi-valued key and the old error suppression left it in place.
