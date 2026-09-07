#!/usr/bin/env python3
"""
矿业新闻日报信源白名单校验工具。

约定信源（memory 2026-09-07 固化，2026-09-07 晚扩展 2 个）：
- ky.mnr.gov.cn          全国矿业权市场网（矿权出让/转让/结果）
- mnr.gov.cn             自然资源部官网
- cgs.gov.cn             中国地质调查局（含各中心子域，如 xgsnrc.cgs.gov.cn）
- chinania.org.cn        中国有色金属工业协会
- cnmn.com.cn            中国有色金属报/中国金属网
- geoglobal.mnr.gov.cn   全球矿产资源信息系统
- cngold.org.cn          中国黄金协会
- chinamining.org.cn     中国矿业网 / 中国矿业联合会
- zgkyb.com              中国矿业报

使用方式：
    python source_whitelist.py --check-url <url>
    python source_whitelist.py --check-file <html_or_json>
    python source_whitelist.py --list
"""
import argparse
import re
import sys
from urllib.parse import urlparse

ALLOWED_DOMAINS = [
    "ky.mnr.gov.cn",
    "mnr.gov.cn",
    "cgs.gov.cn",
    "chinania.org.cn",
    "cnmn.com.cn",
    "geoglobal.mnr.gov.cn",
    "cngold.org.cn",
    "chinamining.org.cn",
    "zgkyb.com",
]

# 非新闻来源的功能/统计/API 链接，校验时跳过
SKIP_PATTERNS = [
    re.compile(r"mining-daily\.goatcounter\.com", re.I),
    re.compile(r"pliucugb-cyber\.github\.io", re.I),
    re.compile(r"api\.deepseek\.com", re.I),
]


def is_allowed(url: str) -> bool:
    """判断 URL 是否落在白名单域名或其子域下。"""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or parsed.path).lower().lstrip("www.")
    except Exception:
        return False
    if not host:
        return False
    for d in ALLOWED_DOMAINS:
        if host == d or host.endswith("." + d):
            return True
    return False


def find_urls_in_text(text: str):
    """从文本/HTML/JSON 中提取 http(s) URL。"""
    return re.findall(r'https?://[^\s"\'<>\)\]\}]+', text)


def should_skip(url: str) -> bool:
    """非新闻来源的功能/统计/API 链接，不参与白名单校验。"""
    return any(p.search(url) for p in SKIP_PATTERNS)


def check_file(path: str) -> dict:
    """检查文件内所有 URL 的白名单状态，返回统计与违规列表。"""
    text = open(path, "r", encoding="utf-8").read()
    urls = find_urls_in_text(text)
    seen = set()
    violations = []
    skipped = []
    for u in urls:
        # 去重：忽略尾部标点或斜杠差异导致的重复
        normalized = u.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        if should_skip(u):
            skipped.append(u)
            continue
        if not is_allowed(u):
            violations.append(u)
    return {
        "total_unique": len(seen),
        "skipped": skipped,
        "violations": violations,
    }


def main():
    parser = argparse.ArgumentParser(description="矿业日报信源白名单校验")
    parser.add_argument("--check-url", help="校验单个 URL")
    parser.add_argument("--check-file", help="校验文件内所有 URL")
    parser.add_argument("--list", action="store_true", help="列出白名单")
    parser.add_argument("--fail-on-error", action="store_true", help="发现违规时 exit 1")
    args = parser.parse_args()

    if args.list:
        print("ALLOWED_DOMAINS:")
        for d in ALLOWED_DOMAINS:
            print(f"  {d}")
        return

    if args.check_url:
        ok = is_allowed(args.check_url)
        print(f"{'ALLOWED' if ok else 'BLOCKED'}: {args.check_url}")
        sys.exit(0 if ok else 1)

    if args.check_file:
        res = check_file(args.check_file)
        print(f"Total unique URLs: {res['total_unique']} (skipped functional: {len(res.get('skipped', []))})")
        if res["violations"]:
            print(f"BLOCKED ({len(res['violations'])}):")
            for u in res["violations"]:
                print(f"  {u}")
            if args.fail_on_error:
                sys.exit(1)
        else:
            print("All URLs are from allowed sources.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
