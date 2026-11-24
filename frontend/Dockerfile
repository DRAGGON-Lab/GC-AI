FROM node:24-alpine AS build
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM nginx:1.28-alpine
COPY --from=build /src/dist /usr/share/nginx/html
# Environment repository supplies TLS/auth nginx.conf and secrets at runtime.
