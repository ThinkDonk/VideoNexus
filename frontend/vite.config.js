import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发代理：/api 转发到本地后端
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: true
      }
    }
  }
})
