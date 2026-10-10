"""本地启动 AnythingLLM 文档上传页面。

用法：
    python start.py [端口]      # 默认 5500
然后浏览器打开 http://localhost:5500
"""

import http.server
import os
import socketserver
import sys
import webbrowser
from functools import partial

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # 开发期禁用缓存，修改页面后刷新即可生效
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), partial(Handler, directory=ROOT)) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"页面已启动：{url}")
        print("按 Ctrl+C 退出")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已退出")