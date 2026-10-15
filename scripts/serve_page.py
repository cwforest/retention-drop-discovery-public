# -*- coding: utf-8 -*-
"""`docs/` 를 띄우면서 **파일을 저장하면 브라우저가 알아서 새로고침**되게 함.

글을 고치며 바로바로 확인할 때 씀. `index.html` 을 내려줄 때 작은 스크립트를
끼워 넣고, 그 스크립트가 0.7초마다 `/__mtime` 을 물어 바뀌었으면 새로고침함.
(원본 파일은 안 건드림 — 보낼 때만 끼움)

쓰는 법:
  python scripts/serve_page.py          # http://localhost:8777
  python scripts/serve_page.py 9000     # 포트 바꿔서
멈추려면 Ctrl+C.
"""
import functools
import http.server
import os
import socketserver
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
# 이 파일들이 바뀌면 새로고침함
볼것 = ['index.html', os.path.join('web', 'app.js'), os.path.join('web', 'style.css')]

# bytes 리터럴에는 한글을 못 넣어서 문자열로 두고 쓸 때 인코딩함
새로고침 = '''
<script>
// 저장하면 알아서 새로고침 — scripts/serve_page.py 가 끼워 넣음 (원본에는 없음)
(function () {
  let 전 = null;
  setInterval(async () => {
    try {
      const r = await fetch('/__mtime', { cache: 'no-store' });
      const t = await r.text();
      if (전 !== null && t !== 전) location.reload();
      전 = t;
    } catch (e) { /* 서버가 잠깐 멈춘 것뿐이면 무시 */ }
  }, 700);
})();
</script>
'''.encode('utf-8')


class 핸들러(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/__mtime'):
            값 = ';'.join(
                str(os.path.getmtime(os.path.join(DOCS, f)))
                for f in 볼것 if os.path.exists(os.path.join(DOCS, f)))
            몸 = 값.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(몸)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(몸)
            return

        길 = self.path.split('?')[0]
        if 길 in ('/', '/index.html'):
            with open(os.path.join(DOCS, 'index.html'), 'rb') as f:
                몸 = f.read()
            몸 = 몸.replace(b'</body>', 새로고침 + b'</body>', 1)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(몸)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(몸)
            return

        super().do_GET()

    def end_headers(self):
        # 고친 CSS·JS 가 캐시에 걸려 안 바뀌는 일을 막음
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *a):
        pass                      # 매 요청마다 찍으면 터미널이 시끄러움


def main():
    포트 = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(
            ('127.0.0.1', 포트),
            functools.partial(핸들러, directory=DOCS)) as 서버:
        print('http://localhost:%d  —  저장하면 자동 새로고침 (Ctrl+C 로 멈춤)' % 포트)
        print('지켜보는 파일:', ', '.join(볼것))
        서버.serve_forever()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
