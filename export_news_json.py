# -*- coding: utf-8 -*-
"""
P0.5 数据底座：从 index.html 解析导出结构化 JSON
- 不依赖 generate_daily.py 内部变量，任何一天生成的 index.html 都能导出
- 覆盖三块：specialSection(专项区静态新闻) + todaySection(今日新增) + archiveSection(往期)
- 字段：id/title/url/source/orig_date/orig_date_full/report_date/first_seen/last_seen/
        category/is_new/tags/summary/embed
- tags：矿种（铜锂稀土…）+ 主题（政策找矿矿权市场技术安全国际），从标题+摘要提取

两路产出：
1. mining_news.json  —— 当日快照（覆盖式），给页面和快速查看用
2. data/news_YYYY-MM.json —— 月度分片（追加式累积），按 orig_date_full 归档，历史永不丢失
   同 id 条目合并时保留 first_seen、刷新 last_seen、保留更优的 embed 值

设计要点：index.html 的"往期"区内容是漂浮的（每天 AI 重新抓取，不是滚动窗口），
因此只有追加式累积库才能保证历史可回溯。页面保留几天与问答能力无关，两者已解耦。
news-data.js（前端问答检索库）仅导出最近 RETAIN_DAYS=30 天，避免随历史无限膨胀。

用法：python export_news_json.py [index.html路径] [输出json路径]
"""
import re
import os
import sys
import json
import hashlib
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')
JSON_PATH = os.path.join(BASE_DIR, 'mining_news.json')

sys.path.insert(0, BASE_DIR)
from logutil import get_logger  # noqa: E402

# 2026-09-10 增：低价值公告兜底词表（EXPORT_LOW_VALUE_NOTICE）。
# 设计依据：仅纳入用户在 1e 步骤明确列出的"公司治理/信披类公告"类型 + 持续督导。
# 与 fetch_news.py 的 ANNOUNCE_NOISE 区分开：ANNOUNCE_NOISE 是抓取阶段可激进过滤的
# 广词表（含"分红""诉讼进展"等会与实质新闻撞车的词），本表只用于 export 阶段兜底，
# 必须更保守，避免误杀"XX亿元中期分红""矿业子公司涉诉"这类实质产业事件。
EXPORT_LOW_VALUE_NOTICE = [
    # 持续督导类（连续 3 天反复爬回，必须堵住）
    "持续督导意见", "持续督导总结报告", "持续督导现场核查", "持续督导年度报告",
    # 用户 1e 步骤明确禁用
    "独立董事", "独立非执行董事", "候选人声明", "股东大会", "临时股东会", "会议通知",
    "法律意见书", "公司章程", "章程修订", "业绩说明会", "投资者关系活动记录",
    "接待日", "内幕信息", "知情人登记", "监事会决议", "董事会决议",
    "股票交易异常", "停牌公告", "复牌公告", "权益分派实施", "回购注销",
    "股权激励", "问询函回复", "关注函回复", "监管函回复", "更正公告", "补充公告",
    "延期回复", "关于召开", "董事离任", "补选董事", "保荐书", "跟踪评级",
    "审计报告", "券商核查意见",
]

# [snapshot]/[archive]/[frontend] 等段落标签保持原样，只是统一加上时间戳与级别。
# 告警仍走 stderr，与改造前一致（调用方按流过滤时不错位）。
log = get_logger('export_news_json')
log_err = get_logger('export_news_json', stream=sys.stderr)
DATA_DIR = os.path.join(BASE_DIR, 'data')          # 月度分片累积库
NEWS_DATA_JS = os.path.join(BASE_DIR, 'news-data.js')  # 前端问答检索条数据源

if len(sys.argv) > 1:
    INDEX_PATH = sys.argv[1]
if len(sys.argv) > 2:
    JSON_PATH = sys.argv[2]
    BASE_DIR = os.path.dirname(os.path.abspath(JSON_PATH)) or BASE_DIR
    DATA_DIR = os.path.join(BASE_DIR, 'data')

