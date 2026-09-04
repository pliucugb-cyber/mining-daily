#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简静态服务：把本目录的 index.html（旧链接停用通知 + 跳转页）返回给所有请求。
用于 WorkBuddy 部署到「矿业新闻日报」旧应用，使其从完整日报变为一个停用提醒页。
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
PORT = int(os.environ.get("PORT", "3000"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with open(INDEX, "rb") as f:
                body = f.read()
        except Exception:
            body = b"Moved to https://pliucugb-cyber.github.io/mining-daily/"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
