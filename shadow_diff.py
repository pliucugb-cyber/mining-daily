#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shadow_diff.py v5 —— 影子模式对比（2026-10-21 重构语义）

⚠️ v5 关键更正（2026-10-21 用 git/GitHub API 证据确诊）：
   脚本原以为 ONLINE_HTML(/var/www/mining-daily) 是"云自部署镜像"，**错了**。
   真相：该目录由 `git fetch origin gh-pages && git reset --hard origin/gh-pages`
   刷新，而 gh-pages 的唯一写者是**本机 WorkBuddy**（提交者 mining-daily@local）。
   云端自 10-16 起不再推 gh-pages（决定记录见 setup_bprime.sh 注释）。
   → 所以「线上」侧其实是**本机产物**，「云」侧是云端产物：
      这是一次**跨源内容池对比**，不是同源部署一致性检查。
   → 证据：线上链接数 10-19/20/21 = 541/542/549，与 gh-pages 三个提交的
      index.html 链接数**精确吻合**，说明镜像刷新每天都成功、部署没坏。

   因此 v5 把三类差异彻底分开，各归各位：
     A. 云端漏抓（本机有、云无）        ← 唯一值得追的质量信号
     B. 同故事异标题（措辞/来源前缀差异）← 非漏抓，仅计数
     C. 内容池差异（云有、线上无）      ← 云端多出的往期归档，**非部署问题**
   旧的"真漏抓"算的是 A 的镜像方向（线上有、云无），在跨源前提下语义混乱，
   v5 改名为「内容池差异」并明确不做告警。

v4 沿用的护栏仍有效：
  1. 同步基线校验：线上全站 < 云版 × SYNC_RATIO → 输出 `对比基线: 异常`。
  2. jaccard 两侧皆空返回 0.0（不谎报 100%）。
  3. 拆分"线上独有"与"云有线上无"。

部署提示：本脚本此前**不在 git 里**（main / shadow-reports 均 404），
          只存在于服务器本地，导致本地修复永远传不上去、服务器长期跑老版。
          v5 起纳入 main，服务器用 `git show origin/main:shadow_diff.py > shadow_diff.py` 更新。
