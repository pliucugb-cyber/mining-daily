# -*- coding: utf-8 -*-
"""
scf/index.py —— 矿业新闻日报 · 轻后端（仅 /api/qa + /api/health）
部署目标：腾讯云云函数 SCF（Web 函数 + 函数 URL，Python 3.10）

设计目标（与用户约定）：
  - 无状态：不读任何数据文件，前端把「问题 + 本地已检索到的相关新闻」一起 POST 过来，
    本函数只负责调 DeepSeek 生成答案（key 存为函数环境变量，不落代码）。
  - 国内访问最稳：腾讯云 SCF 国内节点，同事访问基本不会被墙（相比 Cloudflare Workers 的 workers.dev）。
  - 换电脑可恢复：本文件进 git；key 是云函数环境变量（控制台配置）；
    换机只需 `git clone` + 控制台重新粘贴代码、设环境变量、开函数 URL 即可。

入口：腾讯云 SCF Web 函数调用 main_handler(event, context)
event 关键字段（Web 函数 / 函数 URL / API 网关 v2 兼容）：
  - event["path"]           请求路径，如 "/api/health"
  - event["httpMethod"]     请求方法，如 "GET"/"POST"
  - event["headers"]        请求头 dict（key 大小写不固定，取 origin 时忽略大小写）
  - event["body"]           请求体字符串（isBase64Encoded 为 true 时是 base64）
  - event["isBase64Encoded"] 请求体是否 base64 编码
返回：API 网关 / Web 函数集成响应格式
  {
    "isBase64Encoded": False,
    "statusCode": 200,
    "headers": {"Content-Type": "application/json", ...},
    "body": "<json 字符串>",
  }
"""

import json
import os
import re
import base64
import urllib.request
import urllib.error

# ── 允许的跨域来源（防 key 被任意第三方站点滥用）──
#    GitHub Pages 站点 + 本地调试（无 TLS 的 localhost/127.0.0.1 任意端口）。
def is_allowed_origin(origin):
    if not origin:
        return False
    if re.match(r'^https://[\w.-]+\.github\.io$', origin):
        return True
    if re.match(r'^http://(localhost|127\.0\.0\.1)(:\d+)?$', origin):
        return True
    return False


# ── CORS 头（仅对白名单来源放行，预检也受控）──
def cors_headers(origin):
    allow = is_allowed_origin(origin)
    return {
        'Access-Control-Allow-Origin': origin if allow else 'null',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Cache-Control': 'no-store',
    }


# ── 无 key 时的本地关键词兜底（搬运自 worker.js QA_TEMPLATES）──
QA_TEMPLATES = [
    (['铜', 'Cu'], '铜（Cu）是有色金属中的重要品种，广泛应用于电力、建筑、交通等领域。'),
    (['铝', 'Al'], '铝（Al）具有轻质、耐腐蚀等特性，广泛应用于航空航天、汽车制造、包装容器等领域。'),
    (['锌', 'Zn'], '锌（Zn）主要用于镀锌钢板、合金制造和电池。'),
    (['铅', 'Pb'], '铅（Pb）主要用于铅酸蓄电池、辐射防护材料。'),
    (['镍', 'Ni'], '镍（Ni）是不锈钢和动力电池的关键金属，新能源车带动需求快速增长。'),
    (['锡', 'Sn'], '锡（Sn）主要用于焊锡和电子封装，半导体景气度直接影响其需求。'),
    (['锂', 'Li'], '锂（Li）被称为“白色石油”，是新能源动力电池的核心原材料。中国是全球最大锂消费国。'),
    (['稀土'], '稀土是 17 种金属元素的统称，中国是全球最大的稀土生产国和供应国。'),
    (['金', '黄金'], '黄金兼具商品、货币、避险三重属性，央行购金、地缘冲突是金价的核心驱动。'),
    (['铁矿', '铁矿石'], '铁矿石是钢铁工业的核心原料，中国是全球最大进口国，对外依存度高。'),
    (['新一轮', '找矿', '突破', '战略'],
     '新一轮找矿突破战略行动已取得阶段性成果：铜、铝、锂、钴、镍等关键矿产新增资源量稳步提升。'),
    (['关键矿产', '战略性矿产'],
     '关键矿产对国家经济安全和国防至关重要，中国“十四五”明确将 24 种矿产列为战略性矿产。'),
    (['勘查', '勘探'],
     '矿产勘查分为预查、普查、详查、勘探 4 个阶段，铝土矿等矿种勘查深度按 DZ/T 0202-2020 等规范执行。'),
    (['矿权', '采矿权', '探矿权'], '矿业权包括探矿权和采矿权，出让方式分招拍挂与协议出让。'),
    (['DZ/T', '规范', '标准'],
     '地质矿产领域现行重要标准：DZ/T 0202-2020（铝土矿）、DZ/T 0204-2020（铜铅锌银）、DZ/T 0205-2020（稀有金属）等。'),
]


def keyword_fallback(q):
    for kws, ans in QA_TEMPLATES:
        if any(k in q for k in kws):
            return ans
    return ('关于「' + q + '」，我暂未匹配到精确答案。'
            '可尝试关键词：铜/铝/锌/铅/镍/锡/锂/稀土/找矿/矿权。'
            '（当前为无密钥兜底模式，配置 DEEPSEEK_API_KEY 后可获得 AI 深度解答）')


