import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发代理：/api 与 /stream 都转发到本地后端。
// 注意 changeOrigin 必须为 false（默认值）：保留浏览器的 Host（localhost:5173），
// 后端据此生成同源播放地址（http://localhost:5173/stream/...），
// cookie 才会随播放请求一起发送；若改成 true 会生成 127.0.0.1:9000 地址导致跨域丢 cookie。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: false
      },
      '/stream': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: false
      }
    }
  }
})
