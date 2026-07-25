# SensOS Dashboard — operator presentation surface
FROM nginx:1.27-alpine

LABEL org.opencontainers.image.title="SensOS Dashboard" \
      org.opencontainers.image.description="Operator dashboard shell for SensOS"

COPY index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ || exit 1
