# -*- coding: utf-8 -*-
"""本地验证 scf/index.py 的返回结构与 CORS，不发起真实 DeepSeek 请求。"""
import importlib.util
import json
import os
import base64

SPEC = r'C:\Users\中铝矿业投并部\mining-daily\scf\index.py'
spec = importlib.util.spec_from_file_location('scf_index', SPEC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# mock DeepSeek，避免真实外网请求
m.ask_deepseek = lambda key, q, ctx: '【mock AI 回答】' + q

res = {'pass': [], 'fail': []}


def check(name, cond):
    (res['pass'] if cond else res['fail']).append(name)


GH = 'https://pliucugb-cyber.github.io'

# 1) OPTIONS 预检
r = m.main_handler({'path': '/api/health', 'httpMethod': 'OPTIONS',
                    'headers': {'origin': GH}}, None)
check('OPTIONS 预检返回 204', r['statusCode'] == 204)
check('OPTIONS 带 CORS 头', r['headers'].get('Access-Control-Allow-Methods') == 'GET,POST,OPTIONS')

# 2) health 无 key
os.environ.pop('DEEPSEEK_API_KEY', None)
r = m.main_handler({'path': '/api/health', 'httpMethod': 'GET', 'headers': {'origin': GH}}, None)
d = json.loads(r['body'])
check('health 无 key → has_key=false', d['has_key'] is False)
check('health 无 key → model=disabled', d['model'] == 'disabled')
check('health 无 key → ok=true', d['ok'] is True)

# 3) health 有 key
os.environ['DEEPSEEK_API_KEY'] = 'sk-mock'
r = m.main_handler({'path': '/api/health', 'httpMethod': 'GET', 'headers': {'origin': GH}}, None)
d = json.loads(r['body'])
check('health 有 key → has_key=true', d['has_key'] is True)
check('health 有 key → model=deepseek-chat', d['model'] == 'deepseek-chat')
os.environ.pop('DEEPSEEK_API_KEY', None)

# 4) qa 无 key 关键词兜底
r = m.main_handler({'path': '/api/qa', 'httpMethod': 'POST', 'headers': {'origin': GH},
                    'body': json.dumps({'question': '稀土最近怎么看', 'context': []})}, None)
d = json.loads(r['body'])
check('qa 无 key → source=keyword-fallback', d['source'] == 'keyword-fallback')
check('qa 无 key → 命中稀土兜底', '稀土' in d['answer'])

# 5) qa 有 key（mock）
os.environ['DEEPSEEK_API_KEY'] = 'sk-mock'
r = m.main_handler({'path': '/api/qa', 'httpMethod': 'POST', 'headers': {'origin': GH},
                    'body': json.dumps({'question': '铝土矿进展',
                                        'context': [{'t': '广西铝土矿取得突破', 'd': '2026-09-01', 's': '来源', 'u': 'http://x'}]})}, None)
d = json.loads(r['body'])
check('qa 有 key → source=deepseek', d['source'] == 'deepseek')
check('qa 有 key → answer 来自 mock', d['answer'] == '【mock AI 回答】铝土矿进展')
check('qa 有 key → refs 携带 url', d['refs'] and d['refs'][0]['u'] == 'http://x')
os.environ.pop('DEEPSEEK_API_KEY', None)

# 6) base64 请求体解析
os.environ.pop('DEEPSEEK_API_KEY', None)
b64 = base64.b64encode(json.dumps({'question': '锂价'}).encode('utf-8')).decode()
r = m.main_handler({'path': '/api/qa', 'httpMethod': 'POST', 'headers': {'origin': GH},
                    'body': b64, 'isBase64Encoded': True}, None)
d = json.loads(r['body'])
check('base64 body 可解析 → 命中锂兜底', '锂' in d['answer'])

# 7) CORS 白名单：非白名单 origin 返回 null
r = m.main_handler({'path': '/api/health', 'httpMethod': 'GET', 'headers': {'origin': 'https://evil.com'}}, None)
check('非白名单 origin → Access-Control-Allow-Origin=null', r['headers'].get('Access-Control-Allow-Origin') == 'null')

# 8) 404
r = m.main_handler({'path': '/x', 'httpMethod': 'GET', 'headers': {}}, None)
check('未知路径 → 404', r['statusCode'] == 404)

# 9) 空问题
r = m.main_handler({'path': '/api/qa', 'httpMethod': 'POST', 'headers': {'origin': GH},
                    'body': json.dumps({'question': '   '})}, None)
d = json.loads(r['body'])
check('空问题 → 返回提示', '请输入' in d['answer'])

print('PASS %d, FAIL %d' % (len(res['pass']), len(res['fail'])))
for f in res['fail']:
    print('  FAIL:', f)
for p in res['pass']:
    print('  ok  :', p)
print('RESULT', 'ALL PASS' if not res['fail'] else 'HAS FAIL')
