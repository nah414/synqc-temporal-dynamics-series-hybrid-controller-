# web/Dockerfile
FROM nginx:alpine

# Use a custom nginx config that serves the SPA and proxies /api to the backend service
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the static frontend into nginx's default web root
COPY . /usr/share/nginx/html

EXPOSE 80
