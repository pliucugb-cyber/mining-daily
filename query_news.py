# -*- coding: utf-8 -*-
"""
矿业新闻检索器 —— 问答层的数据入口

从 data/news_YYYY-MM.json 月度累积库中检索新闻，按条件过滤后输出。
设计原则：默认输出极简（一行一条），因为结果要直接喂给模型，token 必须省。

常用示例：
  python query_news.py --stats                      # 库概览：总量/日期范围/矿种TOP/来源TOP
  python query_news.py --days 7                     # 最近 7 天（锚点=库中最新日期）
  python query_news.py -m 锂                        # 按矿种标签
  python query_news.py --kw 稀土 出口               # 关键词（空格=AND）
  python query_news.py --from 2026-08-25 --to 2026-08-28
  python query_news.py --source 有色网 --limit 20
  python query_news.py -m 铜 --format json          # JSON 输出供程序消费
  python query_news.py --kw 锂 --detail             # 带摘要的详细模式

数据目录定位（按顺序探测，便于专家包分发后免配置运行）：
  1) --data-dir 显式指定
  2) 环境变量 MINE_NEWS_DATA_DIR
  3) 脚本同级 / 上级 data 目录
  4) 自动扫描 ~/WorkBuddy/*/output/mining-daily/data 等常见部署位置
  加 --where 可只打印解析到的目录，用于排查。

参数说明：
  -m/--mineral   矿种标签（铜 锂 稀土 镍 钴 金 银 ...），可多次指定，OR 关系
  -t/--topic     主题标签（政策 找矿 矿权 市场 技术 安全 国际），可多次指定，OR 关系
  -k/--kw        关键词，匹配标题+摘要+标签，空格分隔=AND，可多次指定（组间 OR）
  --source       来源模糊匹配
  --cat          分类精确匹配
  --from/--to    日期区间（YYYY-MM-DD，按新闻发布日 orig_date_full）
  --days N       最近 N 天，锚点为库中最新日期
  --new-only     仅当日新增（is_new=true）
  --embed        ok / block / unknown
  --limit N      最多返回条数（默认 30）
  --format       brief(默认) / table / json
  --detail       显示摘要
  --where        只打印解析到的数据目录
"""
import os
import sys
import json
import argparse
import datetime
import collections

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

NOT_FOUND_MSG = """[错误] 未找到矿业新闻累积库目录（需含 news_YYYY-MM.json 月度分片）。
请通过以下任一方式指定：
  1) 命令行：python query_news.py --data-dir "<绝对路径>" ...
  2) 环境变量：
       Windows PowerShell : $env:MINE_NEWS_DATA_DIR="<绝对路径>"
       Windows CMD        : set MINE_NEWS_DATA_DIR=<绝对路径>
       Linux / macOS      : export MINE_NEWS_DATA_DIR="<绝对路径>"
累积库由 mining-daily/export_news_json.py 每日追加生成。"""


def has_news(d):
    """目录里确实存在月度分片才算命中，避免探到空壳目录"""
    if not d or not os.path.isdir(d):
        return False
    try:
        return any(fn.startswith('news_') and fn.endswith('.json')
                   for fn in os.listdir(d))
    except OSError:
        return False


def scan_candidates():
    """常见部署位置：WorkBuddy 各会话目录下的 mining-daily/data + 工作目录附近"""
    out = []
    home = os.path.expanduser('~')
    wb = os.path.join(home, 'WorkBuddy')
    if os.path.isdir(wb):
        try:
            for session in sorted(os.listdir(wb), reverse=True):
                out.append(os.path.join(wb, session, 'output',
                                        'mining-daily', 'data'))
        except OSError:
            pass
    cwd = os.getcwd()
    for rel in ('data', os.path.join('mining-daily', 'data'),
                os.path.join('output', 'mining-daily', 'data')):
        out.append(os.path.join(cwd, rel))
    return out


def resolve_data_dir(explicit=None):
    """返回 (目录, 来源说明)；找不到返回 (None, 原因)"""
    if explicit:
        return explicit, '命令行 --data-dir'
    env = os.environ.get('MINE_NEWS_DATA_DIR')
    if env:
        return env, '环境变量 MINE_NEWS_DATA_DIR'
    here = BASE_DIR
    for rel in ('data', os.path.join('..', 'data'),
                os.path.join('..', '..', 'data')):
        cand = os.path.normpath(os.path.join(here, rel))
        if has_news(cand):
            return cand, '脚本相对目录'
    for cand in scan_candidates():
        if has_news(cand):
            return cand, '自动探测'
    return None, '未找到'


def available_months(data_dir):
    if not os.path.isdir(data_dir):
        return []
    return sorted(fn[5:-5] for fn in os.listdir(data_dir)
                  if fn.startswith('news_') and fn.endswith('.json'))


