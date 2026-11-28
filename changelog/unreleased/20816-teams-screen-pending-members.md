---
type: fix
scope: frontend
issue: 20816
pr: 21005
---
The Company OS Teams screen now shows its teams as soon as the teams read answers, with member names and roles shown as a loading placeholder until the members read arrives, and the role column is translated through the same label MembersView uses. The SLM theme list ignores an older response that arrives after a newer one, and its malformed-list error is a translated message.
