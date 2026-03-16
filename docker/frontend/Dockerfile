# AutoBot Frontend - Vue 3 + nginx (#1809)
# Node build stage + Ubuntu 22.04 nginx for serving
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Build stage ----
FROM node:20-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY autobot-frontend/package.json autobot-frontend/package-lock.json ./
RUN npm ci

# Copy source and build
COPY autobot-frontend/ ./

# Build-time env vars for Vite (overridable via --build-arg)
ARG VITE_BACKEND_HOST=autobot-backend
ARG VITE_BACKEND_PORT=8000
ARG VITE_HTTP_PROTOCOL=http

RUN npm run build


# ---- Production stage ----
FROM ubuntu:22.04 AS production

ENV DEBIAN_FRONTEND=noninteractive

# Install nginx
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx wget \
    && rm -rf /var/lib/apt/lists/*

# Copy built frontend
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# Copy nginx config
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf

# Create cache directories
RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R www-data:www-data /var/cache/nginx /var/run /usr/share/nginx/html

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
