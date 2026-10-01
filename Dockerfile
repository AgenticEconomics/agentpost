# syntax=docker/dockerfile:1

# ──────────────────────────────────────────────────────────────────────────────
# base – shared Python runtime
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Pip caching & no bytecode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ──────────────────────────────────────────────────────────────────────────────
# api – FastAPI server + CLI
# ──────────────────────────────────────────────────────────────────────────────
FROM base AS api

# Install Python deps first for layer caching
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ /app/

# Create non-root user
RUN groupadd -g 1000 agentpost && \
    useradd -u 1000 -g agentpost -m -s /bin/bash agentpost

# Create data directory
RUN mkdir -p /var/lib/agentpost && chown agentpost:agentpost /var/lib/agentpost

# Install CLI wrapper
RUN echo '#!/bin/bash\nexec python -m app.cli "$@"' > /usr/local/bin/agentpost && \
    chmod +x /usr/local/bin/agentpost

# Copy and set up entrypoint
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8765

USER agentpost

# tini handles PID 1 duties and signal forwarding
ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]

# ──────────────────────────────────────────────────────────────────────────────
# web-build – compile React/Vite frontend
# ──────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS web-build

WORKDIR /build

# Install deps first for layer caching
COPY web/package.json web/package-lock.json* web/pnpm-lock.yaml* web/yarn.lock* ./
RUN if [ -f pnpm-lock.yaml ]; then \
        corepack enable && pnpm install --frozen-lockfile; \
    elif [ -f yarn.lock ]; then \
        yarn install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# Copy frontend source and build
COPY web/ ./
RUN if [ -f pnpm-lock.yaml ]; then \
        pnpm run build; \
    elif [ -f yarn.lock ]; then \
        yarn build; \
    else \
        npm run build; \
    fi

# ──────────────────────────────────────────────────────────────────────────────
# web – nginx serving built frontend
# ──────────────────────────────────────────────────────────────────────────────
FROM nginx:alpine AS web

# Remove default nginx config
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static files from build stage
COPY --from=web-build /build/dist /usr/share/nginx/html

# Run as non-root (nginx unprivileged)
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

# ──────────────────────────────────────────────────────────────────────────────
# worker – reference worker process
# ──────────────────────────────────────────────────────────────────────────────
FROM base AS worker

# Install Python deps first for layer caching
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ /app/

# Create non-root user
RUN groupadd -g 1000 agentpost && \
    useradd -u 1000 -g agentpost -m -s /bin/bash agentpost

USER agentpost

# tini for proper signal handling
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "app.worker.reference"]
