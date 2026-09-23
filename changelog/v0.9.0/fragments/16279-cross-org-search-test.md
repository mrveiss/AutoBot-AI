---
type: test
scope: user-management
issue: 16279
pr: 0
---
Added a real-database test proving `UserService.list_users`'s org scoping actually excludes another organisation's users from a sharing-dialog search — two orgs, two seeded users, a shared search term that would match both without the fix — completing #16279's last open criterion alongside the live-host probe already recorded on the issue.
