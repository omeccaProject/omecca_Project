import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 중(npm run dev)엔 Vite 서버(기본 5173)가 뜨고, /api·/ws·/media 요청은 스프링부트
// 게이트웨이(8080)로 그대로 전달(proxy)한다. 배포용 빌드(npm run build)는 dist/를 만들고,
// 그걸 b_gateway의 static 리소스 폴더에 복사하면 게이트웨이 하나로 프론트+백엔드가 같이 뜬다.
export default defineConfig({
  plugins: [react()],
  // sockjs-client가 내부적으로 Node의 global 객체를 참조하는데 브라우저엔 없어서
  // "global is not defined" 에러가 남. Vite가 global을 globalThis로 치환하게 해줌.
  define: {
    global: 'globalThis',
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8080', changeOrigin: true },
      '/ws': { target: 'http://localhost:8080', changeOrigin: true, ws: true },
      // 업로드된 동영상(CameraService.uploadVideo가 저장, StaticResourceConfig가 서빙) 재생용.
      // 없으면 <video src="/media/videos/...">가 8080이 아니라 5173(Vite)로 요청이 가서
      // SPA index.html(200, text/html)을 받아버리고 "영상 연결 실패"로 보인다.
      '/media': { target: 'http://localhost:8080', changeOrigin: true },
    },
  },
})