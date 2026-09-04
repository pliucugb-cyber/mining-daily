# -*- coding: utf-8 -*-
"""
batch_check_embed.py — 批量检测 index.html 中所有新闻 URL 的 iframe 嵌入权限
原理：跨域 iframe 的加载状态在前端 JS 侧无法可靠检测（onload/onerror/scrollHeight 都有缺陷），
      所以在生成侧直接读 HTTP 响应头，把结果作为 data-embed="ok|block" 写进 HTML 标签。
判断规则：
  - X-Frame-Options: DENY / SAMEORIGIN → block（第三方嵌入被拒）
  - Content-Security-Policy 含 frame-ancestors 'none'/'self'（不含本站） → block
  - 无上述限制 → ok
  - 请求失败（超时/SSL） → ok（保守：让前端 iframe 试试，浮窗里有 ↗ 外站 兜底）
用法：
  python batch_check_embed.py            # 检测并直接回填到 index.html
  python batch_check_embed.py --dry-run   # 只输出报告不修改文件
"""
import re
import sys
import concurrent.futures
from html.parser import HTMLParser

import requests

INDEX = r"C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\index.html"
TIMEOUT = 12
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


def check_url(url: str) -> dict:
    """检测单个 URL 的 iframe 嵌入权限。返回 {url, embed, reason}"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True, allow_redirects=True)
        # 只读响应头，不下载 body
        r.close()
        xfo = (r.headers.get("X-Frame-Options") or "").strip().upper()
        csp = (r.headers.get("Content-Security-Policy") or "").strip()
        # 逐条解析 CSP 里的 frame-ancestors（CSP 头可能有多条指令）
        fa_rules = []
        for directive in csp.split(";"):
            d = directive.strip()
            if d.lower().startswith("frame-ancestors"):
                fa_rules.append(d)
        if xfo in ("DENY",):
            return {"url": url, "embed": "block", "reason": f"X-Frame-Options: {xfo}"}
        if xfo == "SAMEORIGIN":
            return {"url": url, "embed": "block", "reason": "X-Frame-Options: SAMEORIGIN（第三方被拒）"}
        for rule in fa_rules:
            val = rule[len("frame-ancestors"):].strip().lower()
            if val in ("'none'", "self") or "http" in val:
                # 'none'/'self'/白名单域 → 第三方一律拒绝（我们的日报域名不可能在白名单里）
                return {"url": url, "embed": "block", "reason": f"CSP {rule}"}
        return {"url": url, "embed": "ok", "reason": "无嵌入限制"}
    except Exception as e:
        # 网络失败：保守标 ok（前端 iframe 仍会尝试，浮窗里有 ↗ 外站 按钮兜底）
        return {"url": url, "embed": "ok", "reason": f"检测失败({type(e).__name__})，保守放行"}


def main():
    dry_run = "--dry-run" in sys.argv
    with open(INDEX, "r", encoding="utf-8") as f:
        html = f.read()

    urls = sorted(set(re.findall(r'data-url="([^"]+)"', html)))
    print(f"共发现 {len(urls)} 个唯一 URL，开始并发检测（超时 {TIMEOUT}s）...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(check_url, urls))

    blocked = [r for r in results if r["embed"] == "block"]
    ok = [r for r in results if r["embed"] == "ok"]
    print(f"\n=== 检测结果：可嵌入 {len(ok)} | 禁止嵌入 {len(blocked)} ===")
    for r in blocked:
        print(f"  [BLOCK] {r['url']}\n         原因: {r['reason']}")

    if dry_run:
        print("\n(dry-run 模式，未修改文件)")
        return

    # 回填：给每个 news-item 的 data-url 后面插入 data-embed 属性
    # 先清掉旧标记避免重复
    html = re.sub(r'\s*data-embed="[^"]*"', "", html)
    for r in results:
        # data-url="..." → data-url="..." data-embed="..."
        html = html.replace(
            f'data-url="{r["url"]}"',
            f'data-url="{r["url"]}" data-embed="{r["embed"]}"',
        )
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)
    n_block = html.count('data-embed="block"')
    n_ok = html.count('data-embed="ok"')
    print(f"\n已回写到 index.html：block 标记 {n_block} 处，ok 标记 {n_ok} 处")


if __name__ == "__main__":
    main()
