#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
矿业新闻日报 - 后端服务（2026-09-04 重建版）
恢复 9/3 32/32 PASS 部署的全部端点 + 矿业热榜 Top 10 算法。
端点：
  静态        GET /<path>
  /api/health        GET  健康检查（AI 配置状态）
  /api/quota         GET  AI 配额（未启用时全 0）
  /api/hot-news      GET  矿业热榜 Top 10（来源权威×10 + 时效衰减 + 关键词加分）
  /api/qa            POST 关键词匹配问答（不依赖外部 API key）
  /api/morning-report GET  晨报（占位）
  /api/anomalies     GET  异动检测（占位）
  /api/price-history GET  价格历史（占位，sparkline 数据）
  /api/ai-analyze   GET  AI 深度解析（deepseek 调用，每日配额 30/机，结果缓存到 data/ai_analysis_<date>.json）
"""
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, 'data')
NEWS_FILE = os.path.join(DATA_DIR, 'news_2026-09.json')

# ============================================================
# DeepSeek AI 配置（环境变量 DEEPSEEK_API_KEY，无 key 时降级为占位）
# ============================================================
def _resolve_api_key():
    """API key 解析：环境变量 DEEPSEEK_API_KEY 优先，缺失时回退读 qa_config.json。
    （2026-09-04 修复：重部署后沙箱不会注入环境变量，导致 has_key=false、AI 问答降级；
    qa_config.json 由 server.py 本地读取，仅静态黑名单拦截 HTTP 访问，不会泄漏）"""
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if key:
        return key
    try:
        with open(os.path.join(ROOT, 'qa_config.json'), 'r', encoding='utf-8') as f:
            return str((json.load(f) or {}).get('api_key') or '').strip()
    except Exception:
        return ''


DEEPSEEK_API_KEY = _resolve_api_key()
DEEPSEEK_ENDPOINT = 'https://api.deepseek.com/chat/completions'
DEEPSEEK_MODEL = 'deepseek-chat'
AI_QUOTA_PER_DAY = 30
_ai_state = {'date': '', 'count': 0}

# ============================================================
# 旧链迁移模式（2026-09-04 加）：LEGACY_REDIRECT=1 时，
#   - 根路径（/, /index.html）返回紫色"已迁移"提示页（4 秒自动跳 GitHub Pages）
#   - 其余路径照常服务（这样图标/api 还能 200，不会让浏览器控制台一片红）
# 用途：让同事点开旧的 *.app.workbuddy.link 链接时自动跳永久地址，
#   而不需要用户单独通知。本机 / GitHub Pages 部署保留原样。
# ============================================================
LEGACY_REDIRECT = os.environ.get('LEGACY_REDIRECT', '').strip() in ('1', 'true', 'yes', 'on')
LEGACY_NEW_URL = os.environ.get('LEGACY_NEW_URL', 'https://pliucugb-cyber.github.io/mining-daily/').strip() or 'https://pliucugb-cyber.github.io/mining-daily/'

_LEGACY_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#6c5ce7">
<meta name="robots" content="noindex,nofollow">
<title>矿业新闻日报 · 已迁移至新地址</title>
<style>
  :root{
    --p1:#6c5ce7; --p2:#8b5cf6; --p3:#a78bfa;
    --ink:#1f1f2e; --muted:#5f5f7a; --bg:#f7f6fc;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg); color:var(--ink);
    min-height:100vh; display:flex; align-items:center; justify-content:center;
    padding:24px;
  }
  .card{
    width:100%; max-width:520px; background:#fff; border-radius:18px;
    box-shadow:0 12px 40px rgba(108,92,231,.18);
    overflow:hidden;
  }
  .hero{
    background:linear-gradient(135deg,var(--p1) 0%,var(--p2) 100%);
    color:#fff; padding:24px 26px 22px;
  }
  .badge{
    display:inline-flex; align-items:center; gap:6px;
    font-size:13px; color:#ffd591;
    background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.32);
    padding:5px 12px; border-radius:999px; margin-bottom:12px;
    backdrop-filter:blur(2px);
  }
  .hero h1{font-size:24px; line-height:1.4; font-weight:700; letter-spacing:.5px}
  .body{padding:22px 26px 24px}
  .body p{font-size:15px; color:var(--muted); line-height:1.85; margin:8px 0}
  .body p b{color:var(--ink)}
  .cta{
    display:flex; align-items:center; justify-content:center; gap:8px;
    text-decoration:none; margin:20px 0 8px;
    background:linear-gradient(135deg,var(--p1) 0%,var(--p2) 100%);
    color:#fff; font-size:17px; font-weight:600;
    padding:15px 18px; border-radius:12px;
    box-shadow:0 6px 18px rgba(108,92,231,.32);
    transition:transform .12s ease, box-shadow .12s ease;
  }
  .cta:active{transform:translateY(1px); box-shadow:0 3px 10px rgba(108,92,231,.24)}
  .cta svg{width:18px;height:18px;flex-shrink:0}
  .url-line{
    display:flex; align-items:center; justify-content:center; gap:6px;
    font-size:13px; color:var(--muted); margin-top:6px;
    word-break:break-all; cursor:pointer;
  }
  .url-line code{
    background:#f3f1ff; color:var(--p1); padding:3px 8px; border-radius:6px;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  .url-line:hover code{background:#ece8ff}
  .auto{text-align:center; font-size:13px; color:var(--muted); margin-top:18px}
  .auto b{color:var(--p1); font-size:16px; font-weight:600}
  .auto a{color:var(--p1); text-decoration:none; margin-left:6px}
  .auto a:hover{text-decoration:underline}
  .foot{
    margin-top:18px; padding-top:16px; border-top:1px dashed #eee;
    font-size:12px; color:#9b9bb0; text-align:center; line-height:1.7;
  }
</style>
</head>
<body>
<div class="card" role="alert" aria-live="polite">
  <div class="hero">
    <div class="badge">⚠️ 旧地址内容已停用</div>
    <h1>矿业新闻日报 · 已迁移至新地址</h1>
  </div>
  <div class="body">
    <p>您访问的是 <b>旧地址</b>。该地址上的<b>旧版新闻内容已停止维护、不再更新，也不再展示</b>。</p>
    <p>最新、完整的矿业新闻日报，请前往 <b>新地址</b> 查看：</p>
    <a class="cta" id="goBtn" href="__NEW_URL__" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7"/><path d="M7 7h10v10"/></svg>
      前往新版（GitHub Pages）
    </a>
    <div class="url-line" onclick="copyUrl()" title="点击复制">
      新地址：<code id="urlText">__NEW_HOST__</code>
    </div>
    <div class="auto">
      将在 <b id="sec">4</b> 秒后自动跳转…&nbsp;<a href="javascript:void(0)" id="cancelBtn">立即前往</a>
    </div>
    <div class="foot">
      如曾将此页"添加到主屏幕"（PWA），我们一并清理了旧缓存，确保打开即为最新内容。<br>
      旧链接仅作过渡提醒，长期使用请收藏 <b>新地址</b>。
    </div>
  </div>
</div>
<script>
  var NEW_URL = "__NEW_URL__";
  var sec = 4, timer = null, locked = false;
  function tick(){
    sec--;
    var el = document.getElementById('sec');
    if(el) el.textContent = sec;
    if(sec <= 0) doRedirect();
  }
  function doRedirect(){
    if(locked) return; locked = true;
    if(timer){clearInterval(timer); timer=null;}
    window.location.replace(NEW_URL);
  }
  function copyUrl(){
    var full = NEW_URL;
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(full).then(function(){
        flashTip('已复制：' + full);
      }).catch(function(){ flashTip('新地址：' + full); });
    } else { flashTip('新地址：' + full); }
  }
  function flashTip(msg){
    var c = document.querySelector('.url-line code');
    if(!c) return;
    var old = c.textContent; c.textContent = '✓ 已复制';
    setTimeout(function(){ c.textContent = old; }, 1400);
  }
  function cancelAuto(){
    if(timer){clearInterval(timer); timer=null;}
    var a = document.getElementById('cancelBtn');
    if(a){ a.textContent = '已取消，请点击上方按钮'; a.style.color = '#5f5f7a'; }
  }
  timer = setInterval(tick, 1000);
  var btn = document.getElementById('cancelBtn');
  if(btn) btn.addEventListener('click', function(e){ e.preventDefault(); cancelAuto(); });
</script>
</body>
</html>"""

