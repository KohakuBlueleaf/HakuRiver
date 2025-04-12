// vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path' // Import path module

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  resolve: {
    alias: {
      // Optional: Set up an alias for easier imports
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Optional: Configure dev server proxy to avoid CORS issues during development
  server: {
    proxy: {
      // Proxy API requests starting with /api to your HakuRiver host
      '/api': {
        target: 'http://127.0.0.1:8000', // Your HakuRiver Host address
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // Remove /api prefix before forwarding
      },
    },
  },
})