# Dr. Boz custom Docker image
# Builds on top of the official Open WebUI image with our custom backend.
FROM ghcr.io/open-webui/open-webui:main@sha256:74093dadc9c6aabc23987a74fd8c2fb8d995b1a5b22e83b0036fb9d6af590e8c
COPY backend/ /app/backend/
