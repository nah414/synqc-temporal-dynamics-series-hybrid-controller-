# deploy/hosted/edge/Dockerfile
#
# Builds a single public container that:
# - serves the UI (from ./web)
# - reverse-proxies /api/* to the internal synqc api container
# - enforces login via oauth2-proxy (see nginx.conf)
FROM nginx:alpine

# Copy UI assets
COPY web/ /usr/share/nginx/html/

# Nginx config
COPY deploy/hosted/edge/nginx.conf /etc/nginx/conf.d/default.conf
