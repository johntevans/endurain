// Homelab fork: Vite dev-server config for the dev stack in homelab/dev/.
//
// Kept as a separate file so the fork never edits upstream's vite.config.ts.
// It serves the SPA and proxies /api (including the websocket) to the dev
// backend container, so the browser only ever talks to one origin. That is
// what lets the dev stack be opened from another machine on the LAN: no CORS,
// and the refresh cookie (not Secure under ENVIRONMENT=development) stays
// same-origin.
import { mergeConfig, type Plugin } from 'vite'

import baseConfig from './vite.config'

const backend = process.env.HOMELAB_DEV_BACKEND ?? 'http://backend:8080'

// public/env.js pins the API to http://localhost:8080, which is wrong for a
// browser on another machine. An empty window.env makes the frontend fall back
// to the relative /api/v1 path, i.e. the proxy below.
function emptyEnvJs(): Plugin {
  return {
    name: 'homelab-empty-env-js',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/env.js', (_req, res) => {
        res.setHeader('Content-Type', 'application/javascript')
        res.end('window.env = {};\n')
      })
    },
  }
}

export default mergeConfig(baseConfig, {
  plugins: [emptyEnvJs()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true, ws: true },
      // Photos, map thumbnails and avatars are static mounts at the root,
      // outside /api. Without these the SPA fallback answers them with HTML.
      '^/(activity_media|activity_thumbnails|user_images|server_images)/': {
        target: backend,
        changeOrigin: true,
      },
    },
  },
})