# 矿种关键词表
MINERALS = ['铜','镍','铅','锌','铝','金','银','稀土','钨','钼','锡','锑','锂','钴',
            '钛','铀','锰','钒','铬','镁','铌','钽','镓','锗','铟','铼','镉','铋','硒','碲','铂','钯','铁']
# 主题关键词表
TOPICS = {
    '政策': ['政策','规划','方案','条例','办法','通知','公告','公示','实施意见','管理规定','准入'],
    '找矿': ['找矿','勘查','勘探','新发现','矿床','突破','增储'],
    '矿权': ['探矿权','采矿权','出让','转让','挂牌','拍卖','矿权'],
    '市场': ['价格','产量','行情','上涨','下跌','供需','库存','利润','景气'],
    '技术': ['技术','数字化','智能','装备','研发','创新','材料'],
    '安全': ['安全','事故','本质安全'],
    '国际': ['国际','全球','海外','西澳','格陵兰','秘鲁','印尼','智利'],
}
# 往期子类标题 → 统一分类名（与今日六分类口径一致，保证检索口径统一）
CAT_NORMALIZE = {
    '找矿成果': '找矿成果与勘查技术',
    '矿权交易': '矿权交易',
    '行业动态': '行业动态',
    '国际矿业动态': '国际矿业动态',
    '培训与学术': '培训与学术',
    '政策法规': '政策法规',
}
# 专项区 sp-cat 子类 → 六分类口径映射
SP_CAT_MAP = {
    '政策与部署': '政策法规',
    '找矿成果与新发现': '找矿成果与勘查技术',
    '勘查技术与装备': '找矿成果与勘查技术',
    '战略矿产与资源安全': '行业动态',
}

def make_id(url):
    """由 URL 生成稳定 id（12 位十六进制），跨天合并时作为主键"""
    return hashlib.md5((url or '').encode('utf-8')).hexdigest()[:12]

def _is_low_value_notice(title, summary=''):
    """2026-09-10 增：低价值公告兜底过滤（仅命中用户 1e 步骤明确禁用的治理/信披类 + 持续督导）。

    用于 export 阶段：即使 index.html 被人工编辑误收录了治理类公告（如券商持续督导意见），
    或旧月份 news_*.json 残留了同类条目，导出前一律剔除；防止"删了 data 又被 export 复活"。

    故意不用 fetch_news.ANNOUNCE_NOISE 那张广词表——它含"分红""诉讼进展"等会与实质新闻
    撞车的词，会误杀"XX亿元中期分红""矿业子公司涉诉"这类产业事件。

    返回 (bool, matched_kw|'') 便于日志输出被剔除的原因。
    """
    t = title or ''
    s = summary or ''
    for kw in EXPORT_LOW_VALUE_NOTICE:
        if kw in t:
            return True, kw
    # 摘要命中也认（兜底场景：标题是"XX公司关于...的公告"，摘要补充持续督导）
    for kw in EXPORT_LOW_VALUE_NOTICE:
        if kw in s:
            return True, kw + '(in summary)'
    return False, ''

def full_date(orig_mmdd, report_date):
    """
    把 'MM-DD' 补全为 'YYYY-MM-DD'。
    以 report_date 年份为准；若补全后晚于 report_date，说明跨年，年份减 1。
    例：08-31 + 2026-09-01 → 2026-08-31 ；12-30 + 2027-01-02 → 2026-12-30
    """
    if not orig_mmdd:
        return ''
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', orig_mmdd)
    if m:                                    # 已是完整日期
        return orig_mmdd
    m = re.match(r'^(\d{2})-(\d{2})$', orig_mmdd.strip())
    if not m:
        return ''
    y = int(report_date[:4])
    cand = '%d-%s-%s' % (y, m.group(1), m.group(2))
    if cand > report_date:                   # 未来日期 → 归属上一年
        cand = '%d-%s-%s' % (y - 1, m.group(1), m.group(2))
    return cand

def strip_emoji(s):
    return re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d\u2190-\u21FF]+', '', s).strip()

