# -*- coding: utf-8 -*-
"""
classify_llm.py —— 用 LLM 按「内容」给新闻条目重新分类（替代按信源硬编码的旧分类）。

为什么需要它
------------
旧分类是 fetch_news.py 里给每个抓取源写死一个 category（例如 SMM 国际站 15 条
全是「国际矿业动态」），与内容无关，导致「行业动态」兜底桶塞了 50% 的条目。
关键词规则方案实测只有约 60% 准确率（详见 classify_dryrun.py 与试跑报告），
LLM 方案小样本实测 95%，故采用本脚本。

调用通道
--------
复用已部署的 Netlify 边缘函数 /api/qa（透传模式）。API Key 只存在 Netlify 环境变量里，
**本地与仓库中没有任何凭据**。本机访问 *.netlify.app 若用 curl 需 --http1.1，
本脚本用 urllib + create_default_context()，不关 TLS 校验。

数据层约定
----------
写入两个字段：
  category —— 8 个内容类之一（见 THEMES）
  region   —— 国内 / 国际
原分类保留到 orig_category，region 缺失或异常时不会让条目消失。
展示层（页面分栏）由 generate_common.bucket() 按 (category, region) 推导，
本脚本不碰展示层，两者解耦。

用法
----
  python classify_llm.py                     # 回填主库（默认两个文件）
  python classify_llm.py --dry-run           # 只打印不写盘
  python classify_llm.py --force             # 已分类的也重跑
  python classify_llm.py --batch 20 --limit 60
"""
import argparse
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

from logutil import get_logger

log = get_logger('classify_llm')

ENDPOINT = 'https://mining-daily-qa.netlify.app/api/qa'

THEMES = ['矿权出让', '并购与投资', '政策与监管', '会议会展',
          '技术与勘查', '市场与价格', '项目与产能', '企业经营', '行业动态']
REGIONS = ['国内', '国际']
# 矿权专区条目由 fetch_ma.py 单独维护，不参与主列表分类，跳过
SKIP_CATEGORIES = {'矿权交易', '矿权市场'}

SYSTEM = '你是矿业新闻分类引擎。只根据内容分类，不看信源。只输出结果 JSON，不要任何解释文字。'

RULES = """分类体系（每条只能选 1 个最贴切的类）：
1. 矿权出让 —— 矿业权（探矿权/采矿权）的挂牌、拍卖、协议出让、转让公示、成交/结果公示、竞得、起始价、矿业权登记/延续/新立
2. 并购与投资 —— 收购、并购、受让、股权转让、增资扩股、合资、重组、要约收购、参股、融资、承购协议。注意：只有涉及交易对价或控制权转移的才算；**同一集团内部的国有股权无偿划转、控股股东变更（无收购方、无对价）归「企业经营」**
3. 政策与监管 —— 政府/部委/监管机构发文、法律法规与条例、标准获批、税费、进出口管制与禁令、审批许可、行业整治、协会声明/倡议、补贴与激励计划、政府招标；**政府/部委主办、以宣贯法律法规为目的的培训班、宣贯班也归本类**。注意：只有发布主体是政府部门且内容是监管/法规/标准/税费/管制时才算；**企业、集团自办的培训班、研修班、安全环保培训不算**
4. 会议会展 —— 行业大会、论坛、峰会、展会、博览会、年会、报告会，以及企业/协会/集团自办的培训研修班
5. 技术与勘查 —— 找矿成果、钻探见矿、矿体与品位、资源量/储量核实、勘查与勘探技术、物探化探遥感、地质调查、**地质灾害调查与监测、应急技术支撑**、科研攻关与验收、专利、技术类奖项。注意：中国地质调查局、地勘单位做的技术工作归本类，不要因为出现"局""中心"就归政策
6. 市场与价格 —— 价格行情与走势、库存、供需与缺口、进出口/产销统计数据、市场预测
7. 项目与产能 —— 矿山或产线开工/奠基/投产/竣工/建成、产能变化、停产复产减产、产量完成情况、矿山建设进展
8. 企业经营 —— 财报业绩与分红、人事变动、控股股东/股东变更、战略合作、经营合同签订、上市、荣誉资质、公司治理
9. 行业动态 —— 以上都不属于（如纯宣传稿、无实质事件的抒情报道）

地域（选 1）：国内 / 国际 —— 按事件发生地或事件主体所在国判断，不要按信源判断。
例如「中国国际矿业大会在天津举办」是国内；「中国企业在海外项目投产」是国内主体但在境外，按内容侧重判断。

判定顺序建议：先看有没有明确的事件动作（开工/收购/发文/召开），再看主题领域。
宣传稿、口号式标题（如「承压奋进攀高逐新」）没有实质事件的，直接归「行业动态」。
分析性/评论性报道（如「某国采出全球X%的铜但仅冶炼Y%」）要看它讨论的核心对象是什么，按核心对象归类，不要因为"没有事件"就兜底。

输出：纯 JSON 数组，不要 markdown 代码块，不要多余文字。格式：
[{"n":1,"theme":"市场与价格","region":"国内"}, ...]

待分类条目：
"""


