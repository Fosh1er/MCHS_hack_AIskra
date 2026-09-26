import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В dev-режиме API проксируется на backend (uvicorn :8000); в docker — nginx (infra/nginx/default.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
});