def extract_tags(title, summary):
    """从标题+摘要提取矿种与主题标签"""
    text = (title or '') + ' ' + (summary or '')
    text = text.replace('金川', '').replace('有色金属', '').replace('金属', '')  # 防公司名/组合词误提取"金"
    tags = []
    for m in MINERALS:
        if m in text and m not in tags:
            tags.append(m)
    for topic, kws in TOPICS.items():
        if any(k in text for k in kws) and topic not in tags:
            tags.append(topic)
    return tags

def parse_all(html, report_date=''):
    """
    整页一遍扫描解析所有 news-item：
    - 跟踪当前 section（specialSection/todaySection/archiveSection）确定归属
    - 跟踪 sub-cat / sp-cat 确定分类
    - 锚点用 </body> 兜底，避免"区段最后一条新闻无前瞻锚点"而漏解析
    """
    pat = re.compile(
        r'<div class="section" id="([a-zA-Z]+)"[^>]*>'      # g1: section id
        r'|<div class="sub-cat"[^>]*>([^<]*)'               # g2: sub-cat
        r'|<div class="sp-cat"[^>]*>([^<]*)'                # g3: sp-cat
        r'|<div class="news-item([^"]*)"(.*?)(?=<div class="section" id=|<div class="sub-cat"[^>]*>|<div class="sp-cat"[^>]*>|<div class="news-item|</body>)',  # g4/g5
        re.S)
    items = []
    cur_cat = '行业动态'
    cur_zone = 'archive'   # special / today / archive
    zone_default_cat = {
        'specialSection': '找矿突破专项',
        'todaySection': '行业动态',
        'archiveSection': '行业动态',
    }
    for mm in pat.finditer(html):
        if mm.group(1) is not None:
            sid = mm.group(1)
            # 归档收藏区/安装指引区之后是JS模板与静态说明，非真实新闻，停止解析
            if sid in ('archivedFavSection', 'installGuideSection'):
                break
            cur_zone = ('today' if sid == 'todaySection'
                        else 'special' if sid == 'specialSection'
                        else 'archive')
            cur_cat = zone_default_cat.get(sid, '行业动态')
            continue
        if mm.group(2) is not None:      # sub-cat
            raw = re.sub(r'<span class="sub-count">.*?</span>', '', mm.group(2))
            name = strip_emoji(raw)
            name = re.sub(r'\d+\s*条?新增\s*$', '', name).strip()
            if name:
                cur_cat = CAT_NORMALIZE.get(name, name)
            continue
        if mm.group(3) is not None:      # sp-cat（专项子类）
            name = strip_emoji(mm.group(3))
            name = re.sub(r'<span class="sub-count">.*?</span>', '', name).strip()
            if name:
                cur_cat = SP_CAT_MAP.get(name, name)
            continue
        # news-item
        cls = mm.group(4) or ''
        block = mm.group(5) or ''
        url_m = re.search(r'data-url="([^"]+)"', block)
        title_m = re.search(r'class="news-title"[^>]*>([^<]+)</a>', block)
        if not url_m or not title_m:
            continue
        src_m = re.search(r'class="src">([^<]+)</span>', block)
        date_m = re.search(r'</span>\s*·\s*([0-9]{2}-[0-9]{2})', block)
        sum_m = re.search(r'class="news-summary">([^<]+)</div>', block)
        embed_m = re.search(r'data-embed="([^"]+)"', block)
        title = title_m.group(1).strip()
        url = url_m.group(1)
        od = date_m.group(1).strip() if date_m else ''
        item = {
            'id': make_id(url),
            'title': title,
            'url': url,
            'source': src_m.group(1).strip() if src_m else '',
            'orig_date': od,                          # 页面原始显示 MM-DD（兼容保留）
            'orig_date_full': full_date(od, report_date) or report_date,  # YYYY-MM-DD，可排序过滤
            'report_date': report_date,               # 本条被抓取入报的日期
            'category': cur_cat,
            'is_new': bool(re.search(r'\bis-new\b', cls)),
            'summary': sum_m.group(1).strip() if sum_m else '',
            'embed': embed_m.group(1) if embed_m else 'unknown',
        }
        item['tags'] = extract_tags(item['title'], item['summary'])
        items.append(item)
    return items

