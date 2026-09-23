---
type: security
scope: secrets
issue: 16299
pr: 0000
---
Guard `.secrets.baseline` so every entry carries a tracked reason: the 5 guessable defaults named in #16299 get a real, specific reason each; every other pre-existing entry is one disclosed, frozen "legacy, unreviewed" reason (full audit tracked at #17034); a new entry added afterward must carry a real reason or the guard fails.
