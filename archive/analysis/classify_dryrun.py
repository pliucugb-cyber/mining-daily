#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classify_dryrun.py —— 新闻分类体系「试跑」工具（只读，绝不写数据文件）

背景
----
现在的分类是**按信源硬编码**的：fetch_news.py 里每个抓取源配置写死一个 category，
同一信源里不管是政策、行情、技术还是会议通知，全都被打成同一类。
结果：152 条里 76 条（50%）落在「行业动态」这个兜底桶，而用户最关心的「政策」没有独立入口。

本脚本做的事
------------
1. 定义一套**按内容**归类的规则（主题维 8 类 + 地域维 国内/国际）
2. 对现有数据跑一遍，输出：新分布、新旧变化矩阵、逐条明细（含命中了哪条规则）、存疑清单
3. **不修改任何数据文件**——只产出报告，供人工抽查准确率

用法
----
    python classify_dryrun.py                      # 跑 mining_news.json，输出报告到 stdout 路径
    python classify_dryrun.py --src data/news_2026-09.json
    python classify_dryrun.py --out 报告.md --limit 30   # 只看前 30 条明细

规则调优后若确认可用，再决定：① 改 fetch_news.py 让新抓取按此归类 ② 回填存量数据。
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 分类体系（主题维）====================
# 顺序即优先级：从上往下第一个命中的类别胜出。
# 每个类别给出「命中关键词」+「这条规则想抓住什么」，便于人工复核时判断规则是否合理。
RULES = [
    ('矿权出让', r'挂牌出让|拍卖出让|协议出让|转让公示|结果公示|竞得|起始价|保证金|矿业权出让|探矿权出让|采矿权出让',
     '矿业权市场的挂牌/拍卖/转让/成交，页面已有独立专区'),
    ('并购与投资', r'收购|并购|受让|股权转让|增资扩股|合资|重组|要约收购|控股权|参股|重大资产|要约',
     '资本动作：买矿、卖矿、股权变动'),
    ('政策与监管', r'国务院|部委|自然资源部|工信部|发改委|海关|税务总局|生态环境部|应急管理部|国家标准|行业标准|新标准获批|技术规范|管理办法|实施细则|条例|政策|法规|管制|管控|禁令|暂停出口|禁止出口|关税|出口税|资源税|矿业权管理|督察|整治|专项行动|规划纲要|地勘基金|财政投入|生态修复|绿色矿山标准',
     '政府/部委/监管动作：发文、标准、税费、进出口管制、整治'),
    ('会议会展', r'大会|论坛|峰会|展会|博览会|年会|开幕|会展|展览',
     '行业会议与展会，页面右栏已有「近期会展」'),
    ('技术与勘查', r'找矿|勘查|钻探|见矿|矿体|品位|资源量|储量|勘探|物探|化探|遥感|地球物理|地质调查|实验室|技术攻关|关键技术|突破|新工艺|选矿回收率|选冶|装备|科研|院士|获奖|专利|示范工程',
     '找矿成果 + 勘查/选冶技术与装备'),
    ('市场与价格', r'价格|报价|均价|现货|期货|库存|供需|紧平衡|过剩|缺口|进口量|出口量|进出口|消费量|溢价|升水|LME|SHFE|元/吨|美元/吨|预测|预计.*市场|涨跌',
     '价格、供需、进出口数据、市场预测'),
    ('项目与产能', r'投产|达产|开工|奠基|竣工|建成|扩产|复产|停产|减产|产能|万吨/年|吨/日|生产线|选厂|冶炼厂|采选|年处理|试生产',
     '矿山/产线建设、投产、产能变化'),
    ('企业经营', r'净利润|净利|营收|营业收入|业绩|财报|半年报|年报|同比增|同比减|董事长|总经理|人事|控股股东|股东变更|战略合作|认证|揭牌|中标',
     '公司财报、人事、合作、荣誉'),
]
FALLBACK = '行业动态'   # 一条都没命中时的兜底（目标：把它压到 10% 以下）

# ==================== 地域维（与主题正交，作为并列标签）====================
FOREIGN_SRC = {'SMM 国际站', 'MINING.COM', '全球矿产资源', '全球矿产资源信息系统'}
FOREIGN_HINT = (r'巴西|津巴布韦|英国|印尼|智利|澳洲|澳大利亚|加拿大|非洲|刚果|秘鲁|菲律宾|蒙古|'
                r'塞尔维亚|美国|欧盟|印度|日本|韩国|墨西哥|阿根廷|南非|赞比亚|坦桑尼亚|几内亚|'
                r'厄瓜多尔|玻利维亚|越南|马来西亚|老挝|缅甸|哈萨克斯坦|乌兹别克斯坦|格陵兰|海外|全球|国际')

COMPILED = [(name, re.compile(pat), desc) for name, pat, desc in RULES]
FOREIGN_RE = re.compile(FOREIGN_HINT)


def classify(title, summary, source, url):
    """返回 (主题分类, 地域, 命中说明)。命中说明用于人工复核「为什么归到这一类」。"""
    text = (title or '') + ' ' + (summary or '')
    hits = []
    for name, rx, _desc in COMPILED:
        m = rx.search(text)
        if m:
            hits.append((name, m.group(0)))
    if hits:
        theme, why = hits[0][0], '命中「%s」' % hits[0][1]
        if len(hits) > 1:
            why += '（同时命中：%s）' % '、'.join('%s·%s' % (n, k) for n, k in hits[1:3])
    else:
        theme, why = FALLBACK, '未命中任何规则'
    region = '国际' if (source in FOREIGN_SRC or FOREIGN_RE.search(title or '') or
                       re.search(r'mining\.com|smm\.cn/.*en|/en/', url or '')) else '国内'
    return theme, region, why


