---
type: security
scope: redis
issue: 16678
pr: 0
---
Every Ansible-rendered Redis client now sends a username with its password, `default` unless one is configured. That covers the AI stack's environment, both deploy playbooks' `redis-cli` checks and container healthcheck, and the units' `REDIS_USERNAME`. A password sent alone is refused while the server's default user needs no password. The legacy `deploy-native.sh` and `deploy-hybrid.sh` no longer write a hardcoded Redis password (#16686). They read the SLM-generated one instead, and a repo guard now rejects any literal Redis password in a shell script.