def load_month(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return {e['id']: e for e in d.get('news', []) if e.get('id')}
    except Exception:
        return {}

def merge_into_months(news, data_dir, report_date):
    """
    追加式累积：按 orig_date_full 的年月归档到 data/news_YYYY-MM.json
    - 同 id 合并：保留 first_seen，刷新 last_seen，保留更优 embed（ok/block 优先于 unknown）
    - 返回统计 dict
    """
    os.makedirs(data_dir, exist_ok=True)
    by_month = {}
    for e in news:
        by_month.setdefault(e['orig_date_full'][:7], []).append(e)

    stats = {'added': 0, 'updated': 0, 'months': {}}
    for month, entries in sorted(by_month.items()):
        path = os.path.join(data_dir, 'news_%s.json' % month)
        store = load_month(path)
        added = updated = 0
        for e in entries:
            old = store.get(e['id'])
            if old:
                e['first_seen'] = old.get('first_seen') or report_date
                e['last_seen'] = report_date
                # embed 保留已知值，避免unknown覆盖真实检测结果
                if e.get('embed') == 'unknown' and old.get('embed') in ('ok', 'block'):
                    e['embed'] = old['embed']
                updated += 1
            else:
                e['first_seen'] = report_date
                e['last_seen'] = report_date
                added += 1
            store[e['id']] = e
        rows = sorted(store.values(),
                      key=lambda x: (x.get('orig_date_full') or '', x.get('id') or ''),
                      reverse=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'month': month,
                       'updated_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                       'count': len(rows),
                       'news': rows}, f, ensure_ascii=False, indent=2)
        stats['added'] += added
        stats['updated'] += updated
        stats['months'][month] = {'added': added, 'updated': updated, 'total': len(rows)}
    write_index(data_dir)
    return stats

def write_index(data_dir):
    """生成 data/index.json 总索引：各月条目数与日期覆盖，供检索器快速定位"""
    months = []
    for fn in sorted(os.listdir(data_dir)):
        if not (fn.startswith('news_') and fn.endswith('.json')):
            continue
        path = os.path.join(data_dir, fn)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            continue
        rows = d.get('news', [])
        dates = sorted({e.get('orig_date_full', '') for e in rows if e.get('orig_date_full')})
        months.append({'month': d.get('month', fn[5:-5]),
                       'count': len(rows),
                       'date_from': dates[0] if dates else '',
                       'date_to': dates[-1] if dates else '',
                       'days_covered': len(dates)})
    with open(os.path.join(data_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'updated_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                   'schema_version': '1.1',
                   'total': sum(m['count'] for m in months),
                   'months': months}, f, ensure_ascii=False, indent=2)

