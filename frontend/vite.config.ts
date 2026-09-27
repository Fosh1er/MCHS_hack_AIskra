import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В dev-режиме API проксируется на backend (uvicorn :8000, другой адрес — AISKRA_API); в docker — nginx
// (infra/nginx/default.conf).
const api = process.env.AISKRA_API ?? 'http://localhost:8000';

// HTTPS для коллег по локальной сети (голосовой ввод: микрофон браузер даёт только на https или localhost).
// Сертификат — `make dev-cert` (самоподписанный, на IP этой машины); есть файлы — dev-сервер отдаёт https.
const certDir = resolve(__dirname, '..', '.cert');
const https = existsSync(resolve(certDir, 'dev.crt')) && process.env.AISKRA_DEV_HTTP !== '1'
  ? { cert: readFileSync(resolve(certDir, 'dev.crt')), key: readFileSync(resolve(certDir, 'dev.key')) }
  : undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    https,
    proxy: {
      '/api': api,
      '/health': api,
      '/ws': { target: api.replace(/^http/, 'ws'), ws: true },
    },
  },
});
