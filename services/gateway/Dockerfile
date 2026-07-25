# SensOS Gateway — public edge (reverse proxy)
FROM nginx:1.27-alpine

LABEL org.opencontainers.image.title="SensOS Gateway" \
      org.opencontainers.image.description="Public edge for SensOS product services"

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
