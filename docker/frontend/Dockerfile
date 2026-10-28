# AutoBot Frontend - Vue 3 + nginx (#1809)
# Node build stage + Ubuntu 22.04 nginx for serving
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# #13783: npm's defaults give a registry reset one short retry, and a bare
# `npm ci` failing takes the whole image build — and with it hardened-smoke-test
# — down on PRs that touch no frontend file. The runner is a singleton, so
# several PRs building at once is exactly when the resets appear. Declared once
# as ARGs and passed into both builder stages via ENV, rather than repeated as
# `npm config set` per stage.
ARG NPM_FETCH_RETRIES=5
ARG NPM_FETCH_RETRY_MINTIMEOUT=20000
ARG NPM_FETCH_RETRY_MAXTIMEOUT=120000

# ---- Build main frontend ----
# Node.js major: pinned to the repo-root .nvmrc by repo_tests/node_major_one_home_19328_test.py (#19328).
ARG NODE_MAJOR=22
FROM node:${NODE_MAJOR}-bookworm-slim AS builder

ARG NPM_FETCH_RETRIES
ARG NPM_FETCH_RETRY_MINTIMEOUT
ARG NPM_FETCH_RETRY_MAXTIMEOUT
ENV NPM_CONFIG_FETCH_RETRIES=$NPM_FETCH_RETRIES \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=$NPM_FETCH_RETRY_MINTIMEOUT \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=$NPM_FETCH_RETRY_MAXTIMEOUT

WORKDIR /app

# Install dependencies first (better layer caching)
# autobot-plugins/ must be present at /autobot-plugins/ before npm ci because
# package-lock.json references file:../autobot-plugins/terminal and ../vnc
COPY autobot-plugins/ /autobot-plugins/
# libs/ must be present at /libs/ before npm ci because package-lock.json
# references file:../libs/autobot-ui (@autobot/ui shared kit), resolved from /app/
COPY libs/ /libs/
COPY autobot-frontend/package.json autobot-frontend/package-lock.json ./
RUN npm ci

# Copy source and build
COPY autobot-frontend/ ./

# Build-time env vars for Vite (overridable via --build-arg)
# Empty defaults = proxy mode: frontend uses relative URLs through nginx,
# which reverse-proxies /api/* to the backend container.
ARG VITE_BACKEND_HOST=
ARG VITE_BACKEND_PORT=
ARG VITE_HTTP_PROTOCOL=

RUN npm run build


# ---- Build SLM frontend ----
FROM node:${NODE_MAJOR}-bookworm-slim AS slm-builder

# Same retry posture as the main builder (#13783) — a stage does not inherit
# another stage's ENV, so the ARGs are re-declared rather than assumed.
ARG NPM_FETCH_RETRIES
ARG NPM_FETCH_RETRY_MINTIMEOUT
ARG NPM_FETCH_RETRY_MAXTIMEOUT
ENV NPM_CONFIG_FETCH_RETRIES=$NPM_FETCH_RETRIES \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=$NPM_FETCH_RETRY_MINTIMEOUT \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=$NPM_FETCH_RETRY_MAXTIMEOUT

WORKDIR /app

# Install dependencies
# autobot-plugins/ must be at /autobot-plugins/ because package-lock.json
# references file:../autobot-plugins/terminal and ../vnc (resolved from /app/)
COPY autobot-plugins/ /autobot-plugins/
# libs/ must be present at /libs/ before npm ci because package-lock.json now
# references file:../libs/autobot-ui (@autobot/ui shared kit, #12019), resolved
# from /app/ — same requirement as the main-frontend builder stage above.
COPY libs/ /libs/
COPY autobot-slm-frontend/package.json autobot-slm-frontend/package-lock.json ./
# Copy shared module (referenced by @shared alias)
COPY autobot_shared/ /autobot_shared/
RUN npm ci

# Copy source and build with /slm/ base path
COPY autobot-slm-frontend/ ./

# Set API URL prefix so fetch('/slm/api/...') hits the SLM backend via nginx
ENV VITE_API_URL=/slm
RUN npx vite build --base /slm/


# ---- nginx base, shared by the SLM-only GUI and the full frontend (#18585) ----
FROM ubuntu:22.04 AS nginx-base

ENV DEBIAN_FRONTEND=noninteractive

# apt retries, and an index failure is fatal at `apt-get update` (#16291)
COPY docker/apt/80-autobot-resilience /etc/apt/apt.conf.d/80-autobot-resilience

# Install nginx
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx wget \
    && rm -rf /var/lib/apt/lists/*

# Shared nginx includes: http-block settings + SLM upstream, and the SLM routes
COPY docker/nginx/nginx-common.conf /etc/nginx/nginx-common.conf
COPY docker/nginx/nginx-slm-locations.conf /etc/nginx/nginx-slm-locations.conf
# TLS settings and the port-80 redirect server, shared by both TLS configs (#18593)
COPY docker/nginx/nginx-tls.conf /etc/nginx/nginx-tls.conf
COPY docker/nginx/nginx-tls-redirect.conf /etc/nginx/nginx-tls-redirect.conf

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]

# ---- SLM-only GUI (#18585) ----
# `--target slm-gui` builds only the SLM frontend — the main-frontend builder
# stage is skipped — and serves it with no dependency on the main backend.
FROM nginx-base AS slm-gui

COPY --from=slm-builder /app/dist/ /usr/share/nginx/html/slm/
COPY docker/nginx/nginx-slm.conf /etc/nginx/nginx.conf

RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R www-data:www-data /var/cache/nginx /var/run /usr/share/nginx/html

# ---- Production stage (full frontend; last, so it stays the default target) ----
FROM nginx-base AS production

# Copy built main frontend
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# Copy built SLM frontend under /slm/
COPY --from=slm-builder /app/dist/ /usr/share/nginx/html/slm/

# Copy nginx config (main + full-stack includes)
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/nginx-backend-upstream.conf /etc/nginx/nginx-backend-upstream.conf
COPY docker/nginx/nginx-locations.conf /etc/nginx/nginx-locations.conf

# Create cache directories
RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R www-data:www-data /var/cache/nginx /var/run /usr/share/nginx/html
