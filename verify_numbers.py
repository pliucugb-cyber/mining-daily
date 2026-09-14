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
    '万亿美元', '亿美元', '万美元', '美元/吨', '美元', '元/吨', '元/克', '元/千克', '克/吨',
    '万吨/年', '万吨', '吨', '千克', '公斤', '克', '公里', '千米', '万盎司', '盎司', '米', '吨/年',
    '条', '项', '种', '个', '倍', '周', '年', '月', '日',
    '％', '%', '万', '亿', '十万', '百万',
    'Trillion', 'trillion', 'Billion', 'billion', 'Million', 'million', 'B', 'M', 'm',
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


# ---------- 2. 数值落地判定（数值按量级归一 + 单位按类别兼容） ----------
# 量级后缀 -> 倍数（中英文互认：59万 <-> 590,000；3,000美元 <-> $3,000）
_MAG_LIST = [('万亿', 1e12), ('Trillion', 1e12), ('trillion', 1e12),
             ('十亿', 1e9), ('Billion', 1e9), ('billion', 1e9), ('B', 1e9),
             ('亿', 1e8), ('百万', 1e6), ('Million', 1e6), ('million', 1e6), ('M', 1e6),
             ('万', 1e4), ('千', 1e3), ('K', 1e3)]


def _core_cat(norm, unit):
    """把 (数值, 单位串) 归一为 (核心数值, 单位类别)。

    核心数值 = 数值 × 量级系数（万/亿/百万/十亿/B/M/千），用于跨语言量级互认：
        中文「59万」 <-> 英文「590,000」；「3,000美元」 <-> 「$3,000」。
    单位类别（money/mass/len/pct）用于避免「3000 米」误配「3000 吨」；
    空类别（纯数字、或未识别单位）兼容任意类别。
    类别 'date'（月/日/年/周）不参与校验——跨语言日期翻译（September 4 <-> 9月4日）
    属正常意译而非抄错，强行校验会大量误报（2026-09-14 实测）。"""
    mult = 1.0
    for k, m in _MAG_LIST:
        if k in unit:
            mult = m
            break
    core = norm * mult
    cat = ''
    if any(c in unit for c in ('美元', 'RMB', 'rmb', 'USD', 'usd', '元')):
        cat = 'money'
    elif any(c in unit for c in ('吨', '千克', '公斤', '克', '盎司')):
        cat = 'mass'
    elif any(c in unit for c in ('米', '公里', '千米')):
        cat = 'len'
    elif any(c in unit for c in ('%', '％')):
        cat = 'pct'
    elif any(c in unit for c in ('月', '日', '年', '周')):
        cat = 'date'
    return core, cat


def number_in_source(n, u, sn, su):
    """摘要数字 (n,u) 是否落到源文数字 (sn,su)。数值按量级归一，单位按类别兼容。"""
    c1, k1 = _core_cat(n, u)
    if k1 == 'date':
        return True  # 摘要里的日期不校验（跨语言不可比，属正常意译）
    c2, k2 = _core_cat(sn, su)
    if k2 == 'date':
        return False  # 源文该数字是日期，与摘要的非日期数字不同类（防「源文有年份就全部放行」）
    if k1 and k2 and k1 != k2:
        return False  # 类别冲突（如 米 vs 吨），即便数值巧合相等也不算落地
    return abs(c1 - c2) <= max(0.01 * abs(c1), 0.01)


def verify_summary(summary, source):
    """校验一条摘要。返回未落地数字列表 [(原始串, 单位串), ...]"""
    if not source:
        return []  # 无基准，交给调用方决定 skip
    src_nums = extract_numbers(source)
    issues = []
    for n, u, raw in extract_numbers(summary):
        if _core_cat(n, u)[1] == 'date':
            continue  # 日期不校验：跨语言不可比；且源文无数字时也不能因此误报（2026-09-14 实测）
        if not u and 1900 <= n <= 2100 and float(n).is_integer():
            continue  # 裸年份（如 "2026" 未带「年」字）不校验，避免年份误报
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