# ── 调用 DeepSeek 生成答案（标准库 urllib，无第三方依赖）──
def ask_deepseek(api_key, question, context):
    system = ('你是资深矿业行业分析师，服务于「矿业新闻日报」产品。'
              '回答要简洁专业、不啰嗦、用中文。'
              '如果提供了相关新闻条目，请自然引用并注明来源与日期；'
              '若没有相关新闻，请明确说明这是基于通用知识的回答，并建议用户查证官方信息。'
              '不要编造数据、价格或政策细节。')

    user = '用户问题：' + question + '\n\n'
    if isinstance(context, list) and len(context):
        user += '以下为前端检索到的相关本地新闻条目（仅供参考，请以公开权威信息为准）：\n'
        for i, c in enumerate(context[:12]):
            if not isinstance(c, dict):
                continue
            d = c.get('d') or ''
            t = c.get('t') or c.get('title') or ''
            s = c.get('s') or c.get('source') or ''
            user += '%d. [%s] %s%s\n' % (i + 1, d, t, ('（' + s + '）' if s else ''))
        user += '\n'
    else:
        user += '（前端未提供相关新闻，请基于通用知识回答。）\n\n'
    user += '请直接给出回答，无需寒暄。'

    payload = {
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'max_tokens': 800,
        'temperature': 0.3,
        'stream': False,
    }

    req = urllib.request.Request(
        'https://api.deepseek.com/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_key,
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        txt = ''
        try:
            txt = e.read().decode('utf-8', 'ignore')[:200]
        except Exception:
            pass
        raise RuntimeError('DeepSeek HTTP %s %s' % (e.code, txt))
    except Exception as e:
        raise RuntimeError('DeepSeek 调用失败：' + str(e))

    choices = (data or {}).get('choices') or [{}]
    content = (((choices[0] or {}).get('message') or {}).get('content') or '').strip()
    if not content:
        raise RuntimeError('DeepSeek 返回为空')
    return content


# ── 工具：统一构造 API 网关 / Web 函数集成响应 ──
def respond(status, payload, cors):
    body_str = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    headers = dict(cors)
    headers['Content-Type'] = 'application/json; charset=utf-8'
    return {
        'isBase64Encoded': False,
        'statusCode': status,
        'headers': headers,
        'body': body_str,
    }


# ── 工具：解析请求体（处理 base64）──
def parse_body(event):
    raw = event.get('body')
    if raw is None:
        return {}
    if event.get('isBase64Encoded'):
        try:
            raw = base64.b64decode(raw).decode('utf-8')
        except Exception:
            return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ── 工具：从 headers 忽略大小写取 origin ──
def get_origin(event):
    headers = event.get('headers') or {}
    if isinstance(headers, dict):
        for k, v in headers.items():
            if k.lower() == 'origin':
                return v
    return None


# ── 工具：兼容取 path 和 method ──
# Web 函数 / 函数 URL：event["path"] / event["httpMethod"]
# API 网关 v2：event["requestContext"]["http"]["path"] / ["method"]
# API 网关 v1：event["requestContext"]["httpMethod"]
def get_path(event):
    if event.get('path'):
        return event['path']
    rc = event.get('requestContext') or {}
    http = rc.get('http') or {}
    return http.get('path') or ''


def get_method(event):
    if event.get('httpMethod'):
        return event['httpMethod']
    rc = event.get('requestContext') or {}
    http = rc.get('http') or {}
    return http.get('method') or rc.get('httpMethod') or 'GET'


# ── 路由处理 ──
def main_handler(event, context):
    event = event or {}
    path = get_path(event)
    method = get_method(event)
    origin = get_origin(event)
    cors = cors_headers(origin)

    # 预检
    if method == 'OPTIONS':
        return respond(204, '', cors)

    # /api/health —— 健康检查 + AI 配置状态
    if path == '/api/health':
        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        has_key = bool(api_key)
        return respond(200, {
            'ok': True,
            'has_key': has_key,
            'model': 'deepseek-chat' if has_key else 'disabled',
            'time': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        }, cors)

    # /api/qa —— 仅接受 POST
    if path == '/api/qa':
        if method != 'POST':
            return respond(405, {'error': 'method not allowed'}, cors)
        body = parse_body(event)
        question = str(body.get('question') or '').strip()
        context_list = body.get('context') if isinstance(body.get('context'), list) else []

        if not question:
            return respond(200, {'answer': '请输入您要查询的矿业相关问题。'}, cors)

        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        # 无 key：关键词兜底（仍可用，不报错）
        if not api_key:
            return respond(200, {
                'answer': keyword_fallback(question),
                'question': question,
                'source': 'keyword-fallback',
                'cited': 0,
                'refs': [],
            }, cors)

        # 有 key：调 DeepSeek（含前端传来的相关新闻作为 RAG 上下文）
        try:
            answer = ask_deepseek(api_key, question, context_list)
            refs = []
            for c in (context_list or [])[:8]:
                if isinstance(c, dict) and (c.get('u') or c.get('url')):
                    refs.append({
                        'd': c.get('d') or '',
                        't': c.get('t') or c.get('title') or '',
                        'u': c.get('u') or c.get('url') or '',
                    })
            return respond(200, {
                'answer': answer,
                'question': question,
                'source': 'deepseek',
                'cited': len(context_list or []),
                'refs': refs,
            }, cors)
        except Exception as e:
            return respond(502, {
                'error': 'AI 服务调用失败：' + str(e),
            }, cors)

    return respond(404, {'error': 'not found'}, cors)
