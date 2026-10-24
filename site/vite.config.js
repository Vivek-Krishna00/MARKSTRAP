import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built into ../web/site and served by FastAPI at "/" (the app lives at "/app").
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../web/site', emptyOutDir: true },
  server: { proxy: { '/app': 'http://localhost:8000', '/api': 'http://localhost:8000', '/console': 'http://localhost:8000' } },
});
