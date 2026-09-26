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
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/frontend/dist /usr/share/nginx/html