def month_needed(month, args):
    """粗筛：判断该月份分片是否需要加载（避免全量读入）"""
    if args.months:
        return month in args.months
    if args.date_from and month < args.date_from[:7]:
        return False
    if args.date_to and month > args.date_to[:7]:
        return False
    return True


def load_rows(data_dir, args):
    rows = []
    for month in available_months(data_dir):
        if not month_needed(month, args):
            continue
        path = os.path.join(data_dir, 'news_%s.json' % month)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                rows.extend(json.load(f).get('news', []))
        except Exception as e:
            print('[warn] 读取失败 %s: %s' % (path, e), file=sys.stderr)
    return rows


def match_kw(row, kw_groups, mode='and'):
    """关键词组之间 OR；组内空格分隔的词，AND 模式需全部命中，OR 模式命中任一即可"""
    if not kw_groups:
        return True
    hay = ' '.join([row.get('title', ''), row.get('summary', ''),
                    ' '.join(row.get('tags', [])), row.get('source', ''),
                    row.get('category', '')])
    for grp in kw_groups:
        words = [w for w in grp.split() if w]
        if not words:
            continue
        if mode == 'or':
            if any(w in hay for w in words):
                return True
        elif all(w in hay for w in words):
            return True
    return False


def apply_filters(rows, args, kw_mode='and'):
    out = []
    for r in rows:
        if args.mineral and not (set(args.mineral) & set(r.get('tags', []))):
            continue
        if args.topic and not (set(args.topic) & set(r.get('tags', []))):
            continue
        if args.source and args.source not in r.get('source', ''):
            continue
        if args.cat and r.get('category') != args.cat:
            continue
        d = r.get('orig_date_full', '')
        if args.date_from and d < args.date_from:
            continue
        if args.date_to and d > args.date_to:
            continue
        if args.new_only and not r.get('is_new'):
            continue
        if args.embed and r.get('embed') != args.embed:
            continue
        if not match_kw(r, args.kw, kw_mode):
            continue
        out.append(r)
    out.sort(key=lambda x: (x.get('orig_date_full', ''), x.get('id', '')), reverse=True)
    return out


def print_trend(rows):
    """按发布日期聚合计数，用横向条表示强度，便于模型快速理解趋势"""
    if not rows:
        print('（无数据）')
        return
    cnt = collections.Counter(r.get('orig_date_full', '未知') for r in rows)
    keys = sorted(k for k in cnt if k != '未知')
    if '未知' in cnt:
        keys.append('未知')
    top = max(cnt.values())
    print('== 时间分布 ==')
    for k in keys:
        bar = '#' * max(1, round(cnt[k] / top * 32))
        print('%s  %-34s %d' % (k, bar, cnt[k]))
    print('合计 %d 条' % len(rows))


def print_stats(rows, data_dir):
    dates = sorted({r['orig_date_full'] for r in rows if r.get('orig_date_full')})
    print('== 累积库概览 ==')
    print('目录: %s' % data_dir)
    print('总条目: %d' % len(rows))
    if dates:
        print('日期范围: %s ~ %s（覆盖 %d 天）' % (dates[0], dates[-1], len(dates)))
        miss = missing_days(dates)
        if miss:
            print('缺失日期: %s' % ', '.join(miss))
    mc = collections.Counter(m for r in rows for m in r.get('tags', [])
                             if m in MINERAL_SET)
    if mc:
        print('矿种TOP: %s' % ', '.join('%s(%d)' % (k, v) for k, v in mc.most_common(10)))
    tc = collections.Counter(t for r in rows for t in r.get('tags', [])
                             if t in TOPIC_SET)
    if tc:
        print('主题TOP: %s' % ', '.join('%s(%d)' % (k, v) for k, v in tc.most_common(8)))
    sc = collections.Counter(r.get('source', '') for r in rows if r.get('source'))
    print('来源TOP: %s' % ', '.join('%s(%d)' % (k, v) for k, v in sc.most_common(8)))
    cc = collections.Counter(r.get('category', '') for r in rows)
    print('分类: %s' % ', '.join('%s(%d)' % (k, v) for k, v in cc.most_common()))


def missing_days(dates):
    """找出日期区间内的空缺天"""
    if len(dates) < 2:
        return []
    d0 = datetime.date.fromisoformat(dates[0])
    d1 = datetime.date.fromisoformat(dates[-1])
    have = set(dates)
    miss = []
    cur = d0
    while cur <= d1:
        s = cur.isoformat()
        if s not in have:
            miss.append(s)
        cur += datetime.timedelta(days=1)
    return miss


MINERAL_SET = set('铜 镍 铅 锌 铝 金 银 稀土 钨 钼 锡 锑 锂 钴 钛 铀 锰 钒 铬 镁 '
                  '铌 钽 镓 锗 铟 铼 镉 铋 硒 碲 铂 钯 铁'.split())
