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
  2026-10-25 A03：严格模式下**校验器故障同样必须中断**（调用方分类处理），
  "吞掉异常继续生成"会让 strict 守门形同虚设。

对照基准三级强度（2026-10-25 A04 重构，按 url 关联）：
  content  正文级（强基准：候选池/月库正文）——数字校验可信，可用于阻塞守门
  summary  摘要级（弱基准：候选池 RSS 摘要 / 当日并集池摘要 / 月库 ai_summary）——仅提示不阻塞
  （无）    无基准——跳过比对，计入覆盖率，绝不显示为"通过"
读取范围：月库 news_????-??.json（年份不写死，2027 起可读）+ 当日候选池
  news_candidates_<date>.json + 当日并集池 news_candidates_union_<date>.json
  （云端/境外独有条目，2026-10-25 前对数字校验不可见）。
覆盖规则：强基准永远覆盖弱基准（旧实现"先到先得"让候选池 RSS 摘要
  永久挡住月库正文 → 该条永远按弱基准仅提示，A04d）；同级之间当日池优先于月库。

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
# 2026-10-05 修正：单位前允许一个连字符（hyphen/minus – en – em —），识别英文 "数字-单位" 写法
#   （如 "$600-million" / "1.4-billion"），否则只提出裸数 → 摘要里的正确意译被判「未落地」（假 dropped）。
#   注意：\s*[-–—]?\s* 仅影响「数字紧邻连字符+单位」的附着，不改动无连字符的正常匹配与日期判定。
_UNIT_LIST = [
    '万亿美元', '亿美元', '万美元', '美元/吨', '美元', '元/吨', '元/克', '元/千克', '克/吨',
    '万吨/年', '万吨', '吨', '千克', '公斤', '克', '公里', '千米', '万盎司', '盎司', '米', '吨/年',
    '条', '项', '种', '个', '倍', '周', '年', '月', '日',
    '％', '%', '万', '亿', '十万', '百万',
    'Trillion', 'trillion', 'Billion', 'billion', 'Million', 'million', 'B', 'M', 'm',
]
_UNIT_ALT = '|'.join(sorted(set(_UNIT_LIST), key=len, reverse=True))
_NUM_RE = re.compile(r'([$£€]?\d[\d,]*(?:\.\d+)?)\s*[-–—]?\s*(%s)?' % _UNIT_ALT)


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


def load_source_map(report, data_dir='data', level_out=None, origins_out=None):
    """返回 {url: 源文文本}；level_out/origins_out（可选 dict）外泄基准强度与来源文件。

    基准强度三级（2026-10-25 A04）：
      'content' = 正文级（强基准，数字校验可信，可用于阻塞守门）；
      'summary' = 摘要级（弱基准，仅提示不阻塞）。
    读取范围：月库（news_????-??.json，年份动态）+ 当日候选池 + 当日并集池。
    覆盖规则：(强度, 来源优先级) 二元组大者胜——强基准永远覆盖弱基准；
    同级之间候选池(3) > 并集池(2) > 月库(1)，当日池优先于历史库。
    """
    src_map = {}
    levels = {}
    origins = {}
    src_ranks = {}
    _LVL_RANK = {'summary': 1, 'content': 2}

    def _put(url, text, level, origin, src_rank):
        url = _norm_url(url)
        if not url or not text:
            return
        cur = src_map.get(url)
        if cur is not None:
            cur_rank = (_LVL_RANK.get(levels.get(url), 0), src_ranks.get(url, 0))
            new_rank = (_LVL_RANK.get(level, 0), src_rank)
            if new_rank <= cur_rank:
                return  # 同级或更弱：先到先得，不覆盖
        src_map[url] = text
        levels[url] = level
        origins[url] = origin
        src_ranks[url] = src_rank

    def _read_pool(path, items, origin, src_rank):
        """从候选/并集/月库条目提取基准。content 先读、summary 后读，
        配合 _put 的覆盖规则保证同池内 content 不被自家 summary 挡住。"""
        for e in items:
            if not isinstance(e, dict):
                continue
            u = e.get('url')
            _put(u, e.get('content'), 'content', origin, src_rank)
            _put(u, e.get('summary'), 'summary', origin, src_rank)
            _put(u, e.get('ai_summary'), 'summary', origin, src_rank)

    # 1) 月库（补历史；2026-10-25 A04a：年份不再写死 news_2026-*，
    #    否则 2027 年起 glob 整体失配、月库基准静默消失）
    for fn in sorted(glob.glob(os.path.join(data_dir, 'news_????-??.json'))):
        try:
            lib = json.load(open(fn, encoding='utf-8'))
            _read_pool(fn, (lib.get('news') if isinstance(lib, dict) else lib) or [],
                       os.path.basename(fn), 1)
        except Exception:
            continue

    # 2) 当日候选池（本机采编实际输入）
    cand = os.path.join(data_dir, 'news_candidates_%s.json' % report)
    if os.path.exists(cand):
        try:
            data = json.load(open(cand, encoding='utf-8'))
            pool = data.get('items') or data.get('news') or (data if isinstance(data, list) else [])
            _read_pool(cand, pool, os.path.basename(cand), 3)
        except Exception as ex:
            print('[verify_numbers] 读候选池失败: %s' % ex, file=sys.stderr)

    # 3) 当日并集池（2026-10-25 A04b：union_candidates.py 产物里的云端/境外
    #    独有条目此前完全不进 src_map，其数字永远无法核验）
    uni = os.path.join(data_dir, 'news_candidates_union_%s.json' % report)
    if os.path.exists(uni):
        try:
            data = json.load(open(uni, encoding='utf-8'))
            pool = data.get('news') or data.get('items') or []
            _read_pool(uni, pool, os.path.basename(uni), 2)
        except Exception as ex:
            print('[verify_numbers] 读并集池失败: %s' % ex, file=sys.stderr)

    if level_out is not None:
        level_out.update(levels)
    if origins_out is not None:
        origins_out.update(origins)
    return src_map


