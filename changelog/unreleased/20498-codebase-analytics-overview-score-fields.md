---
type: fix
scope: frontend
issue: 20498
pr: 21397
---
The Codebase Analytics overview reads the score and technical-debt fields its endpoints actually return, and shows a missing value as "not available" instead of 0.