def load_items(path):
    with io.open(path, encoding='utf-8') as f:
        d = json.load(f)
    if isinstance(d, dict):
        items = d.get('news') or d.get('items') or []
    else:
        items = d
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=os.path.join(ROOT, 'mining_news.json'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--limit', type=int, default=0, help='明细条数上限，0=全部')
    args = ap.parse_args()

    items = load_items(args.src)
    if not items:
        print('没有读到条目：%s' % args.src)
        return 1

    rows = []
    for x in items:
        title = x.get('title') or x.get('t') or ''
        summ = x.get('summary') or x.get('s') or ''
        src = x.get('source') or x.get('src') or ''
        url = x.get('url') or x.get('u') or ''
        old = x.get('category') or x.get('c') or ''
        theme, region, why = classify(title, summ, src, url)
        rows.append({'title': title, 'old': old, 'new': theme, 'region': region,
                     'why': why, 'source': src})

    n = len(rows)
    new_cnt = Counter(r['new'] for r in rows)
    old_cnt = Counter(r['old'] for r in rows)
    region_cnt = Counter(r['region'] for r in rows)
    matrix = defaultdict(Counter)
    for r in rows:
        matrix[r['old']][r['new']] += 1
    fallback_rows = [r for r in rows if r['new'] == FALLBACK]
    conflict_rows = [r for r in rows if '同时命中' in r['why']]

    out = []
    w = out.append
    w('# 新闻分类体系试跑报告（%s）\n' % os.path.basename(args.src))
    w('**只试跑、未改动任何数据。** 共 %d 条。\n' % n)

    w('\n## 1. 分类体系定义（按内容归类，信源只辅助判断国内/国际）\n')
    w('| 优先级 | 类别 | 想抓住什么 | 典型关键词 |')
    w('|---|---|---|---|')
    for i, (name, pat, desc) in enumerate(RULES, 1):
        short = pat if len(pat) <= 60 else pat[:57] + '…'
        w('| %d | %s | %s | `%s` |' % (i, name, desc, short))
    w('| 兜底 | %s | 一条都没命中 | — |' % FALLBACK)

    w('\n## 2. 新旧分布对比\n')
    w('| 类别 | 现在 | 试跑后 |')
    w('|---|---|---|')
    keys = [k for k, _ in old_cnt.most_common()] + [k for k in RULES]
    seen = set()
    for k in [k[0] for k in RULES] + [FALLBACK] + [k for k, _ in old_cnt.most_common()]:
        if k in seen:
            continue
        seen.add(k)
        a = old_cnt.get(k, 0)
        b = new_cnt.get(k, 0)
        w('| %s | %d（%.0f%%） | %d（%.0f%%） |' % (k, a, 100.0 * a / n, b, 100.0 * b / n))
    w('\n兜底桶占比：**%.0f%% → %.0f%%**（%d → %d 条）'
      % (100.0 * old_cnt.get(FALLBACK, 0) / n, 100.0 * len(fallback_rows) / n,
         old_cnt.get(FALLBACK, 0), len(fallback_rows)))
    w('\n地域：' + '、'.join('%s %d 条' % (k, v) for k, v in region_cnt.most_common()))

    w('\n## 3. 变化矩阵（现在 → 试跑后）\n')
    w('| 现在的分类 | 拆分到 |')
    w('|---|---|')
    for old, c in sorted(matrix.items(), key=lambda kv: -sum(kv[1].values())):
        w('| %s（%d） | %s |' % (old or '(空)', sum(c.values()),
                               '、'.join('%s %d' % (k, v) for k, v in c.most_common())))

    w('\n## 4. 需要你拍板的存疑条目\n')
    w('### 4.1 没命中任何规则（仍落兜底 %s）—— %d 条' % (FALLBACK, len(fallback_rows)))
    if fallback_rows:
        w('')
        w('| 标题 | 信源 |')
        w('|---|---|')
        for r in fallback_rows[:40]:
            w('| %s | %s |' % (r['title'][:60].replace('|', '/'), r['source']))
        if len(fallback_rows) > 40:
            w('')
            w('（仅列前 40 条，共 %d 条）' % len(fallback_rows))
    w('\n### 4.2 同时命中多类（规则有歧义）—— %d 条' % len(conflict_rows))
    if conflict_rows:
        w('')
        w('| 标题 | 归为 | 为什么 |')
        w('|---|---|---|')
        for r in conflict_rows[:30]:
            w('| %s | %s | %s |' % (r['title'][:46].replace('|', '/'), r['new'], r['why'][:70]))

    w('\n## 5. 逐条明细\n')
    show = rows if not args.limit else rows[:args.limit]
    w('| # | 标题 | 现在 | 试跑后 | 地域 | 判定依据 |')
    w('|---|---|---|---|---|---|')
    for i, r in enumerate(show, 1):
        w('| %d | %s | %s | %s | %s | %s |' % (
            i, r['title'][:52].replace('|', '/'), r['old'], r['new'], r['region'], r['why'][:60]))

    text = '\n'.join(out)
    if args.out:
        with io.open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print('报告已写入：%s' % args.out)
    else:
        print(text)

    print('\n[汇总] 共 %d 条；兜底 %d 条（%.0f%%）；多类冲突 %d 条'
          % (n, len(fallback_rows), 100.0 * len(fallback_rows) / n, len(conflict_rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
