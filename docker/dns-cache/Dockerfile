FROM python:3.11-alpine

# Install required packages
RUN apk add --no-cache dnsmasq bind-tools

# Create app directory
WORKDIR /app

# Copy DNS cache service
COPY dns-cache-service.py .

# Create cache directory
RUN mkdir -p /var/cache/autobot

# Create dnsmasq configuration
RUN echo "# AutoBot DNS Cache Configuration" > /etc/dnsmasq.conf && \
    echo "port=53" >> /etc/dnsmasq.conf && \
    echo "cache-size=1000" >> /etc/dnsmasq.conf && \
    echo "local-ttl=30" >> /etc/dnsmasq.conf && \
    echo "log-queries" >> /etc/dnsmasq.conf && \
    echo "log-facility=-" >> /etc/dnsmasq.conf && \
    echo "addn-hosts=/var/cache/autobot/hosts" >> /etc/dnsmasq.conf

# Create startup script
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'echo "🚀 Starting AutoBot DNS Cache Service"' >> /app/start.sh && \
    echo 'python3 dns-cache-service.py --once --cache-file /var/cache/autobot/cache.json' >> /app/start.sh && \
    echo 'python3 dns-cache-service.py --hosts --cache-file /var/cache/autobot/cache.json > /var/cache/autobot/hosts' >> /app/start.sh && \
    echo 'dnsmasq --no-daemon --log-queries &' >> /app/start.sh && \
    echo 'exec python3 dns-cache-service.py --interval 15 --cache-file /var/cache/autobot/cache.json' >> /app/start.sh && \
    chmod +x /app/start.sh

EXPOSE 53/udp

CMD ["/app/start.sh"]