TOPIC_SET = set('政策 找矿 矿权 市场 技术 安全 国际'.split())


def print_brief(rows, detail):
    for r in rows:
        tags = '/'.join(r.get('tags', [])[:3])
        print('%s | %s | %s' % (r.get('orig_date_full', '????-??-??'),
                                r.get('source', '?'), r.get('title', '')))
        if detail and r.get('summary'):
            print('    %s' % r['summary'])
            print('    tags=%s  cat=%s  %s' % (tags, r.get('category', ''), r.get('url', '')))
    print('\n共 %d 条' % len(rows))


def print_table(rows):
    print('%-12s %-22s %s' % ('日期', '来源', '标题'))
    print('-' * 78)
    for r in rows:
        src = r.get('source', '')[:20]
        print('%-12s %-22s %s' % (r.get('orig_date_full', ''), src, r.get('title', '')))
    print('-' * 78)
    print('共 %d 条' % len(rows))


def main():
    p = argparse.ArgumentParser(description='矿业新闻检索器（问答层数据入口）',
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('-m', '--mineral', action='append', help='矿种标签，可多次')
    p.add_argument('-t', '--topic', action='append', help='主题标签，可多次')
    p.add_argument('-k', '--kw', action='append', nargs='+',
                   help='关键词，空格=AND，可多次(组间OR)；加不加引号均可')
    p.add_argument('--source', help='来源模糊匹配')
    p.add_argument('--cat', help='分类精确匹配')
    p.add_argument('--from', dest='date_from', help='起始日期 YYYY-MM-DD')
    p.add_argument('--to', dest='date_to', help='结束日期 YYYY-MM-DD')
    p.add_argument('--days', type=int, help='最近 N 天（锚点=库中最新日期）')
    p.add_argument('--new-only', action='store_true', help='仅当日新增')
    p.add_argument('--embed', choices=['ok', 'block', 'unknown'], help='嵌入状态')
    p.add_argument('--limit', type=int, default=30, help='最多返回条数，默认 30')
    p.add_argument('--format', choices=['brief', 'table', 'json'], default='brief')
    p.add_argument('--detail', action='store_true', help='显示摘要与链接')
    p.add_argument('--any', action='store_true', help='关键词放宽为任一词命中(OR)')
    p.add_argument('--trend', action='store_true', help='按日期聚合输出时间分布')
    p.add_argument('--stats', action='store_true', help='输出库概览统计')
    p.add_argument('--months', nargs='*', help='限定月份分片，如 2026-08 2026-09')
    p.add_argument('--data-dir', default=None, help='累积库目录，缺省时自动探测')
    p.add_argument('--where', action='store_true', help='只打印解析到的数据目录')
    args = p.parse_args()

    # nargs='+' 会把每组收成列表，统一还原成"空格分隔的字符串"，使
    # --kw "稀土 政策" 与 --kw 稀土 政策 两种写法等价
    if args.kw:
        args.kw = [' '.join(g) if isinstance(g, list) else g for g in args.kw]

    data_dir, origin = resolve_data_dir(args.data_dir)

    if args.where:
        print('数据目录: %s' % (data_dir or '（未找到）'))
        print('定位来源: %s' % origin)
        return 0 if data_dir else 1

    if not data_dir or not os.path.isdir(data_dir):
        print(NOT_FOUND_MSG, file=sys.stderr)
        return 1

    rows = load_rows(data_dir, args)

    if args.stats:
        print_stats(rows, data_dir)
        return 0

    if args.days:
        dates = [r['orig_date_full'] for r in rows if r.get('orig_date_full')]
        if dates:
            anchor = max(dates)
            a = datetime.date.fromisoformat(anchor) - datetime.timedelta(days=args.days - 1)
            args.date_from = a.isoformat()
            if not args.date_to:
                args.date_to = anchor
            print('[锚点 %s] 检索 %s ~ %s\n' % (anchor, args.date_from, args.date_to))

    hits = apply_filters(rows, args, 'or' if args.any else 'and')
    # 精确匹配无结果时自动放宽为"任一词命中"，避免问答场景空手而归
    if not hits and args.kw and any(' ' in g for g in args.kw):
        hits = apply_filters(rows, args, 'or')
        if hits:
            print('[提示] 全部关键词同时命中无结果，已放宽为任一词命中\n')

    if args.trend:
        print_trend(hits)
        return 0

    total = len(hits)
    hits = hits[:args.limit]

    if args.format == 'json':
        print(json.dumps({'total': total, 'returned': len(hits), 'items': hits},
                         ensure_ascii=False, indent=2))
    elif args.format == 'table':
        print_table(hits)
    else:
        print_brief(hits, args.detail)
    if args.limit and total > len(hits):
        print('（已截断，共 %d 条，用 --limit 调整）' % total)
    return 0


if __name__ == '__main__':
    sys.exit(main())
