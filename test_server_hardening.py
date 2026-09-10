# -*- coding: utf-8 -*-
"""
server.py 加固回归测试（2026-09-10 第 2 批 P1）

覆盖：可选鉴权（MD_SERVER_TOKEN）+ 请求体限长 + 脏输入不崩。
运行：python test_server_hardening.py        （退出码 0=全过，1=有失败）

注意：本文件是 .py，不属于 test_*.js 的 jsdom 套件，需单独跑。
另：它会真起 127.0.0.1 随机端口的 HTTP 服务，跑完自动 shutdown。
"""
import os
import sys
import json
import threading
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  ' + name + (('  ' + extra) if extra else ''))
    else:
        FAIL += 1
        print('FAIL  ' + name + (('  ' + extra) if extra else ''))


def boot(token=None):
    """以给定 token 重启一个 server 实例（随机端口），返回 (srv, port)。"""
    os.environ.pop('MD_SERVER_TOKEN', None)
    if token:
        os.environ['MD_SERVER_TOKEN'] = token
    sys.modules.pop('server', None)
    import server                       # noqa: E402
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def req(port, path, method='GET', body=None, headers=None):
    url = 'http://127.0.0.1:%d%s' % (port, path)
    r = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return -1, '%s: %s' % (type(e).__name__, e)


# ---------- A. 未设 MD_SERVER_TOKEN：必须完全兼容旧行为 ----------
srv, port = boot(None)
c, _ = req(port, '/api/health')
check('未设 token 时 /api/health 仍可访问（向后兼容）', c == 200, 'HTTP %d' % c)
c, b = req(port, '/api/qa', 'POST', json.dumps({'question': '铜价'}).encode(),
           {'Content-Type': 'application/json'})
check('未设 token 时 /api/qa 正常返回', c == 200 and 'answer' in b, 'HTTP %d' % c)
c, _ = req(port, '/index.html')
check('未设 token 时静态页可访问', c == 200, 'HTTP %d' % c)
srv.shutdown()

# ---------- B. 设置 MD_SERVER_TOKEN ----------
TOK = 'test-token-abc123'
srv, port = boot(TOK)

c, _ = req(port, '/api/health')
check('设 token 后 /api/health 无凭据 → 401', c == 401, 'HTTP %d' % c)
c, _ = req(port, '/api/health', headers={'Authorization': 'Bearer ' + TOK})
check('正确 Bearer → 200', c == 200, 'HTTP %d' % c)
c, _ = req(port, '/api/health?token=' + TOK)
check('正确 ?token= → 200', c == 200, 'HTTP %d' % c)
c, _ = req(port, '/api/health?token=wrong-token')
check('错误 token → 401', c == 401, 'HTTP %d' % c)
c, _ = req(port, '/api/health', headers={'Authorization': 'Bearer ' + TOK + 'x'})
check('长度不同的 token → 401（定长比较生效）', c == 401, 'HTTP %d' % c)
c, _ = req(port, '/index.html')
check('静态页不受鉴权影响（本地预览不误伤）', c == 200, 'HTTP %d' % c)

# ---------- C. 请求体限长 ----------
big = json.dumps({'question': 'x' * (400 * 1024)}).encode()
c, b = req(port, '/api/qa?token=' + TOK, 'POST', big,
           {'Content-Type': 'application/json'})
check('400KB 超限 POST → 413', c == 413, 'HTTP %d' % c)
if c == 413:
    check('413 响应体含 max_bytes 提示', 'payload_too_large' in b, b[:80])

c, _ = req(port, '/api/qa?token=' + TOK, 'POST',
           json.dumps({'question': '铜'}).encode(),
           {'Content-Type': 'application/json'})
check('413 之后服务仍存活（未被拖死）', c == 200, 'HTTP %d' % c)

c, b = req(port, '/api/qa?token=' + TOK, 'POST',
           json.dumps({'question': 'y' * 5000}).encode(),
           {'Content-Type': 'application/json'})
q_len = len(json.loads(b).get('question', '')) if c == 200 else -1
check('超长提问被截断到 2000 字内', c == 200 and 0 < q_len <= 2000, 'len=%s' % q_len)

# ---------- D. 脏输入不崩 ----------
c, _ = req(port, '/api/qa?token=' + TOK, 'POST', b'not-json-at-all',
           {'Content-Type': 'application/json'})
check('非法 JSON 退化为 {} 而非 500', c == 200, 'HTTP %d' % c)

srv.shutdown()

print('\n通过 %d / 失败 %d' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
