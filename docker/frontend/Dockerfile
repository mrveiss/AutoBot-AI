# AutoBot Frontend - Vue 3 + nginx (#1809)
# Node build stage + Ubuntu 22.04 nginx for serving
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Build main frontend ----
FROM node:20-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
# autobot-plugins/ must be present at /autobot-plugins/ before npm ci because
# package-lock.json references file:../autobot-plugins/terminal and ../vnc
COPY autobot-plugins/ /autobot-plugins/
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
FROM node:20-bookworm-slim AS slm-builder

WORKDIR /app

# Install dependencies
COPY autobot-slm-frontend/package.json autobot-slm-frontend/package-lock.json ./
# Copy shared module (referenced by @shared alias)
COPY autobot_shared/ /autobot_shared/
RUN npm ci

# Copy source and build with /slm/ base path
COPY autobot-slm-frontend/ ./

# Set API URL prefix so fetch('/slm/api/...') hits the SLM backend via nginx
ENV VITE_API_URL=/slm
RUN npx vite build --base /slm/


# ---- Production stage ----
FROM ubuntu:22.04 AS production

ENV DEBIAN_FRONTEND=noninteractive

# Install nginx
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx wget \
    && rm -rf /var/lib/apt/lists/*

# Copy built main frontend
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# Copy built SLM frontend under /slm/
COPY --from=slm-builder /app/dist/ /usr/share/nginx/html/slm/

# Copy nginx config (main + shared includes)
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/nginx-common.conf /etc/nginx/nginx-common.conf
COPY docker/nginx/nginx-locations.conf /etc/nginx/nginx-locations.conf

# Create cache directories
RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R www-data:www-data /var/cache/nginx /var/run /usr/share/nginx/html

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
