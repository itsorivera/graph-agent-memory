import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Codespaces serves forwarded ports at https://<codespace>-5173.app.github.dev.
// Vite rejects unknown Host headers by default ("Blocked request"), and its HMR
// websocket must use the forwarded HTTPS port (443) instead of 5173.
const codespaces = Boolean(process.env.CODESPACES)

export default defineConfig({
  plugins: [react()],
  optimizeDeps: { include: ['cytoscape-cose-bilkent', 'cytoscape', 'graphlib', 'bin-pack', '@neo4j-bloom/dagre'], exclude: ['@neo4j-nvl/layout-workers'] },
  server: {
    port: 5173,
    allowedHosts: ['.app.github.dev'],
    hmr: codespaces ? { clientPort: 443 } : undefined,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
