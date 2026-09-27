import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В dev-режиме API проксируется на backend (uvicorn :8000, другой адрес — AISKRA_API); в docker — nginx
// (infra/nginx/default.conf).
const api = process.env.AISKRA_API ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': api,
      '/health': api,
      '/ws': { target: api.replace(/^http/, 'ws'), ws: true },
    },
  },
});
