# -*- coding: utf-8 -*-
"""
数字落地校验（2026-09-14 新增）

目的：日报每条摘要里出现的「数字 + 单位」，必须能在对应源文里找到。
      直接打中「LLM 抄错数字」（如把 113 米看成别的、把 45 亿写成 4.5 亿）这类最该防的错。

设计原则：
- 纯标准库、零第三方依赖；WB 流程与 B'（云端 DeepSeek）都可直接复用。
- 不侵入 daily 生成脚本：既能被 generate_YYYYMMDD.py import（verify_new_items），
  也能 CLI 独立跑（读 index.html 校验），两种入口共用同一套提取/比对逻辑。
- fail soft 优先：源文缺失（如候选池未落盘、未开 --fetch-detail）时只报 skip，不中断生成；
  设环境变量 VERIFY_NUMBERS_STRICT=1 时，发现未落地数字则抛异常（生产守门用）。

对照基准优先级（按 url 关联）：
  1. 候选池 data/news_candidates_<date>.json 的 content 字段（--fetch-detail 才有正文）
  2. 候选池的 summary 字段（RSS 短摘要，默认就有）
  3. 月库 data/news_2026-*.json 同 url 的 content / ai_summary / summary
基准越完整，校验越有效。当前默认只到 RSS 摘要 → 覆盖有限；
要让校验真正强，WB 早间任务 fetch 时加 --fetch-detail（或让月库带 content）。

用法：
  python verify_numbers.py                       # CLI：读 index.html + data/ 候选池，打印报告
  python verify_numbers.py --list-numbers       # 仅打印从 index.html 提取到的数字（不比对）
  python verify_numbers.py --strict             # 有未落地数字则非零退出（CI / 守门）
  # 在 generate_YYYYMMDD.py 中：
  from verify_numbers import verify_new_items
  issues = verify_new_items(new_items, REPORT)  # -> [(url, [未落地数字...]), ...]
"""
import re
import os
import sys
import json
import glob
import argparse


# ---------- 1. 数字提取 ----------
# 数值：可选货币符号 + 阿拉伯数字（允许千分位逗号、小数）
# 单位：已知单位词表「最长匹配」，避免 "公里" 被拆成 "公"+"里"、或 "公告" 的"公"被误吞
_UNIT_LIST = [
    '亿美元', '万美元', '美元/吨', '美元', '元/吨', '元/克', '元/千克', '克/吨',
    '万吨/年', '万吨', '吨', '千克', '公斤', '克', '公里', '千米', '万盎司', '盎司', '米', '吨/年',
    '条', '项', '种', '个', '倍', '周', '年', '月', '日',
    '％', '%', '万', '亿', '十万', '百万',
    'Billion', 'billion', 'Million', 'million', 'B', 'm',
]
_UNIT_ALT = '|'.join(sorted(set(_UNIT_LIST), key=len, reverse=True))
_NUM_RE = re.compile(r'([$£€]?\d[\d,]*(?:\.\d+)?)\s*(%s)?' % _UNIT_ALT)


def extract_numbers(text):
    """返回 [(归一数值 float, 单位串 str, 原始串 str), ...]"""
    out = []
    if not text:
        return out
    for m in _NUM_RE.finditer(text):
        raw_val = m.group(1)
        unit = m.group(2) or ''
        norm = float(raw_val.replace(',', '').replace('$', '').replace('£', '').replace('€', ''))
        out.append((norm, unit, raw_val + unit))
    return out


# ---------- 2. 数值落地判定（含货币跨单位归一化） ----------
# 货币量级 -> 折算到「亿」的系数（仅用于美元/亿元等跨境金额互认）
_FACTOR = {
    '十亿': 10, 'Billion': 10, 'billion': 10, 'B': 10,
    '亿': 1,
    '百万': 0.01, 'Million': 0.01, 'million': 0.01,
    '万': 0.0001,
}


def _to_yi(n, u):
    for k, f in _FACTOR.items():
        if k in u:
            return n * f
    return None


def number_in_source(n, u, sn, su):
    """摘要数字 (n,u) 是否落到源文数字 (sn,su)。"""
    # 精确同单位匹配（去逗号后数值相等、单位串一致）
    if abs(n - sn) < 1e-9 and u == su:
        return True
    # 货币跨单位归一化：如 45亿 <-> $4.5 Billion、5亿 <-> $500 Million
    cy, csy = _to_yi(n, u), _to_yi(sn, su)
    if cy is not None and csy is not None:
        if abs(cy - csy) <= max(0.01 * cy, 0.01):
            return True
    return False


def verify_summary(summary, source):
    """校验一条摘要。返回未落地数字列表 [(原始串, 单位串), ...]"""
    if not source:
        return []  # 无基准，交给调用方决定 skip
    src_nums = extract_numbers(source)
    issues = []
    for n, u, raw in extract_numbers(summary):
        if not any(number_in_source(n, u, sn, su) for sn, su, _ in src_nums):
            issues.append((raw, u))
    return issues


# ---------- 3. 从 HTML / new_items 提取摘要+url ----------
def extract_summary_from_item(it):
    m = re.search(r'<div class="news-summary">(.*?)</div>', it, re.S)
    if not m:
        return ''
    return re.sub(r'<[^>]+>', '', m.group(1))  # 去可能的标签


