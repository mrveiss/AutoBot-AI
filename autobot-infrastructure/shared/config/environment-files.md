# AutoBot Environment Files

The env-file family is described once, in
[`docs/developer/ENV_VARS.md`, "Env-file family"](../../../docs/developer/ENV_VARS.md#env-file-family):

- which file each deployment reads (`docker/.env.docker` for Docker, `.env.base` plus one overlay
  for native installs, `.env.example` as the annotated reference);
- the load order (base first, then one overlay);
- the host-key format rule;
- the guard that enforces it (`repo_tests/env_file_family_18555_test.py`).

This page used to repeat that with details that had gone stale, and it is kept only as a pointer
to the one description (#18917).
