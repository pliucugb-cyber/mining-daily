#!/usr/bin/env python3
"""
矿业新闻日报信源白名单校验工具。

约定信源（memory 2026-09-07 固化，2026-09-07 晚扩展 4 个）：
- ky.mnr.gov.cn          全国矿业权市场网（矿权出让/转让/结果）
- mnr.gov.cn             自然资源部官网
- cgs.gov.cn             中国地质调查局（含各中心子域，如 xgsnrc.cgs.gov.cn）
- chinania.org.cn        中国有色金属工业协会
- cnmn.com.cn            中国有色金属报/中国金属网
- geoglobal.mnr.gov.cn   全球矿产资源信息系统
- cngold.org.cn          中国黄金协会
- chinamining.org.cn     中国矿业网 / 中国矿业联合会
- zgkyb.com              中国矿业报
- cninfo.com.cn          巨潮资讯网（A股/北交所/港股官方披露平台，并购/投资类公告来源，2026-09-07 新增）
- smm.cn                 上海有色网 SMM（有色金属现货基准价发布方；补价格行情、库存/港口出港量、
                         钛/铌/钽/锑等小金属快讯。覆盖 www.smm.cn / news.smm.cn 等子域。
                         2026-09-07 覆盖度核查 P0 新增。注意部分深度报告付费，取公开资讯页）
- antaike.com            安泰科（中国有色金属工业协会下属研究机构；补行业分析、产量数据、政策解读。
                         2026-09-07 覆盖度核查 P0 新增）

境外信源（2026-09-08 覆盖度核查 P2 新增，均经国内网络实测可达，详见文件尾「境外源准入规则」）：
- metal.com              SMM 上海有色网国际站（英文）。含 www.metal.com / news.metal.com。
                         ⚠️ 最优境外源：中国团队运营、境内直连无墙、英文内容、有色全品种，
                            且自带 SHFE/LME 库存与进口套利数据（补「贸易进出口/库存 0%」缺口）
- icsg.org               国际铜研究组（ICSG）：铜供需平衡、产量、库存月度数据
- ilzsg.org              国际铅锌研究组（ILZSG）：铅锌供需与库存
- insg.org               国际镍研究组（INSG）：镍供需与库存
- world-aluminium.org    国际铝业协会（IAI）：全球原铝产量月度数据
- lme.com                伦敦金属交易所（LME）官方：与站内 LME 六金属卡片直接对口
- mining.com             全球矿业新闻综合（英文，量大日更）⚠️ 须排除 sponsored 广告路径
- kitco.com              贵金属行情与矿业新闻（金银铂钯）
- gold.org               世界黄金协会

已被实测否决、禁止引入的境外源（勿重复提议）：
- reuters.com / bloomberg.com  → 国内不可达（HTTP 000，对照组百度/腾讯 200 正常）
- usgs.gov / minerals.usgs.gov → 反爬拦截，正文返回 0 字节
- mining-journal.com / fastmarkets.com → 付费墙（付费关键词命中 10 次 / 订阅制）
- cochilco.cl                → 国内不可达

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
    "cninfo.com.cn",
    # 2026-09-07 覆盖度核查 P0 新增（补价格行情/贸易库存/小金属/行业分析缺口）
    "smm.cn",        # 上海有色网（含 www.smm.cn / news.smm.cn 等子域）
    "antaike.com",   # 安泰科（中国有色金属工业协会下属研究机构）
    # ===== 2026-09-08 覆盖度核查 P2：境外源（全部经国内网络实测可达才准入） =====
    # 准入硬门槛：① 国内 curl 实测 HTTP 非 000 且正文非空；② 无付费墙/注册墙；
    #            ③ 与有色金属行业直接相关。三项缺一不入。
    "metal.com",             # SMM 国际站（英文，境内直连，含库存/进口套利数据）★首选
    "icsg.org",              # 国际铜研究组
    "ilzsg.org",             # 国际铅锌研究组
    "insg.org",              # 国际镍研究组
    "world-aluminium.org",   # 国际铝业协会（IAI）
    "lme.com",               # 伦敦金属交易所
    "mining.com",            # 全球矿业新闻（须排除 /sponsored-content/ 与 /joint-venture/ 广告路径）
    "kitco.com",             # 贵金属
    "gold.org",              # 世界黄金协会
    # ===== 2026-09-08 覆盖度核查 P1 新增 =====
    "ccmn.cn",               # 长江有色网（现货视角资讯，与 SMM 互补）
    "szse.cn",               # 深圳证券交易所（公告直连，巨潮备份链路；含 disc.szse.cn）
]

# 白名单子域默认放行，但少数子域是营销/广告页而非新闻，必须显式否决。
# 2026-09-08：长江有色的商城与广告跳转子域会随主域 ccmn.cn 一起被放行，
# 若不拉黑，商城产品报价页可能被当成新闻收录。
BLOCKED_HOSTS = [
    "mall.ccmn.cn",   # 长江有色商城（「供应优质黄铜棒 网上协商价格」类产品页）
    "ad.ccmn.cn",     # 长江有色广告跳转
]

# 境外源采编禁用路径（2026-09-08）：这些路径是广告/软文，不是新闻，采编时必须跳过。
# 白名单校验不拦截（域名合法），但自动化 prompt 已写死须排除。
FOREIGN_SPONSORED_PATTERNS = [
    re.compile(r"mining\.com/(sponsored-content|joint-venture)/", re.I),
    re.compile(r"servedbyadbutler\.com", re.I),
]

# 非新闻来源的功能/统计/API 链接，校验时跳过
SKIP_PATTERNS = [
    re.compile(r"mining-daily\.goatcounter\.com", re.I),
    re.compile(r"pliucugb-cyber\.github\.io", re.I),
    re.compile(r"api\.deepseek\.com", re.I),
    re.compile(r"mining-daily-qa\.netlify\.app", re.I),
]


def is_allowed(url: str) -> bool:
    """判断 URL 是否落在白名单域名或其子域下。"""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or parsed.path).lower()
        # 2026-09-08 修复：原用 lstrip("www.") 属按「字符集」剥离而非按前缀，
        # 会把 world-aluminium.org 误剥成 orld-aluminium.org 导致合法源被拒。
        host = host[4:] if host.startswith("www.") else host
    except Exception:
        return False
    if not host:
        return False
    # 显式否决优先于白名单：商城/广告子域随主域放行，必须单独拦掉
    if host in BLOCKED_HOSTS:
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
