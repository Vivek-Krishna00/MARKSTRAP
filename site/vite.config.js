import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// Built into ../web/site and served by FastAPI: the website at "/", the app at "/app".
const api = 'http://localhost:8000';
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../web/site', emptyOutDir: true,
    rollupOptions: { input: { main: resolve(__dirname, 'index.html'), app: resolve(__dirname, 'app.html') } },
  },
  server: { proxy: { '/api': api, '/console': api, '/campaigns': api, '/renders': api, '/favicon.png': api } },
});
