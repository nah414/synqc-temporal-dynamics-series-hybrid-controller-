FROM nginx:1.27-alpine

# Nginx config for hosted edge (auth + reverse proxy)
COPY ./deploy/hosted/edge/nginx.conf /etc/nginx/conf.d/default.conf

# Copy the static UI
# NOTE: This assumes your UI assets (index.html + /assets) live in ./web.
# If you build to a different folder (e.g. web/dist), change this COPY line.
COPY ./web/ /usr/share/nginx/html/
