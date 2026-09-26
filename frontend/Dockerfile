# Сборка SPA (контекст — корень репозитория, т.к. нужен воркспейс packages/ui-kit)
FROM node:22-alpine AS build
WORKDIR /repo
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/
COPY packages/ui-kit/package.json packages/ui-kit/
RUN npm ci
COPY packages packages
COPY frontend frontend
RUN npm run build -w frontend

FROM nginx:1.27-alpine
# openssl — для самоподписанного сертификата при первом старте (п. 6.2)
RUN apk add --no-cache openssl && rm -f /etc/nginx/conf.d/default.conf
COPY infra/nginx/templates/ /etc/nginx/templates/
COPY --chmod=755 infra/nginx/15-tls-selfsigned.sh /docker-entrypoint.d/15-tls-selfsigned.sh
ENV PUBLIC_HTTPS_PORT=8443
COPY --from=build /repo/frontend/dist /usr/share/nginx/html
