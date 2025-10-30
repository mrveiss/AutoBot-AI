# Minimal sandbox container for secure command execution
FROM alpine:3.18

# Install basic utilities that agents might need
RUN apk add --no-cache \
    bash \
    coreutils \
    curl \
    git \
    grep \
    jq \
    python3 \
    py3-pip \
    sed \
    tar \
    wget

# Create non-root user
RUN adduser -D -u 1000 -g 1000 sandbox

# Set up working directory
WORKDIR /workspace

# Switch to non-root user
USER sandbox

# Set minimal environment
ENV PATH=/usr/local/bin:/usr/bin:/bin
ENV HOME=/home/sandbox
ENV USER=sandbox

# Default command
CMD ["/bin/sh"]