def load_source_map(report, data_dir='data', level_out=None):
    """返回 {url: 源文文本}。优先级：候选池 content > 候选池 summary > 月库 content/ai_summary/summary。

    level_out（可选 dict）：写入每个 url 的基准强度——
      'content' = 正文级（强基准，数字校验可信，可用于阻塞守门）；
      'summary' = RSS 摘要级（弱基准，摘要常≈标题，校验易误报，仅提示不阻塞）。
    2026-09-14 实测：弱基准下"未落地"多为误报（摘要数字不在短短几字的 RSS 摘要里）。
    """
    src_map = {}

    def _put(url, text, level):
        url = _norm_url(url)
        if not url or not text:
            return
        if url not in src_map:  # 先到先得（候选池优先于月库）
            src_map[url] = text
            if level_out is not None:
                level_out[url] = level

    # 候选池
    cand = os.path.join(data_dir, 'news_candidates_%s.json' % report)
    if os.path.exists(cand):
        try:
            data = json.load(open(cand, encoding='utf-8'))
            pool = data.get('items') or data.get('news') or (data if isinstance(data, list) else [])
            for e in pool:
                if not isinstance(e, dict):
                    continue
                _put(e.get('url'), e.get('content'), 'content')
                _put(e.get('url'), e.get('summary'), 'summary')
        except Exception as ex:
            print('[verify_numbers] 读候选池失败: %s' % ex, file=sys.stderr)

    # 月库（补候选池未覆盖的 url）
    for fn in sorted(glob.glob(os.path.join(data_dir, 'news_2026-*.json'))):
        try:
            lib = json.load(open(fn, encoding='utf-8'))
            for e in (lib.get('news') if isinstance(lib, dict) else lib):
                if not isinstance(e, dict):
                    continue
                _put(e.get('url'), e.get('content'), 'content')
                _put(e.get('url'), e.get('ai_summary'), 'summary')
                _put(e.get('url'), e.get('summary'), 'summary')
        except Exception:
            continue
    return src_map


# ---------- 5. 入口：被 generate_*.py 调用 ----------
def verify_new_items(new_items, report, data_dir='data', strict=False, src_map_override=None):
    """
    new_items: [(cat, it_html), ...]（与 generate_*.py 中结构一致）
    返回 [(url, [未落地原始串...]), ...]（仅正文级基准的未落地；弱基准只提示不返回）。
    无基准的条目不产生条目（只打印 skip）。
    分级（2026-09-14 实测确立）：
      - 正文级基准（content）：未落地 -> 阻塞（strict 时抛异常）；
      - RSS 摘要级（summary）弱基准：未落地 -> 仅提示，绝不阻塞（弱基准过短必误报）。
    src_map_override 提供时视为正文级（调优注入真实正文）。
    """
    from generate_common import item_url  # 复用，避免重复实现
    levels = {}
    src_map = src_map_override if src_map_override is not None else load_source_map(report, data_dir, levels)
    hard, weak = [], []
    skipped = 0
    for _cat, it in new_items:
        url = _norm_url(item_url(it))
        summary = extract_summary_from_item(it)
        source = src_map.get(url, '')
        if not source:
            skipped += 1
            continue
        lvl = 'content' if src_map_override is not None else levels.get(url, 'summary')
        miss = verify_summary(summary, source)
        if miss:
            (hard if lvl == 'content' else weak).append((url, [m[0] for m in miss]))
    if skipped:
        print('[verify_numbers] %d 条无源文基准（候选池/月库未覆盖），跳过数字比对' % skipped)
    if weak:
        print('[verify_numbers] %d 条弱基准（RSS 摘要级）数字未落地，仅提示不阻塞：' % len(weak))
        for url, miss in weak[:20]:
            print('   ~ %s : %s' % (url, '、'.join(miss)))
    if hard:
        print('[verify_numbers] %d 条正文级摘要存在数字未在源文落地：' % len(hard))
        for url, miss in hard:
            print('   - %s : %s' % (url, '、'.join(miss)))
        if strict:
            raise AssertionError('数字落地校验未通过：%d 条' % len(hard))
    else:
        print('[verify_numbers] 数字落地校验通过（正文级已比对 %d 条；弱基准提示 %d 条）'
              % (len(new_items) - skipped - len(weak), len(weak)))
    return hard


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
    levels = {}
    src_map = load_source_map(report, args.data_dir, levels)
    total_checked = 0
    hard, weak = [], []
    for url, summary in items:
        nu = _norm_url(url)
        source = src_map.get(nu, '')
        if not source:
            continue
        total_checked += 1
        miss = verify_summary(summary, source)
        if miss:
            lvl = levels.get(nu, 'summary')
            (hard if lvl == 'content' else weak).append((url, [m[0] for m in miss]))
    print('[verify_numbers] 已比对 %d 条（其余无源文基准跳过）' % total_checked)
    if weak:
        print('[verify_numbers] 弱基准（RSS 摘要级）%d 条未落地，仅提示不阻塞：' % len(weak))
        for url, miss in weak[:20]:
            print('  ~ %s : %s' % (url, '、'.join(miss)))
    for url, miss in hard:
        print('  - %s : %s' % (url, '、'.join(miss)))
    if hard:
        print('[verify_numbers] 正文级共 %d 条未通过' % len(hard))
        return 1 if args.strict else 0
    print('[verify_numbers] 正文级全部通过')
    return 0


def _today():
    import datetime
    return datetime.date.today().isoformat()


if __name__ == '__main__':
    sys.exit(main())
