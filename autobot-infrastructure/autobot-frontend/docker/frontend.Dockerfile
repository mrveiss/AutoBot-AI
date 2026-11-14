# Frontend Dockerfile
# Node.js major: pinned to the repo-root .nvmrc by repo_tests/node_major_one_home_19328_test.py (#19328).
ARG NODE_MAJOR=22
FROM node:${NODE_MAJOR}-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Create non-root user
RUN addgroup -g 1000 -S autobot && \
    adduser -u 1000 -S autobot -G autobot && \
    chown -R autobot:autobot /app
USER autobot

# Expose port
EXPOSE 5173

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5173/ || exit 1

# Start development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
