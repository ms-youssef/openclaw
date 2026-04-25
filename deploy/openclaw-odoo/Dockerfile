# OpenClaw runtime image with the Odoo Discuss channel plugin baked in.
#
# Build context must be the repo root so the COPY can see openclaw-odoo-channel/.
#
# Build:
#   docker build -t openclaw-odoo:local \
#       -f deploy/openclaw-odoo/Dockerfile .

ARG OPENCLAW_TAG=latest
FROM ghcr.io/openclaw/openclaw:${OPENCLAW_TAG}

USER root

RUN mkdir -p /home/node/.openclaw/extensions

COPY --chown=1000:1000 openclaw-odoo-channel/ /home/node/.openclaw/extensions/odoo/

USER 1000

WORKDIR /home/node/.openclaw/extensions/odoo
RUN npm install --omit=dev

WORKDIR /home/node
