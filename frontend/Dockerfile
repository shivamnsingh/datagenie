# ── Frontend Dockerfile (multi-stage) ──────────────────────────────────────────

# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: route all requests to index.html for client-side routing
RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / { try_files $uri $uri/ /index.html; }\n\
  location /api/ { proxy_pass http://backend:8000; proxy_set_header Host $host; }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
