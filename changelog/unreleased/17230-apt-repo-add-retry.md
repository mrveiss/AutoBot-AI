---
type: fix
scope: infra
issue: 17230
pr: 0000
---
Adding an apt repository during provisioning now retries with a bounded backoff, so one transient keyserver or repository-host failure (`gpg: keyserver receive failed`) no longer aborts the whole play. A repository that still cannot be added once the retries are spent stops the deploy as before, but now only after up to five attempts 10 seconds apart, so a permanent failure such as a mistyped or retired repository takes up to about 50 seconds longer to surface.