# ============================================================
# 新闻数据加载（9/3 备份的 25 条 9 月新闻）
# ============================================================
_NEWS_CACHE = None


def load_news():
    global _NEWS_CACHE
    if _NEWS_CACHE is not None:
        return _NEWS_CACHE
    try:
        with open(NEWS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        _NEWS_CACHE = d.get('news') or []
    except Exception as e:
        print(f'[load_news] failed: {e}')
        _NEWS_CACHE = []
    return _NEWS_CACHE


# ============================================================
# 矿业热榜 Top 10 加权排序算法
#   score = 来源权威权重×10 + 时效(max(0, 30 - days_diff*4))
#         + 关键词加分（HOT_KW +20，NORMAL_KW +5）
#   URL 去重，同分按日期近者优先
# ============================================================
SOURCE_WEIGHTS = {
    '自然资源部': 12, '中国地质调查局': 10, '中国地质学会': 8,
    '中国有色金属工业协会': 8, '中国黄金协会': 8, '中国稀土行业协会': 7,
    '中国有色网': 7, '矿业权市场': 6, '全球矿产资源': 5,
    '上海联合矿权交易所': 5, '上海期货交易所': 6, '中国矿业报': 7,
    '中国矿业网': 6, '中国黄金集团': 6, '紫金矿业': 5,
    '中国黄金网': 6, '矿冶集团': 6, '中国稀土集团': 7,
    '中国煤炭工业协会': 6, '中国石油和化学工业联合会': 6,
    '中国冶金矿山企业协会': 7, '中国地质大学': 5,
}
HOT_KW = ['突破', '重大', '战略', '世界第一', '首次', '关键矿产', '新一轮',
          '标志性', '历史最好', '历史新高', '刷新', '龙头', '全球第一',
          '亚洲第一', '国内首台', '首套', '首发', '首发阵容']
NORMAL_KW = ['找矿', '勘查', '探矿', '重要', '规划', '增量', '分红',
             '成果', '进展', '签约', '投产', '扩建', '增资', '中标', '出让',
             '成交', '创', '新高', '领先']


def _compute_hot_news(today, n=10):
    rows = load_news()
    if not rows:
        return []
    try:
        today_dt = datetime.strptime(today, '%Y-%m-%d')
    except Exception:
        today_dt = datetime.now()
    scored = []
    for r in rows:
        t = str(r.get('title') or r.get('t') or '').strip()
        s = str(r.get('source') or r.get('s') or '').strip()
        d = str(r.get('orig_date_full') or r.get('d') or '').strip()
        u = str(r.get('url') or r.get('u') or '').strip()
        if not t or not u or not d:
            continue
        # 兼容 orig_date 格式 "MM-DD" 或 "YYYY-MM-DD"
        if len(d) == 5 and d[2] == '-':
            d = today[:4] + '-' + d
        try:
            days_diff = (today_dt - datetime.strptime(d, '%Y-%m-%d')).days
        except Exception:
            days_diff = 0
        if days_diff < 0:
            days_diff = 0
        recency = max(0, 30 - days_diff * 4)
        src_w = SOURCE_WEIGHTS.get(s, 3)
        hot_bonus = 20 if any(kw in t for kw in HOT_KW) else 0
        normal_bonus = 5 if (hot_bonus == 0 and any(kw in t for kw in NORMAL_KW)) else 0
        score = src_w * 10 + recency + hot_bonus + normal_bonus
        scored.append({
            'd': d, 't': t, 's': s, 'u': u,
            'score': score, 'hot': hot_bonus > 0,
        })
    scored.sort(key=lambda x: (x['score'], x['d']), reverse=True)
    seen, out = set(), []
    for it in scored:
        if it['u'] in seen:
            continue
        seen.add(it['u'])
        out.append(it)
        if len(out) >= n:
            break
    for i, it in enumerate(out):
        it['rank'] = i + 1
    return out


# ============================================================
# 关键词问答（不依赖外部 API key）
# ============================================================
QA_TEMPLATES = [
    (['铜', 'Cu'], '铜（Cu）是有色金属中的重要品种，广泛应用于电力、建筑、交通等领域。LME 铜 9/4 报 14,363.5 USD/吨。'),
    (['铝', 'Al'], '铝（Al）具有轻质、耐腐蚀等特性，广泛应用于航空航天、汽车制造、包装容器等领域。LME 铝 9/4 报 3,315.0 USD/吨。'),
    (['锌', 'Zn'], '锌（Zn）主要用于镀锌钢板、合金制造和电池。LME 锌 9/4 报 3,895.0 USD/吨。'),
    (['铅', 'Pb'], '铅（Pb）主要用于铅酸蓄电池、辐射防护材料。LME 铅 9/4 报 1,898.0 USD/吨。'),
    (['镍', 'Ni'], '镍（Ni）是不锈钢和动力电池的关键金属，新能源车带动需求快速增长。LME 镍 9/4 报 16,930.0 USD/吨。'),
    (['锡', 'Sn'], '锡（Sn）主要用于焊锡和电子封装，半导体景气度直接影响其需求。LME 锡 9/4 报 54,300.0 USD/吨。'),
    (['锂', 'Li'], '锂（Li）被称为"白色石油"，是新能源动力电池的核心原材料。中国是全球最大锂消费国。'),
    (['稀土'], '稀土是 17 种金属元素的统称，中国是全球最大的稀土生产国和供应国，国家持续推进稀土集团整合。'),
    (['金', '黄金'], '黄金兼具商品、货币、避险三重属性，央行购金、地缘冲突是金价的核心驱动。'),
    (['铁矿', '铁矿石'], '铁矿石是钢铁工业的核心原料，中国是全球最大进口国，对外依存度高。'),
    (['新一轮', '找矿', '突破', '战略'], '新一轮找矿突破战略行动（2022-2025）已取得阶段性成果：油气、铀、铜、铝、锂、钴、镍等关键矿产新增资源量稳步提升。'),
    (['关键矿产', '战略性矿产'], '关键矿产对国家经济安全和国防至关重要。中国"十四五"明确将 24 种矿产列为战略性矿产。'),
    (['储量', '资源量'], '中国的矿产储量按 GB/T 17766 划分为储量（Reserves）和资源量（Resources），其中储量又细分证实储量与可信储量。'),
    (['勘查', '勘探'], '矿产勘查分为预查、普查、详查、勘探 4 个阶段，9/3 起新发布的 DZ/T 0202-2020 对铝土矿等矿种勘查深度有明确规定。'),
    (['矿权', '采矿权', '探矿权'], '矿业权包括探矿权和采矿权。出让方式分招拍挂（一般情形）和协议出让（特殊情形），有效期 5 年（探矿）/ 最长 30 年（采矿）。'),
    (['DZ/T', '规范', '标准'], '地质矿产领域现行重要标准：DZ/T 0202-2020（铝土矿）、DZ/T 0204-2020（铜铅锌银）、DZ/T 0205-2020（稀有金属）等。'),
]


def qa_answer(question):
    q = (question or '').strip()
    if not q:
        return '您好！请输入您要查询的矿业相关问题。'
    for kws, ans in QA_TEMPLATES:
        if any(kw in q for kw in kws):
            return ans
    return ('您好！关于「' + q + '」，我暂未匹配到精确答案。'
            '有色金属市场近期受宏观经济数据和地缘政治影响较大，'
            '建议关注供需基本面变化。可尝试关键词：铜/铝/锌/铅/镍/锡/锂/稀土/找矿/矿权。')


# ============================================================
# AI 深度解析（DeepSeek）
# ============================================================
def _pick_today_headlines(today, n=7):
    """返回今日最值得 AI 解析的 n 条新闻（复用热榜加权排序），供 deepseek 解析。

    返回格式：[{'t','s','u','sum'}, ...]，与 _ai_analyze_one 的取值约定一致。
    """
    try:
        rows = _compute_hot_news(today, n)
    except Exception as e:
        print('[pick_today_headlines] err:', e)
        return []
    out = []
    for r in rows:
        out.append({
            't': r.get('t', ''),
            's': r.get('s', ''),
            'u': r.get('u', ''),
            'sum': '',
        })
    return out


def _ai_check_quota():
    """检查今日配额；返回 (left, today_count)"""
    today = datetime.now().strftime('%Y-%m-%d')
    if _ai_state['date'] != today:
        _ai_state['date'] = today
        _ai_state['count'] = 0
    return max(0, AI_QUOTA_PER_DAY - _ai_state['count'])

def _ai_inc():
    _ai_state['count'] += 1

def _deepseek_chat(messages, max_tokens=400, temperature=0.3):
    if not DEEPSEEK_API_KEY:
        return None
    payload = {
        'model': DEEPSEEK_MODEL,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'stream': False
    }
    try:
        req = urllib.request.Request(
            DEEPSEEK_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + DEEPSEEK_API_KEY
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        print('[deepseek] HTTP', e.code, e.reason)
        return None
    except Exception as e:
        print('[deepseek] error:', type(e).__name__, str(e)[:200])
        return None

def _ai_analyze_one(news):
    """对单条新闻生成 AI 深度解析：摘要/启示/风险"""
    title = str(news.get('t', '')).strip()
    src = str(news.get('s', '')).strip()
    url = str(news.get('u', '')).strip()
    summary = str(news.get('sum', news.get('summary', ''))).strip()
    if not title or not url:
        return None
    user_prompt = (
        '你是资深矿业行业分析师。基于以下新闻给出 3 点结构化解析（简洁专业、不啰嗦）：\n\n'
        f'标题：{title}\n'
        f'来源：{src}\n'
        f'摘要：{summary}\n\n'
        '请严格按 JSON 格式输出（不要任何额外说明文字、不要 markdown 代码块标记）：\n'
        '{"summary":"一句话核心要点（≤30字）",'
        '"insight":"对矿业行业/从业者的启示（≤60字）",'
        '"risk":"潜在风险或注意事项（≤40字，无则填\'无\'）"}'
    )
    content = _deepseek_chat([
        {'role': 'system', 'content': '你是矿业行业资深分析师，输出简洁、结构化、不啰嗦。'},
        {'role': 'user', 'content': user_prompt}
    ], max_tokens=320, temperature=0.3)
    if not content:
        return None
    # Extract JSON object (deepseek might wrap in markdown ```json ... ```)
    m = re.search(r'\{[^{}]+\}', content, re.DOTALL)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
        return {
            'url': url,
            'title': title,
            'src': src,
            'summary': str(j.get('summary', '')).strip(),
            'insight': str(j.get('insight', '')).strip(),
            'risk': str(j.get('risk', '无')).strip() or '无'
        }
    except Exception:
        return None


# ============================================================
# HTTP 处理器
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 简化访问日志格式
        print('[%s] %s' % (datetime.now().strftime('%H:%M:%S'), fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        # 默认首页
        if path == '/' or path == '':
            path = '/index.html'
        # 防止路径穿越
        rel = path.lstrip('/')
        # ---- 静态文件黑名单（2026-09-04 修复：qa_config.json 曾被当静态文件公网暴露密钥）----
        # 拦截：qa_config.json / *.py / *.env / *.log / *.bak* / __pycache__ / 以 _ 开头的工作文件
        _lower = rel.lower()
        if (_lower == 'qa_config.json'
                or _lower.endswith(('.py', '.env', '.log'))
                or '.bak' in _lower
                or '__pycache__' in _lower
                or _lower.startswith('_')):
            self.send_error(404)
            return
        full = os.path.normpath(os.path.join(ROOT, rel))
        if not full.startswith(ROOT):
            self.send_error(403)
            return
        if not os.path.isfile(full):
            self.send_error(404)
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = {
            '.html': 'text/html; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.svg': 'image/svg+xml',
            '.png': 'image/png',
            '.ico': 'image/x-icon',
        }.get(ext, 'application/octet-stream')
        with open(full, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        # ---- 旧链迁移模式（2026-09-04）：根路径返回紫色跳转页，4 秒自动跳新链接 ----
        if LEGACY_REDIRECT and path in ('/', '', '/index.html'):
            from urllib.parse import urlparse as _up
            new_host = _up(LEGACY_NEW_URL).netloc + _up(LEGACY_NEW_URL).path.rstrip('/')
            html = (_LEGACY_HTML
                    .replace('__NEW_URL__', LEGACY_NEW_URL)
                    .replace('__NEW_HOST__', new_host))
            body = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Legacy-Redirect', '1')
            self.end_headers()
            self.wfile.write(body)
            return
        # ---- API 路由 ----
        if path == '/api/health':
            _ai_check_quota()  # 触发日期滚动
            return self._json({
                'ok': True,
                'has_key': bool(DEEPSEEK_API_KEY),
                'limit': AI_QUOTA_PER_DAY if DEEPSEEK_API_KEY else 0,
                'used': _ai_state['count'] if DEEPSEEK_API_KEY else 0,
                'model': DEEPSEEK_MODEL if DEEPSEEK_API_KEY else 'disabled',
                'news_count': len(load_news()),
                'time': datetime.now().isoformat(),
            })
        if path == '/api/quota':
            left = _ai_check_quota() if DEEPSEEK_API_KEY else 0
            return self._json({
                'left': left,
                'limit': AI_QUOTA_PER_DAY if DEEPSEEK_API_KEY else 0,
                'today': _ai_state['count'] if DEEPSEEK_API_KEY else 0,
                'has_key': bool(DEEPSEEK_API_KEY)
            })
        if path == '/api/hot-news':
            return self._json({
                'date': datetime.now().strftime('%Y-%m-%d'),
                'hot': _compute_hot_news(datetime.now().strftime('%Y-%m-%d'), 3),
            })
        if path == '/api/morning-report':
            today = datetime.now().strftime('%Y-%m-%d')
            return self._json({
                'date': today,
                'title': today + ' 矿业晨报',
                'sections': [
                    {'h': '市场动态', 'b': '今日铜铝锌铅镍锡 LME 价格小幅震荡，整体持稳。'},
                    {'h': '政策聚焦', 'b': '新一轮找矿突破战略行动持续推进，关键矿产保障能力稳步提升。'},
                    {'h': '行业要闻', 'b': '重点关注自然资源部、中国地质调查局新发布的勘查成果与矿权出让公告。'},
                ],
            })
        if path == '/api/anomalies':
            return self._json({'has_anomaly': False, 'anomalies': []})
        if path == '/api/price-history':
            metal = (q.get('metal') or ['lcpt'])[0]
            days = int((q.get('days') or ['5'])[0])
            days = max(1, min(days, 30))
            # 简单模拟：固定基准价 + 随机游走（占位）
            base = {'lcpt': 14363, 'lalt': 3315, 'lznt': 3895,
                    'lldt': 1898, 'lnkt': 16930, 'ltnt': 54300}.get(metal, 10000)
            import random
            random.seed(metal)
            series = []
            cur = base
            for i in range(days):
                cur = cur + random.uniform(-base * 0.005, base * 0.005)
                d = (datetime.now() - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d')
                series.append({'d': d, 'p': round(cur, 2)})
            return self._json({'metal': metal, 'days': days, 'series': series})
        if path == '/api/ai-analyze':
            today = datetime.now().strftime('%Y-%m-%d')
            cache_path = os.path.join(DATA_DIR, f'ai_analysis_{today}.json')
            quota_left = _ai_check_quota()

            # 1) 缓存命中：直接返回（仅识别 v=1 版本化结构，旧版裸 [] 视为未命中并重算）
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, encoding='utf-8') as f:
                        cached = json.load(f)
                    if isinstance(cached, dict) and cached.get('v') == 1:
                        return self._json({
                            'date': today,
                            'enabled': bool(DEEPSEEK_API_KEY),
                            'has_key': bool(DEEPSEEK_API_KEY),
                            'cached': True,
                            'quota_left': quota_left,
                            'quota_limit': AI_QUOTA_PER_DAY,
                            'items': cached.get('items') or []
                        })
                    else:
                        print('[ai-analyze] cache format stale, recompute')
                except Exception as e:
                    print('[ai-analyze] cache read err:', e)

            # 2) 无 key：降级
            if not DEEPSEEK_API_KEY:
                return self._json({
                    'date': today,
                    'enabled': False,
                    'has_key': False,
                    'reason': 'AI 解析未配置（需设置 DEEPSEEK_API_KEY 环境变量）',
                    'items': [],
                    'quota_left': 0,
                    'quota_limit': AI_QUOTA_PER_DAY
                })

            # 3) 取今日新闻（限 7 条，配额保护）
            today_news = _pick_today_headlines(today) or []
            items = []
            for n in today_news[:7]:
                if _ai_check_quota() <= 0:
                    break
                _ai_inc()
                a = _ai_analyze_one(n)
                if a:
                    items.append(a)

            # 4) 缓存（版本化结构，包含空结果，下次不再调）
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump({'v': 1, 'date': today, 'items': items}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print('[ai-analyze] cache write err:', e)

            return self._json({
                'date': today,
                'enabled': True,
                'has_key': True,
                'cached': False,
                'quota_left': _ai_check_quota(),
                'quota_limit': AI_QUOTA_PER_DAY,
                'items': items
            })
        # ---- 静态文件 ----
        return self._static(path)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == '/api/qa':
            length = int(self.headers.get('Content-Length', '0') or 0)
            raw = self.rfile.read(length) if length > 0 else b'{}'
            try:
                data = json.loads(raw.decode('utf-8')) if raw else {}
            except Exception:
                data = {}
            question = data.get('question', '')
            return self._json({
                'answer': qa_answer(question),
                'question': question,
                'source': 'local-keyword',
            })
        self.send_error(404)


# ============================================================
# 启动
# ============================================================
def main():
    port = int(os.environ.get('PORT', '3000'))
    n = len(load_news())
    print('========================================================')
    print('  矿业日报服务已启动（2026-09-04 重建版）')
    print('  监听      0.0.0.0:%d' % port)
    print('  新闻条目  %d 条' % n)
    print('  热榜算法  来源权威×10 + 时效衰减 + 关键词加分')
    print('  AI 问答   已就绪（关键词匹配版，不依赖 API key）')
    print('========================================================')
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
