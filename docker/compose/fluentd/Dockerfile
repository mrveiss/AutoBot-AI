# Custom Fluentd image with Seq output plugin
FROM fluent/fluentd:v1.16-debian-1

# Install additional plugins
USER root

RUN apt-get update && apt-get install -y \
    build-essential \
    ruby-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Seq output plugin and other useful plugins
RUN gem install fluent-plugin-seq \
    fluent-plugin-multi-format-parser \
    fluent-plugin-record-modifier \
    fluent-plugin-grep \
    fluent-plugin-rewrite-tag-filter

# Create necessary directories
RUN mkdir -p /var/log/fluentd-buffers \
    && mkdir -p /var/log/autobot \
    && chown -R fluent:fluent /var/log/fluentd-buffers \
    && chown -R fluent:fluent /var/log/autobot

USER fluent