def write_news_data_js(data_dir, out_path):
    """生成前端问答检索条的数据源 news-data.js（window.NEWS_DATA）

    用短字段名压体积（d/t/s/u/g/c/m），因为要随日报一起进浏览器。
    页面加载失败时前端会自动降级为从 DOM 提取，所以这里出错不影响日报本身。
    """
    rows = []
    for fn in sorted(os.listdir(data_dir)):
        # 2026-09-10 修：原本 fn.startswith('news_') 会把候选池 news_candidates_*.json
        # 也读进来——而候选池是中间产物（不 commit 不 deploy），里面残留的低价值条目
        # 会"复活"到 news-data.js。必须严格匹配月库命名 news_YYYY-MM.json。
        if not (fn.startswith('news_') and fn.endswith('.json')):
            continue
        if fn.startswith('news_candidates_'):        # 候选池：中间产物，不读
            continue
        if not re.match(r'^news_\d{4}-\d{2}\.json$', fn):  # 非月库格式：忽略
            continue
        try:
            with open(os.path.join(data_dir, fn), 'r', encoding='utf-8') as f:
                rows.extend(json.load(f).get('news', []))
        except Exception as e:
            log_err.warning('[warn] 读取失败 %s: %s', fn, e)
            continue
    # 2026-09-10 增：news-data.js 合成前再兜一道低价值过滤。
    # 兜底场景：旧月份 news_*.json 里残留的治理类公告（如"持续督导意见"）
    # 若未在月度库中手动删除，会被原样写进检索条；这里再清一遍。
    _rows_lv = []
    _dropped_lv = 0
    for _r in rows:
        _is_lv, _ = _is_low_value_notice(_r.get('title', ''), _r.get('summary', ''))
        if _is_lv:
            _dropped_lv += 1
        else:
            _rows_lv.append(_r)
    if _dropped_lv:
        log.info('[news-data low-value] 兜底剔除 %d 条（来自月度库残留）', _dropped_lv)
    rows = _rows_lv
    # 同一公告可能因抓取器 URL 形态不同（如 PDF 直链 vs cninfo 详情页）产生重复记录；
    # 按 title 归并去重：优先保留 static.cninfo.com.cn/finalpage PDF 直链（更稳定），
    # 剔除 cninfo.com.cn/new/disclosure/detail 详情页形态，避免「今日要闻/问答」出现重复。
    # 仅对「并购与投资」类公告做此归并，避免误杀不同来源的同名新闻。
    def _is_pdf(u): return 'static.cninfo.com.cn/finalpage/' in (u or '')
    merged = []
    seen_ma_title = {}
    for r in rows:
        if r.get('category') == '并购与投资':
            t = r.get('title', '')
            if t in seen_ma_title:
                # 若已有 detail 形态而本条为 PDF 直链 → 用 PDF 替换
                if _is_pdf(r.get('url', '')) and not _is_pdf(seen_ma_title[t].get('url', '')):
                    merged.remove(seen_ma_title[t])
                    seen_ma_title[t] = r
                    merged.append(r)
                continue
            seen_ma_title[t] = r
            merged.append(r)
        else:
            merged.append(r)
    rows = merged
    rows.sort(key=lambda r: (r.get('orig_date_full', ''), r.get('id', '')), reverse=True)
    # 搜索库保留窗口：news-data.js 导出最近 RETAIN_DAYS 天，避免随历史无限膨胀
    RETAIN_DAYS = 365
    _cut = datetime.date.today() - datetime.timedelta(days=RETAIN_DAYS)
    def _odt(s):
        try:
            return datetime.date.fromisoformat(s)
        except Exception:
            return None
    _before = len(rows)
    rows = [r for r in rows if (_odt(r.get('orig_date_full', '')) or _cut) >= _cut]
    if _before != len(rows):
        log.info('[news-data] 保留 %d 天内 %d/%d 条（剔除 %d 条更早）',
              RETAIN_DAYS, len(rows), _before, _before - len(rows))
    slim = [{
        'd': r.get('orig_date_full', ''),
        't': r.get('title', ''),
        's': r.get('source', ''),
        'u': r.get('url', ''),
        'g': r.get('tags', []),
        'c': r.get('category', ''),
        'm': (r.get('summary', '') or '')[:120],
        'n': r.get('first_seen', ''),   # 收录日期（今日要闻条用 n==report_date 识别当日新增）
    } for r in rows]
    payload = {'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
               'schema': '1.2-slim', 'total': len(slim), 'news': slim}
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('window.NEWS_DATA='
                + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                + ';')
    return len(slim), os.path.getsize(out_path)


