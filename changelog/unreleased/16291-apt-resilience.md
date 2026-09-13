---
type: fix
scope: docker
issue: 16291
pr: 16356
---
Image builds now retry a failed apt download. If a package index still can't be downloaded, the build stops at `apt-get update` with the unreachable URL in the error, instead of failing later at `apt-get install` with a misleading unmet-dependency message. The setting lives in one apt configuration file that every image stage uses.
