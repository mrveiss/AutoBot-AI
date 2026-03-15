# AutoBot Frontend - Vue 3 + nginx
# Multi-stage: build with Node, serve with nginx
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# ---- Build stage ----
FROM node:18-alpine AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY autobot-frontend/package.json autobot-frontend/package-lock.json ./
RUN npm ci

# Copy source and build
COPY autobot-frontend/ ./

# Build-time env vars for Vite (overridable via --build-arg)
ARG VITE_BACKEND_HOST=backend
ARG VITE_BACKEND_PORT=8000
ARG VITE_HTTP_PROTOCOL=http

RUN npm run build


# ---- Production stage ----
FROM nginx:1.27-alpine AS production

# Copy built frontend
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# Copy nginx config (mounted via docker-compose, but provide default)
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf

# Create cache directories
RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R nginx:nginx /var/cache/nginx /var/run /usr/share/nginx/html

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
