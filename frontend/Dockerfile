# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
#   Node 20 LTS — installs npm deps and runs `vite build`.
#   The resulting /app/dist is the only thing carried to the runtime stage.
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

# Copy manifests first so npm install is cached when only source code changes.
COPY package.json package-lock.json* ./

RUN npm ci --prefer-offline

# Copy source and build config
COPY . .

# VITE_API_BASE_URL is injected at build time via --build-arg so the
# production bundle points at the real backend URL without a .env file
# being baked into the image.
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
#   Nginx Alpine (~25 MB) serves the static Vite bundle.
#   Configuration is supplied by nginx/nginx.conf (maintained separately),
#   which handles the SPA fallback, REST proxy, and WebSocket upgrade.
# ─────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

LABEL maintainer="smart-attendance" \
      description="Smart Attendance System — React/Vite frontend" \
      version="0.1.0"

COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default nginx config with the project's production config.
# nginx/nginx.conf is a full http-context file, so it goes to the top-level
# include path rather than conf.d/.
COPY ../nginx/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/ > /dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
