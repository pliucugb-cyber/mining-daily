# -*- coding: utf-8 -*-
"""
validate_urls.py — 扫描 output/mining-daily/index.html 中所有新闻 URL，
验证可访问性和标题-内容匹配度。

校验规则（任一不通过即标记为"待修复"）：
  1. HTTP 状态码 >= 400 → 失效（403/429 若 body>5KB 视为反爬，降级为警告）
  2. 返回内容 < 5KB → 列表页嫌疑（可能 URL 失效）
  3. 标题关键词未在内容中匹配到（命中 < 40%）→ 错挂源/URL 错配嫌疑

输出：
  - 控制台报告
  - 写入 validate_report.md（含失效清单 + 修复建议）

用法：
  python validate_urls.py                    # 校验并报告
  python validate_urls.py --fail-on-broken   # 若有失效则 exit 1（CI/自动化友好）
"""
import re
import sys
import time
from urllib.parse import urlparse
from pathlib import Path
import urllib.request
import urllib.error

OUTPUT_HTML = Path(__file__).parent / 'index.html'
REPORT_MD = Path(__file__).parent / 'validate_report.md'

# 停用词（不参与标题关键词匹配）
STOPWORDS = set('的地得了在是为和与及或了着过一中上下年月日时分秒点条')

# 标识"列表页嫌疑"的最小返回字节数
LIST_PAGE_THRESHOLD = 5_000

# 单次请求超时（秒）
TIMEOUT = 12

# 同一域名请求间隔（防 WAF / 防频率限制）
DOMAIN_COOLDOWN = 0.5

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def extract_news_items():
    """从 index.html 提取所有新闻条目的 (url, title, src, date)。

    优先读取 data-url 属性，并验证同一 news-item 内所有 href 与其一致。
    """
    text = OUTPUT_HTML.read_text(encoding='utf-8')
    items = []
    pattern = re.compile(
        r'<div class="news-item[^"]*" data-url="([^"]+)"[^>]*>'
        r'.*?<a class="news-title" href="([^"]+)" target="_blank">([^<]+)</a>'
        r'.*?<span class="src">([^<]+)</span>\s*·\s*([^<]+)'
        r'.*?<div class="news-summary">([^<]+)</div>',
        re.S
    )
    for m in pattern.finditer(text):
        data_url, href, title, src, date, summary = m.groups()
        items.append({
            'url': data_url,
            'href': href,
            'title': title.strip(),
            'src': src.strip(),
            'date': date.strip(),
            'summary': summary.strip(),
            'url_consistent': data_url == href
        })
    return items


def keywords_of(title):
    """从标题提取关键词（中文 2 字以上、剔除停用词）。"""
    tokens = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}', title)
    out = []
    for t in tokens:
        if re.match(r'[\u4e00-\u9fff]+', t):
            for i in range(len(t) - 1):
                w = t[i:i+2]
                if not all(c in STOPWORDS for c in w):
                    out.append(w)
        else:
            out.append(t)
    seen = set()
    uniq = []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
        if len(uniq) >= 8:
            break
    return uniq


def fetch(url, last_domain_ts):
    """GET 一个 URL，返回 (status, body_bytes, body_text)。"""
    domain = urlparse(url).netloc
    now = time.time()
    wait = last_domain_ts.get(domain, 0) + DOMAIN_COOLDOWN - now
    if wait > 0:
        time.sleep(wait)
    last_domain_ts[domain] = time.time()

    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            text = body.decode('utf-8', errors='ignore')
            return resp.status, len(body), text[:200_000]
    except urllib.error.HTTPError as e:
        body = e.read()
        text = body.decode('utf-8', errors='ignore') if body else ''
        return e.code, len(body), text[:200_000]
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, 0, f'[NETWORK ERROR] {e}'
    except Exception as e:
        return 0, 0, f'[ERROR] {e}'