# ---------- 5. 入口：被 generate_*.py 调用 ----------
def verify_new_items(new_items, report, data_dir='data', strict=False,
                     src_map_override=None, stats_out=None):
    """
    new_items: [(cat, it_html), ...]（与 generate_*.py 中结构一致）
    返回 [(url, [未落地原始串...]), ...]（仅正文级基准的未落地；弱基准只提示不返回）。
    分级（2026-09-14 实测确立，2026-10-25 A04 补覆盖率披露）：
      - 正文级基准（content）：未落地 -> 阻塞（strict 时抛 AssertionError）；
      - 摘要级（summary）弱基准：未落地 -> 仅提示，绝不阻塞（弱基准过短必误报）；
      - 无基准：跳过比对并计入 no_source，绝不显示为"通过"。
    stats_out（可选 dict）：写入覆盖率统计
      {'total','checked','strong','weak','no_source','hard','weak_hits'}，
      供调用方/CI 判断"本次校验是否真的覆盖了大多数条目"。
    strict=True 且存在正文级未落地 -> 抛 AssertionError（业务不通过）；
    校验器自身故障（异常）同样向上抛，由调用方按 A03 规则处理。
    """
    from generate_common import item_url  # 复用，避免重复实现
    levels = {}
    origins = {}
    src_map = src_map_override if src_map_override is not None \
        else load_source_map(report, data_dir, levels, origins)
    hard, weak = [], []
    strong_n = weak_n = skipped = 0
    for _cat, it in new_items:
        url = _norm_url(item_url(it))
        summary = extract_summary_from_item(it)
        source = src_map.get(url, '')
        if not source:
            skipped += 1
            continue
        lvl = 'content' if src_map_override is not None else levels.get(url, 'summary')
        if lvl == 'content':
            strong_n += 1
        else:
            weak_n += 1
        miss = verify_summary(summary, source)
        if miss:
            (hard if lvl == 'content' else weak).append((url, [m[0] for m in miss]))
    if skipped:
        print('[verify_numbers] %d 条无源文基准（候选池/并集池/月库未覆盖），跳过数字比对' % skipped)
    if weak:
        print('[verify_numbers] %d 条弱基准（摘要级）数字未落地，仅提示不阻塞：' % len(weak))
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
              % (strong_n, len(weak)))
    # 2026-10-25 A04c：明确三档覆盖率，低覆盖时提示人工复核，
    # 避免"弱基准/无基准占多数"被一句"通过"带过。
    print('[verify_numbers] 校验覆盖率：共 %d 条 = 正文级 %d + 摘要级 %d + 无基准 %d'
          % (len(new_items), strong_n, weak_n, skipped))
    if skipped and skipped >= max(1, len(new_items) // 2):
        print('[verify_numbers] ⚠️ 无基准条目占比过半，本次校验覆盖有限，请人工复核数字')
    if stats_out is not None:
        stats_out.clear()
        stats_out.update({'total': len(new_items), 'checked': strong_n + weak_n,
                          'strong': strong_n, 'weak': weak_n, 'no_source': skipped,
                          'hard': len(hard), 'weak_hits': len(weak)})
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
    origins = {}
    src_map = load_source_map(report, args.data_dir, levels, origins)
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
    if total_checked == 0:
        # 2026-10-25 A04c：全无基准时旧实现打印"正文级全部通过"——
        # 覆盖率 0% 的"通过"是最危险的一种误导。
        print('[verify_numbers] ⚠️ 无任何源文基准（候选池/并集池/月库均未覆盖），'
              '本次未执行数字比对，不能视为通过')
        return 3 if args.strict else 0
    print('[verify_numbers] 正文级全部通过（已比对 %d 条，其余无基准跳过）' % total_checked)
    return 0


def _today():
    import datetime
    return datetime.date.today().isoformat()


if __name__ == '__main__':
    sys.exit(main())