def build_user(batch):
    lines = []
    for it in batch:
        lines.append('%d. 标题：%s' % (it['n'], it['title']))
        lines.append('   信源：%s' % (it.get('source') or '（无）'))
        lines.append('   摘要：%s' % ((it.get('summary') or '（无摘要）')[:300]))
    return RULES + '\n'.join(lines)


def call_llm(messages, max_tokens=3000, temperature=0.0, retries=3):
    payload = {'messages': messages, 'max_tokens': max_tokens, 'temperature': temperature}
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                ENDPOINT, data=body,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                method='POST')
            ctx = ssl.create_default_context()   # 严禁关闭 TLS 校验
            with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
            last = e
            wait = 5 * (attempt + 1)
            log.warning('调用失败（第 %d 次）：%s，%d 秒后重试', attempt + 1, e, wait)
            time.sleep(wait)
    raise RuntimeError('LLM 调用连续失败：%s' % last)


def parse_result(content):
    m = re.search(r'\[.*\]', content, re.S)
    if not m:
        raise ValueError('响应中没有 JSON 数组')
    rows = json.loads(m.group(0))
    out = {}
    for r in rows:
        n = int(r['n'])
        theme = (r.get('theme') or '').strip()
        region = (r.get('region') or '').strip()
        if theme not in THEMES:          # 模型自造类名 → 兜底，绝不写脏数据
            log.warning('第 %d 条返回未知类名「%s」，回落行业动态', n, theme)
            theme = '行业动态'
        if region not in REGIONS:
            region = '国内'
        out[n] = (theme, region)
    return out


def atomic_write_json(path, data):
    buf = json.dumps(data, ensure_ascii=False, indent=1).encode('utf-8')
    assert len(buf) > 200, '写出内容异常小，疑似编码失败：%d' % len(buf)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(buf)
    os.replace(tmp, path)


def classify_file(path, batch_size, limit, force, dry_run):
    doc = json.load(io.open(path, encoding='utf-8'))
    items = doc['news']
    todo = []
    for i, e in enumerate(items):
        if (e.get('category') or '') in SKIP_CATEGORIES:
            continue
        if not force and (e.get('region') in REGIONS) and (e.get('category') in THEMES):
            continue                                  # 断点续跑
        todo.append((i, e))
    if limit:
        todo = todo[:limit]
    log.info('%s：共 %d 条，待分类 %d 条', path, len(items), len(todo))
    if not todo:
        return 0

    done = 0
    total = len(todo)
    for start in range(0, total, batch_size):
        chunk = todo[start:start + batch_size]
        batch = [{'n': k + 1,
                  'title': e.get('title', ''),
                  'source': e.get('source', ''),
                  'summary': e.get('summary', '')} for k, (_, e) in enumerate(chunk)]
        raw = call_llm([{'role': 'system', 'content': SYSTEM},
                        {'role': 'user', 'content': build_user(batch)}])
        if raw.get('_fallback'):
            raise RuntimeError('边缘函数走了关键词兜底，未真正调用模型：%s' % raw.get('_warning'))
        got = parse_result(raw['choices'][0]['message']['content'])
        miss = [b['n'] for b in batch if b['n'] not in got]
        if miss:
            log.warning('本批缺少 %d 条结果：%s', len(miss), miss)
        for k, (idx, e) in enumerate(chunk):
            if (k + 1) not in got:
                continue
            theme, region = got[k + 1]
            if not dry_run:
                if 'orig_category' not in e:
                    e['orig_category'] = e.get('category', '')
                e['category'] = theme
                e['region'] = region
            done += 1
        log.info('  批次 %d/%d 完成（%d 条）',
                 start // batch_size + 1, (total + batch_size - 1) // batch_size, len(chunk))
        time.sleep(1)

    if not dry_run:
        atomic_write_json(path, doc)
    log.info('%s：写入 %d 条%s', path, done, '（dry-run 未写盘）' if dry_run else '')
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--files', nargs='*',
                    default=['data/news_2026-08.json', 'data/news_2026-09.json'])
    ap.add_argument('--batch', type=int, default=30)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    total = 0
    for p in args.files:
        if not os.path.exists(p):
            log.error('文件不存在：%s', p)
            continue
        total += classify_file(p, args.batch, args.limit, args.force, args.dry_run)
    log.info('全部完成，共分类 %d 条', total)


if __name__ == '__main__':
    main()