def main():
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # 本次日报日期：从"今日新增（YYYY-MM-DD 抓取）"提取（必须先算，parse_all 要用它补年份）
    rd = re.search(r'今日新增（(\d{4}-\d{2}-\d{2})', html)
    report_date = rd.group(1) if rd else datetime.date.today().strftime('%Y-%m-%d')

    news = parse_all(html, report_date)

    # 按url去重（优先保留 is_new 的条目）
    news.sort(key=lambda x: not x['is_new'])
    seen, dedup = set(), []
    for e in news:
        if e['url'] in seen:
            continue
        seen.add(e['url'])
        dedup.append(e)
    news = dedup

    # 2026-09-10 增：低价值公告兜底过滤（与 fetch_news.ANNOUNCE_NOISE 同词表）。
    # 在去重后、merge_into_months 前过滤——保证"删了 index.html 中误收的治理类"后，
    # 月度库 news_*.json 也不会被复活。这是 export 阶段的安全网。
    _filtered, _lv_drop = [], []
    for _e in news:
        _is_lv, _kw = _is_low_value_notice(_e.get('title', ''), _e.get('summary', ''))
        if _is_lv:
            _lv_drop.append((_e, _kw))
        else:
            _filtered.append(_e)
    if _lv_drop:
        for _e, _kw in _lv_drop:
            log.info('[low-value-filter] 剔除 %s | %s | kw=%s | %s',
                     _e.get('source', ''), _e.get('title', '')[:60], _kw,
                     _e.get('url', '')[:80])
        log.info('[low-value-filter] 共剔除 %d 条（页面解析后），剩余 %d',
                 len(_lv_drop), len(_filtered))
    news = _filtered

    # 追加式写入月度分片累积库（历史永不丢失）
    stats = merge_into_months([dict(e) for e in news], DATA_DIR, report_date)

    sources = sorted({e['source'] for e in news if e['source']})
    # 页面实际渲染的 news-item 总数/今日新增数
    # 口径（2026-09-08 修正）：只统计「今日区 + 专项区 + 往期区」，排除 rightsSection。
    # 矿权专区内的卡片由 renderRightsSection() 从 NEWS_DATA 渲染，不属于新闻条目，
    # 计入会让 page_total 虚高（实测 2026-09-08：全页 112 条 vs 实际 110 条，
    # 差的 2 条正是 rightsSection 内的卡片），导致与 meta.total 长期对不上。
    _p_today = html.find('id="todaySection"')
    _p_rights = html.find('id="rightsSection"')
    if _p_today >= 0 and _p_rights > _p_today:
        _seg = html[_p_today:_p_rights]
        page_total = len(re.findall(r'<div class="news-item', _seg))
        page_new = len(re.findall(r'<div class="news-item[^"]*is-new', _seg))
    else:
        # 边界定位失败时退回全页统计，但必须显式告警，杜绝「静默口径偏差」
        log_err.warning('[warn] 未定位到 todaySection/rightsSection 边界，'
              'page_total 退回全页统计（可能高于 meta.total）')
        page_total = len(re.findall(r'<div class="news-item', html))
        page_new = len(re.findall(r'<div class="news-item[^"]*is-new', html))
    result = {
        'meta': {
            'report_date': report_date,
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'total': len(news),
            'new_today': sum(1 for e in news if e['is_new']),
            'archive': sum(1 for e in news if not e['is_new']),
            'page_total': page_total,
            'page_new_count': page_new,
            'sources': sources,
            'schema_version': '1.1',
            'archive_hint': '历史全量见 data/news_YYYY-MM.json（追加式累积），检索用 query_news.py',
            'note': 'P0.5 数据底座：由 export_news_json.py 从 index.html 解析导出（URL去重），供矿业情报智能体查询',
        },
        'news': news,
    }
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info('[snapshot] %s', JSON_PATH)
    log.info('  report_date: %s | total: %d | new: %d | archive: %d | sources: %d',
          report_date, len(news), result['meta']['new_today'],
             result['meta']['archive'], len(sources))
    log.info('[archive] %s', DATA_DIR)
    log.info('  added: %d | updated: %d | total: %d',
          stats['added'], stats['updated'], sum(m['total'] for m in stats['months'].values()))
    for month, s in sorted(stats['months'].items()):
        log.info('    %s  +%d  ~%d  =%d', month, s['added'], s['updated'], s['total'])
    # 前端问答检索条数据源（页面加载不到时自动降级为 DOM 提取，失败不阻塞）
    try:
        n, size = write_news_data_js(DATA_DIR, NEWS_DATA_JS)
        log.info('[frontend] %s', NEWS_DATA_JS)
        log.info('  %d 条 | %.1f KB（网页问答检索条数据源）', n, size / 1024.0)
    except Exception as e:
        log_err.warning('[warn] news-data.js 生成失败，网页问答将降级为页面内检索：%s', e)
    return result

if __name__ == '__main__':
    main()
