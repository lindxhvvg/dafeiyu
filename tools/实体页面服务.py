# -*- coding: utf-8 -*-
"""实体模式专用的静态页面服务（端口 8080）。

普通的 http.server 会把整个项目目录暴露到局域网，其中就有 keys.local.json、
soul.db 等敏感文件——这是"线上链接带密钥"事故的同款病根。
本服务只放行页面本身与 形象/ 下的素材，其余一律 403。
"""
import os
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_FILES = ('脑袋-v0.1.html', 'index.html', 'favicon.ico')


class BodyOnlyHandler(SimpleHTTPRequestHandler):
    def _allowed(self):
        raw = urllib.parse.urlsplit(self.path).path
        path = urllib.parse.unquote(raw).lstrip('/')
        if '..' in path or '\\' in path:
            return False, path
        # 以解析后的真实文件路径为准：URL 里的任何变形都绕不过这一层。
        # 只放行项目根下的页面文件与 形象/ 目录内的素材。
        real = os.path.abspath(self.translate_path(raw))
        base = os.path.abspath(BASE)
        rel = os.path.relpath(real, base)
        if rel.startswith('..') or os.path.isabs(rel):
            return False, path
        if rel.startswith('形象' + os.sep):
            return True, path
        return rel in ALLOWED_FILES, path

    def do_GET(self):
        ok, path = self._allowed()
        if path == '':
            body = ('<!doctype html><meta charset="utf-8">'
                    '大肥鱼实体模式：请用 局域网接入.txt 里的完整地址打开').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not ok:
            self.send_error(403, 'forbidden')
            return
        super().do_GET()

    def do_HEAD(self):
        ok, path = self._allowed()
        if not ok or path == '':
            self.send_error(403, 'forbidden')
            return
        super().do_HEAD()

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    os.chdir(BASE)
    ThreadingHTTPServer(('0.0.0.0', 8080), BodyOnlyHandler).serve_forever()
