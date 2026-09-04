#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
redirect_server.py —— 旧链接的「搬迁告示」服务

背景
----
矿业日报的内容已迁至 GitHub Pages（地址固定，不随电脑变化）：
    https://pliucugb-cyber.github.io/mining-daily/

旧链接 https://48e362fedb334509b4517cef02f125a8.app.workbuddy.link 有两个先天限制：
  1. 它与「本机目录绝对路径」绑定，换电脑就变；
  2. 它是发布时上传的**静态快照**，不会自动更新。
因此旧链接上的内容会一直停留在迁移那天的样子。同事打开看到的是过期日报，
却完全无从察觉——这比打不开更麻烦。

本服务就是旧链接的新用途：**不再承载任何日报内容，只负责把人送到新地址**。
任何路径都返回同一张提示页，几秒后自动跳转。

用法
----
    PORT=3000 python redirect_server.py    # 云端部署（注入 PORT 时自动监听 0.0.0.0）
    python redirect_server.py              # 本地试跑 http://127.0.0.1:3000

发布时把 startCmd 指定为本文件即可，目录不变 → 旧链接不变。
"""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 新站地址（迁移目标）。日后若再换地址，改这一行即可。
NEW_SITE = 'https://pliucugb-cyber.github.io/mining-daily/'

PAGE = u"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>站点已迁移 · 矿业新闻日报</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#f5f7fa;color:#1f2d3d;
       font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;
       padding:24px;-webkit-font-smoothing:antialiased}
  .card{background:#fff;border-radius:14px;box-shadow:0 6px 28px rgba(26,35,126,.10);
        padding:38px 32px;max-width:520px;width:100%;text-align:center}
  .badge{display:inline-block;background:#eef2ff;color:#1a237e;font-size:12px;font-weight:600;
         padding:5px 12px;border-radius:99px;letter-spacing:.5px;margin-bottom:18px}
  h1{margin:0 0 14px;font-size:22px;line-height:1.4}
  p{margin:0 0 10px;font-size:14px;line-height:1.75;color:#4a5a6a}
  .new{display:block;margin:22px 0 6px;padding:13px 16px;background:#f7f9fc;border:1px solid #e3e9f2;
       border-radius:10px;word-break:break-all;font-size:14px;color:#1a237e;text-decoration:none;font-weight:600}
  .new:hover{background:#eef2ff;border-color:#c7d2fe}
  .btn{display:inline-block;margin-top:18px;padding:12px 30px;background:#1a237e;color:#fff;
       border-radius:9px;font-size:15px;font-weight:600;text-decoration:none;cursor:pointer;border:none}
  .btn:hover{background:#283593}
  .cd{margin-top:14px;font-size:12.5px;color:#8996a5}
  .note{margin-top:24px;padding-top:16px;border-top:1px solid #edf1f6;font-size:12.5px;color:#8996a5;line-height:1.7}
</style>
</head>
<body>
  <div class="card">
    <div class="badge">通知</div>
    <h1>矿业新闻日报已换新地址</h1>
    <p>为方便长期使用，日报已迁移到固定地址，<br>今后换电脑、换人维护都不会变。</p>
    <p>这个旧地址已停止更新，看到的内容是迁移前的旧数据，<br>请勿再据此判断行情。</p>

    <a class="new" href="__NEW__" id="newLink">__NEW__</a>
    <a class="btn" href="__NEW__" id="go">立即前往新地址</a>
    <div class="cd"><span id="cd">5</span> 秒后自动跳转…</div>

    <div class="note">
      建议把新地址保存到收藏夹，并请互相转告同事们一并更新收藏。<br>
      若已把日报「安装成 App」，请删除旧图标后重新访问新地址安装一次。<br>
      旧地址将于近期下线，请以新地址为准。
    </div>
  </div>
<script>
(function(){
  var NEW = "__NEW__";
  var left = 5, redirected = false;
  var cdEl = document.getElementById('cd');

  // 倒计时归零后真正执行跳转的函数（旧版误调用了未定义的 go()，导致永不跳转）
  function jump(){
    if (redirected) return;
    redirected = true;
    // 旧站点注册过 Service Worker 并有缓存；同事若把它装成 PWA，
    // 残留的 SW 会让旧内容"复活"。跳转前主动注销并清空缓存。
    try {
      if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
        navigator.serviceWorker.getRegistrations().then(function(rs){
          rs.forEach(function(r){ try { r.unregister(); } catch(e){} });
        }).catch(function(){});
      }
      if (window.caches && caches.keys) {
        caches.keys().then(function(ks){
          ks.forEach(function(k){ try { caches.delete(k); } catch(e){} });
        }).catch(function(){});
      }
    } catch(e) {}
    setTimeout(function(){ window.location.href = NEW; }, 350);
  }

  setInterval(function(){
    left--;
    if (cdEl) cdEl.textContent = (left > 0 ? left : 0);
    if (left <= 0) jump();
  }, 1000);

  var goBtn = document.getElementById('go');
  if (goBtn) goBtn.addEventListener('click', function(ev){ ev.preventDefault(); jump(); });
})();
</script>
</body>
</html>
"""


class RedirectHandler(BaseHTTPRequestHandler):
    server_version = 'MiningDailyRedirect/1.0'

    def _respond(self, body, code=200, ctype='text/html; charset=utf-8'):
        data = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def do_HEAD(self):
        self._respond(PAGE.replace('__NEW__', NEW_SITE))

    def do_GET(self):
        # 浏览器会自动请求 favicon，返回 HTML 会让控制台报 MIME 错误，这里直接给空响应
        if self.path.rstrip('/').endswith('favicon.ico'):
            self.send_response(204)
            self.end_headers()
            return
        self._respond(PAGE.replace('__NEW__', NEW_SITE))

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(os.environ.get('PORT', '3000'))
    # 与 server.py 保持同一约定：云端注入 PORT 时监听 0.0.0.0，本地只听本机
    host = os.environ.get('HOST') or ('0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    print('========================================================')
    print('  矿业日报 · 旧链接迁移提示服务')
    print('  监听      %s:%d' % (host, port))
    print('  跳转目标  %s' % NEW_SITE)
    print('  说明      任何路径都返回搬迁提示页，不再承载日报内容')
    print('========================================================')
    srv = ThreadingHTTPServer((host, port), RedirectHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