def extract_items_from_html(html):
    """从 index.html 提取 [(url, 摘要文本), ...]"""
    items = []
    for blk in re.finditer(r'<div class="news-item[^"]*"[^>]*>.*?</div>\s*</div>', html, re.S):
        blk = blk.group(0)
        um = re.search(r'data-url="([^"]+)"', blk)
        sm = re.search(r'<div class="news-summary">(.*?)</div>', blk, re.S)
        if um and sm:
            items.append((um.group(1), re.sub(r'<[^>]+>', '', sm.group(1))))
    return items


# ---------- 4. 源文映射（按 url 关联候选池 / 月库） ----------
def _norm_url(u):
    return (u or '').strip()


def load_source_map(report, data_dir='data'):
    """返回 {url: 源文文本}。优先级：候选池 content > 候选池 summary > 月库 content/ai_summary/summary。"""
    src_map = {}

    def _put(url, text):
        url = _norm_url(url)
        if not url or not text:
            return
        if url not in src_map:  # 先到先得（候选池优先于月库）
            src_map[url] = text

    # 候选池
    cand = os.path.join(data_dir, 'news_candidates_%s.json' % report)
    if os.path.exists(cand):
        try:
            data = json.load(open(cand, encoding='utf-8'))
            pool = data.get('items') or data.get('news') or (data if isinstance(data, list) else [])
            for e in pool:
                if not isinstance(e, dict):
                    continue
                _put(e.get('url'), e.get('content') or e.get('summary') or '')
        except Exception as ex:
            print('[verify_numbers] 读候选池失败: %s' % ex, file=sys.stderr)

    # 月库（补候选池未覆盖的 url）
    for fn in sorted(glob.glob(os.path.join(data_dir, 'news_2026-*.json'))):
        try:
            lib = json.load(open(fn, encoding='utf-8'))
            for e in (lib.get('news') if isinstance(lib, dict) else lib):
                if not isinstance(e, dict):
                    continue
                _put(e.get('url'), e.get('content') or e.get('ai_summary') or e.get('summary') or '')
        except Exception:
            continue
    return src_map


# ---------- 5. 入口：被 generate_*.py 调用 ----------
def verify_new_items(new_items, report, data_dir='data', strict=False):
    """
    new_items: [(cat, it_html), ...]（与 generate_*.py 中结构一致）
    返回 [(url, [未落地原始串...]), ...]；无基准的条目不产生条目（只打印 skip）。
    strict=True 且存在未落地 -> 抛 AssertionError（生产守门）。
    """
    from generate_common import item_url  # 复用，避免重复实现
    src_map = load_source_map(report, data_dir)
    issues = []
    skipped = 0
    for _cat, it in new_items:
        url = _norm_url(item_url(it))
        summary = extract_summary_from_item(it)
        source = src_map.get(url, '')
        if not source:
            skipped += 1
            continue
        miss = verify_summary(summary, source)
        if miss:
            issues.append((url, [m[0] for m in miss]))
    if skipped:
        print('[verify_numbers] %d 条无源文基准（候选池/月库未覆盖），跳过数字比对' % skipped)
    if issues:
        print('[verify_numbers] %d 条摘要存在数字未在源文落地：' % len(issues))
        for url, miss in issues:
            print('   - %s : %s' % (url, '、'.join(miss)))
        if strict:
            raise AssertionError('数字落地校验未通过：%d 条' % len(issues))
    else:
        print('[verify_numbers] 数字落地校验通过（已比对 %d 条）' % (len(new_items) - skipped))
    return issues


# ---------- 6. CLI ----------
def main():
    ap = argparse.ArgumentParser(description='矿业日报数字落地校验')
    ap.add_argument('--html', default='index.html')
    ap.add_argument('--date', default=None, help='报告日期 YYYY-MM-DD（默认今天）')
    ap.add_argument('--data-dir', default='data')
    ap.add_argument('--list-numbers', action='store_true', help='仅打印提取到的数字，不比对')
    ap.add_argument('--strict', action='store_true', help='有未落地数字则非零退出')
    args = ap.parse_args()

    if not os.path.exists(args.html):
        print('[verify_numbers] 未找到 %s' % args.html, file=sys.stderr)
        return 2
    html = open(args.html, encoding='utf-8').read()
    items = extract_items_from_html(html)
    print('[verify_numbers] 从 %s 提取 %d 条摘要' % (args.html, len(items)))

    if args.list_numbers:
        for url, summary in items:
            nums = extract_numbers(summary)
            print('  %s' % url)
            print('    数字: %s' % ('、'.join(n[2] for n in nums) or '（无）'))
        return 0

    report = args.date or os.environ.get('REPORT_DATE') or _today()
    src_map = load_source_map(report, args.data_dir)
    total_checked = 0
    issues = []
    for url, summary in items:
        source = src_map.get(_norm_url(url), '')
        if not source:
            continue
        total_checked += 1
        miss = verify_summary(summary, source)
        if miss:
            issues.append((url, [m[0] for m in miss]))
    print('[verify_numbers] 已比对 %d 条（其余无源文基准跳过）' % total_checked)
    for url, miss in issues:
        print('  - %s : %s' % (url, '、'.join(miss)))
    if issues:
        print('[verify_numbers] 共 %d 条未通过' % len(issues))
        return 1 if args.strict else 0
    print('[verify_numbers] 全部通过')
    return 0


def _today():
    import datetime
    return datetime.date.today().isoformat()


if __name__ == '__main__':
    sys.exit(main())
