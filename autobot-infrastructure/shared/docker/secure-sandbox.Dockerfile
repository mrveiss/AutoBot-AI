# Enhanced Security Sandbox Container for AutoBot
# Multi-layered security with resource limits, monitoring, and isolation

FROM alpine:3.18

# Install security and monitoring tools
RUN apk add --no-cache \
    # Basic utilities
    bash \
    coreutils \
    curl \
    grep \
    jq \
    sed \
    tar \
    wget \
    # Security tools
    aide \
    rkhunter \
    clamav \
    # Monitoring tools
    htop \
    iftop \
    iotop \
    strace \
    tcpdump \
    # Network security
    iptables \
    openssh-client \
    # Python for automation
    python3 \
    py3-pip \
    py3-cryptography \
    py3-psutil \
    # File integrity
    tripwire

# Create secure directories
RUN mkdir -p /sandbox/{workspace,logs,config,tmp} \
    && mkdir -p /var/log/security \
    && mkdir -p /etc/security/limits.d

# Create multiple security users with different privilege levels
RUN addgroup -g 1000 sandbox \
    && adduser -D -u 1000 -g sandbox -G sandbox sandbox \
    && adduser -D -u 1001 -g sandbox -G sandbox sandbox-restricted \
    && adduser -D -u 1002 -g sandbox -G sandbox sandbox-monitor

# Set up resource limits
COPY docker/security/limits.conf /etc/security/limits.d/sandbox.conf
COPY docker/security/security-monitor.py /usr/local/bin/security-monitor
COPY docker/security/sandbox-wrapper.sh /usr/local/bin/sandbox-wrapper

# Configure security policies
COPY docker/security/aide.conf /etc/aide/aide.conf
COPY docker/security/rkhunter.conf /etc/rkhunter.conf

# Set up iptables rules for network isolation
COPY docker/security/iptables-rules.sh /etc/init.d/iptables-rules

# Install Python security dependencies
RUN pip3 install --no-cache-dir \
    psutil \
    watchdog \
    cryptography \
    pyjwt \
    requests

# Set up file permissions and ownership
RUN chown -R sandbox:sandbox /sandbox \
    && chmod 750 /sandbox/workspace \
    && chmod 640 /sandbox/logs \
    && chmod 755 /usr/local/bin/security-monitor \
    && chmod 755 /usr/local/bin/sandbox-wrapper \
    && chmod 755 /etc/init.d/iptables-rules

# Configure logging directory
RUN mkdir -p /var/log/autobot \
    && chown sandbox:sandbox /var/log/autobot \
    && chmod 750 /var/log/autobot

# Set up workspace with restricted permissions
WORKDIR /sandbox/workspace

# Security hardening
RUN echo "sandbox:x:1000:1000:Sandbox User:/sandbox:/bin/bash" >> /etc/passwd \
    && echo "sandbox:!:18000:0:99999:7:::" >> /etc/shadow \
    && echo "sandbox-restricted:!:18000:0:99999:7:::" >> /etc/shadow \
    && echo "sandbox-monitor:!:18000:0:99999:7:::" >> /etc/shadow

# Set security environment variables
ENV SANDBOX_MODE=restricted
ENV SECURITY_LEVEL=high
ENV MONITOR_ENABLED=true
ENV LOG_LEVEL=INFO
ENV PATH=/usr/local/bin:/usr/bin:/bin
ENV HOME=/sandbox
ENV USER=sandbox
ENV TMPDIR=/sandbox/tmp

# Health check for security monitoring
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /usr/local/bin/security-monitor --health-check || exit 1

# Switch to sandbox user
USER sandbox

# Entry point with security wrapper
ENTRYPOINT ["/usr/local/bin/sandbox-wrapper"]
CMD ["/bin/bash"]
