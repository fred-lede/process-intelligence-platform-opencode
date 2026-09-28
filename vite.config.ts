import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  build: {
    chunkSizeWarningLimit: 5000,
    // Vite 8 ships Rolldown instead of Rollup. `build.rollupOptions` still
    // works via a compatibility layer but is deprecated, and the *object* form
    // of `output.manualChunks` was removed outright — it is what made the build
    // fail with "manualChunks is not a function". Rolldown's replacement is
    // `output.codeSplitting` groups.
    rolldownOptions: {
      output: {
        codeSplitting: {
          // The first group whose `test` matches captures the module, so the
          // plotly group — whose path also contains "react" — is listed before
          // the react group. `includeDependenciesRecursively` reproduces the
          // dependency-inclusive behaviour of the old object form.
          groups: [
            {
              name: 'vendor-plotly',
              test: /node_modules\/(plotly\.js|react-plotly\.js)\//,
              includeDependenciesRecursively: true,
            },
            {
              name: 'vendor-antd',
              test: /node_modules\/(antd|@ant-design)\//,
              includeDependenciesRecursively: true,
            },
            {
              name: 'vendor-react',
              test: /node_modules\/(react|react-dom|scheduler)\//,
            },
          ],
        },
      },
    },
  },
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ['**/src-tauri/**', '**/engine/**'],
    },
  },
})