def check_one(item, last_domain_ts):
    """对一条新闻做完整校验，返回 (status, findings)。"""
    url = item['url']
    title = item['title']
    src = item.get('src', '')
    findings = []

    # 前置：data-url 与标题 href 不一致
    if not item.get('url_consistent', True):
        findings.append('❌ 同一新闻条目内 data-url 与标题链接 href 不一致（HTML 内部错配）')

    status_code, body_len, body_text = fetch(url, last_domain_ts)

    # 规则 1：HTTP 状态码
    if status_code == 0:
        findings.append('❌ 网络错误/超时（无法访问）')
    elif status_code >= 400:
        if status_code in (403, 429) and body_len > LIST_PAGE_THRESHOLD:
            findings.append(f'⚠️ HTTP {status_code}（反爬限制，curl 被拒但浏览器实际能开，body {body_len}B）')
        elif status_code in (403, 429):
            findings.append(f'⚠️ HTTP {status_code}（反爬限制或临时拒绝）')
        else:
            findings.append(f'❌ HTTP {status_code}（失效）')
    elif status_code >= 300:
        findings.append(f'⚠️ HTTP {status_code}（重定向）')

    # 规则 2：返回内容过短
    if status_code == 200 and body_len < LIST_PAGE_THRESHOLD:
        findings.append(f'⚠️ 内容仅 {body_len}B（< 5KB，列表页嫌疑——参数化 URL 失效）')

    # 规则 3：标题关键词匹配
    keywords = keywords_of(title)
    if status_code == 200 and keywords:
        hit = sum(1 for k in keywords if k in body_text)
        if hit == 0:
            findings.append(f'❌ 标题关键词 0/{len(keywords)} 命中（{keywords[:3]}…）——可能错挂源或 URL 错配')
        elif hit / len(keywords) < 0.4:
            findings.append(f'⚠️ 标题关键词只命中 {hit}/{len(keywords)}（{keywords}）——疑似错挂')

    # 规则 4：WAF / JS challenge 检测
    if 'wtsjsk' in body_text or 'Browser security check' in body_text or 'Browser security' in body_text:
        findings.append('⚠️ WAF 拦截（页面带 JS challenge，浏览器能绕过但 curl 过不了）')

    ok = not any(f.startswith('❌') for f in findings)
    return ok, findings


def main():
    if not OUTPUT_HTML.exists():
        print(f'❌ 找不到 {OUTPUT_HTML}')
        sys.exit(1)

    items = extract_news_items()
    print(f'从 {OUTPUT_HTML} 扫到 {len(items)} 条新闻 URL 待校验\n')

    last_domain_ts = {}
    results = []
    for i, p in enumerate(items, 1):
        ok, findings = check_one(p, last_domain_ts)
        flag = '✅' if ok else '❌'
        kw = keywords_of(p['title'])
        print(f'{flag} [{i}/{len(items)}] {p["src"]} · {p["date"]} · {p["title"][:45]}')
        print(f'   URL: {p["url"]}')
        print(f'   关键词: {kw}')
        for f in findings:
            print(f'   {f}')
        print()
        results.append({**p, 'ok': ok, 'findings': findings, 'keywords': kw})

    # 汇总
    total = len(results)
    broken = [r for r in results if not r['ok']]
    warned = [r for r in results if r['ok'] and any('⚠️' in f for f in r['findings'])]
    print('=' * 60)
    print(f'总计: {total} 条 | 失效: {len(broken)} 条 | 警告: {len(warned)} 条')

    # 写报告
    md = ['# URL 校验报告', '', f'校验时间: {time.strftime("%Y-%m-%d %H:%M:%S")}',
          f'扫描文件: {OUTPUT_HTML}', '', '## 汇总', '',
          f'- 总计: **{total}** 条',
          f'- ✅ 正常: **{total - len(broken) - len(warned)}** 条',
          f'- ⚠️ 警告: **{len(warned)}** 条',
          f'- ❌ 失效: **{len(broken)}** 条', '']
    if broken:
        md.append('## ❌ 失效清单（必须修复）')
        md.append('')
        for r in broken:
            md.append(f"### {r['title']}")
            md.append(f"- URL: `{r['url']}`")
            md.append(f"- 来源: {r['src']} · {r['date']}")
            md.append(f"- 关键词: {r['keywords']}")
            for f in r['findings']:
                md.append(f"- {f}")
            md.append('')
    if warned:
        md.append('## ⚠️ 警告清单（建议核查）')
        md.append('')
        for r in warned:
            md.append(f"### {r['title']}")
            md.append(f"- URL: `{r['url']}`")
            md.append(f"- 来源: {r['src']} · {r['date']}")
            for f in r['findings']:
                md.append(f"- {f}")
            md.append('')
    REPORT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(f'\n报告写入: {REPORT_MD}')

    if '--fail-on-broken' in sys.argv and broken:
        sys.exit(1)


if __name__ == '__main__':
    main()
