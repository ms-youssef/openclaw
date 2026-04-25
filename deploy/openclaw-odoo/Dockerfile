# OpenClaw runtime image with the Odoo Discuss channel plugin baked in.
#
# Build:
#   docker build -t openclaw-odoo:local \
#       --build-arg PLUGIN_REPO=https://github.com/ms-youssef/openclaw-odoo-channel.git \
#       --build-arg PLUGIN_REF=main \
#       deploy/openclaw-odoo

ARG OPENCLAW_TAG=latest
FROM ghcr.io/openclaw/openclaw:${OPENCLAW_TAG}

ARG PLUGIN_REPO=https://github.com/ms-youssef/openclaw-odoo-channel.git
ARG PLUGIN_REF=main

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/node/.openclaw/extensions \
    && git clone --depth 1 --branch "${PLUGIN_REF}" "${PLUGIN_REPO}" \
        /home/node/.openclaw/extensions/odoo \
    && chown -R 1000:1000 /home/node/.openclaw

USER 1000

WORKDIR /home/node/.openclaw/extensions/odoo
RUN npm install --omit=dev

WORKDIR /home/node
