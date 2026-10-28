import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react(), {
    name: 'health-endpoint',
    configureServer(server) {
      server.middlewares.use('/health', (_req, res) => {
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ status: 'ok', service: 'odin-frontend' }));
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use('/health', (_req, res) => {
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ status: 'ok', service: 'odin-frontend' }));
      });
    },
  }],
});