"""
import os
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from html.parser import HTMLParser

CLOUD_HTML = "/opt/md-src/index.html"
ONLINE_HTML = "/var/www/mining-daily/index.html"
ONLINE_ONLY_WARN = 10   # 今日(含无日期)线上独有链接预警阈值
TITLE_RATIO = 0.55      # 标题相似度 >= 此值判为"同故事异标题"
SYNC_RATIO = 0.9        # 线上全站链接 >= 云版×此值 才认为同步正常

DATE_PATH = re.compile(r'/(20\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/')
DATE_FLAT = re.compile(r'(20\d{2})[-/]?(\d{2})[-/]?(\d{2})')


def parse_url_date(url):
    m = DATE_PATH.search(url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = DATE_FLAT.search(url)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if len(mo) == 2 and len(d) == 2:
            return f"{y}-{mo}-{d}"
    return None


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = set()
        self.texts = []
        self._in_a = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_a = True
            self._buf = []
            for k, v in attrs:
                if k == "href" and v:
                    self.links.add(v.strip())

    def handle_endtag(self, tag):
        if tag == "a":
            txt = "".join(self._buf).strip()
            if txt:
                self.texts.append(txt)
            self._in_a = False
            self._buf = []

    def handle_data(self, data):
        if self._in_a:
            self._buf.append(data)


def load(path):
    if not os.path.exists(path):
        print(f"[error] 文件不存在: {path}")
        sys.exit(2)
    with open(path, encoding="utf-8", errors="ignore") as f:
        html = f.read()
    p = Collector()
    p.feed(html)
    texts = set()
    for t in p.texts:
        t = "".join(t.split())
        if len(t) >= 2:
            texts.add(t)
    return p.links, texts


def jaccard(a, b):
    # 两侧皆空：无数据可对比，严禁谎报 100%，返回 0.0
    if not a and not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def norm_title(t):
    t = re.sub(r'[●•·▶►|]', '', t)
    t = re.sub(r'【[^】]*】|（[^）]*）|\([^)]*\)|\[[^\]]*\]', '', t)
    t = re.sub(r'\s+', '', t)
    return t


def strip_source(t):
    m = re.match(r'^[^：:]{1,10}[：:](.+)$', t)
    return m.group(1) if m else t


def best_match(t, pool):
    tn = norm_title(t)
    tc = strip_source(tn)
    best, score = None, 0.0
    for c in pool:
        cn = norm_title(c)
        r = max(SequenceMatcher(None, tn, cn).ratio(),
                SequenceMatcher(None, tc, strip_source(cn)).ratio())
        if r > score:
            score, best = r, c
    return best, score


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()
    today = args.date

    cloud_links, cloud_texts = load(CLOUD_HTML)
    online_links, online_texts = load(ONLINE_HTML)

    # --- 同步基线校验（v4 新增）---
    # 云版是内容源，线上是部署目标。线上严重滞后时对比无效。
    sync_threshold = int(len(cloud_links) * SYNC_RATIO)
    sync_ok = len(online_links) >= sync_threshold

    cloud_today = {u for u in cloud_links if parse_url_date(u) == today}
    online_today = {u for u in online_links if parse_url_date(u) == today}

    online_only = online_links - cloud_links   # 线上有、云无 → 待核查
    cloud_only = cloud_links - online_links     # 云有、线上无 → 部署滞后
    leak_today, leak_undated, archive_old = [], [], []
    for u in sorted(online_only):
        d = parse_url_date(u)
        if d is None:
            leak_undated.append(u)
        elif d < today:
            archive_old.append(u)
        else:
            leak_today.append(u)

    cloud_today_only = cloud_today - online_today  # 今日云有线上无 → 部署滞后

    print("=" * 64)
    print(f"影子模式对比报告  (report={today})")
    print("-" * 64)
    print("【全站对比】(含归档, 仅供参考)")
    print(f"  云: 链接{len(cloud_links)} 文本{len(cloud_texts)}"
          f" | 线上: 链接{len(online_links)} 文本{len(online_texts)}")
    print(f"  链接相似度 {jaccard(cloud_links, online_links)*100:.1f}%"
          f" | 标题相似度 {jaccard(cloud_texts, online_texts)*100:.1f}%")
    print(f"  同步状态: {'正常' if sync_ok else '异常(线上滞后/未同步)'}"
          f" | 阈值=云版×{SYNC_RATIO}({sync_threshold})")
    print("-" * 64)
    print("【今日链接对比】(仅含今天URL日期链接)")
    print(f"  云今日链接 {len(cloud_today)} | 线上今日链接 {len(online_today)}")
    print(f"  今日链接相似度: {jaccard(cloud_today, online_today)*100:.1f}%")
    print(f"  今日部署滞后(云有线上无) {len(cloud_today_only)} 条"
          f" | 今日线上独有(待核查) {len(leak_today)} 条"
          f" | 无日期 {len(leak_undated)} 条 | 归档漂移 {len(archive_old)} 条(已排除)")
    for x in leak_undated[:20]:
        print(f"     ? {x[:84]}")
    print("-" * 64)

    # 标题深查：两侧差异标题分别模糊匹配，拆成三类（见 v5 文件头说明）
    online_only_t = online_texts - cloud_texts   # 本机有、云无 → 云端可能漏抓
    cloud_only_t = cloud_texts - online_texts   # 云有、本机无 → 内容池差异

    variant, cloud_miss = [], []
    for t in sorted(online_only_t):
        best, score = best_match(t, cloud_texts)
        if score >= TITLE_RATIO:
            variant.append((t, best, score))
        else:
            cloud_miss.append((t, best, score))

    pool_diff = []
    for t in sorted(cloud_only_t):
        best, score = best_match(t, online_texts)
        pool_diff.append((t, best, score))

    print("【A. 云端漏抓】(本机有、云端无近似标题 — 唯一值得追的质量信号)")
    print(f"  ❌ 云端漏抓 {len(cloud_miss)} 条" + ("(基线异常，数字不可信)" if not sync_ok else ""))
    for t, b, s in cloud_miss[:40]:
        print(f"     - [{s:.2f}] {t[:56]}")
    print("-" * 64)

    print("【B. 同故事异标题】(措辞/来源前缀差异, 非漏抓, 仅计数)")
    print(f"  🔁 {len(variant)} 条")
    for t, b, s in variant[:15]:
        print(f"     ≈[{s:.2f}] {t[:40]}")
        print(f"        云版: {b[:40]}")
    print("-" * 64)

    print("【C. 内容池差异】(云端有、本机无 — 多为云端保留的往期归档，非部署问题、不告警)")
    print(f"  ℹ️ {len(pool_diff)} 条")
    for t, b, s in pool_diff[:12]:
        print(f"     · [{s:.2f}] {t[:56]}")
    print("-" * 64)

    cand = len(leak_today) + len(leak_undated)

    # --- 判定优先级（v5 调整：只对 A 类云端漏抓告警）---
    if not sync_ok:
        print(f"⚠️ 对比基线异常：线上全站仅 {len(online_links)} 条 < 云版 {len(cloud_links)}×{SYNC_RATIO}。")
        print(f"   注意：线上侧=本机 gh-pages 产物（非云自部署镜像），故这是跨源内容池差异，"
              f"不代表部署失败；A 类数字仅供参考。")
        print("对比基线: 异常")
    elif len(cloud_miss) > ONLINE_ONLY_WARN:
        print(f"⚠️ 预警：云端漏抓标题 {len(cloud_miss)} 条（本机有、云端无），建议排查云端 fetch/过滤。")
        print("对比基线: 正常")
    elif cand > ONLINE_ONLY_WARN:
        print(f"⚠️ 预警：今日/无日期线上独有链接 {cand} 条。")
        print("对比基线: 正常")
    else:
        print(f"✓ 云端漏抓 {len(cloud_miss)} 条、今日/无日期链接独有 {cand} 条，"
              f"均在合理范围（<= {ONLINE_ONLY_WARN}）。")
        print("对比基线: 正常")
    print(f"ℹ️ 内容池差异 {len(pool_diff)} 条为云端多出的往期归档，属跨源正常现象，不作告警。")


_MAIN = "_" * 2 + "main" + "_" * 2
if __name__ == _MAIN:
    main()
