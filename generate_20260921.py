# -*- coding: utf-8 -*-
"""
生成 2026-09-21 矿业资讯速览 index.html
- 09-20 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-21）回补历史条目
- 换入 09-19~09-20 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-18 收盘 + LME 09-18 收盘（东财日K末点已追平，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（本日无新增矿权公告，原样保留）
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""
import re, datetime, json, glob, os
from source_whitelist import is_allowed
from generate_common import (
    ni, card, _replace_block, split_items, item_url, strip_new, _esc, render_cat_groups,
    UP, DOWN, FLAT, TAG_TODAY, TAG_ARCH, TAG_RIGHTS,
    CAT_KQ, CAT_ZK, CAT_HY, CAT_GJ, CAT_MA, CAT_ZC, CAT_SC, MA_REQUIRE, window,
    THEME_BUCKET, LEGACY_BUCKET, bucket,
    item_after_cutoff as _item_after_cutoff,
    _lib_item as _lib_item_raw,
    _reclassify_ma as _reclassify_ma_raw,
    dedup_same_event, item_title, same_event,
    unit_class, UNIT_SHFE_GROUP, UNIT_LME_GROUP,
)
from functools import partial


SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-21'
GRAB = '2026-09-21'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月21日 星期一', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新',
              'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡刷新（全部现算，禁止手抄） ============
_ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']

SHFE_DEFS = [
    ('cum', '沪铜', 'SHFE', '元/吨', 0),
    ('alm', '沪铝', 'SHFE', '元/吨', 0),
    ('pbm', '沪铅', 'SHFE', '元/吨', 0),
    ('znm', '沪锌', 'SHFE', '元/吨', 0),
    ('snm', '沪锡', 'SHFE', '元/吨', 0),
    ('nim', '沪镍', 'SHFE', '元/吨', 0),
    ('au9999', '上海金', 'Au99.99', '元/克', 2),
    ('agtd', '白银', 'Ag(T+D)', '元/千克', 0),
    ('lcm', '碳酸锂', '主力连续', '元/吨', 0),
]
shfe_cards = []
for slug, name, tag, unit, nd in SHFE_DEFS:
    pts = _ph[slug]['points']
    prev, cur = pts[-2][1], pts[-1][1]
    chg = cur - prev
    pct = chg / prev * 100.0 if prev else 0.0
    val = format(cur, ',.%df' % nd)
    arrow = UP if chg >= 0 else DOWN
    sign = '+' if chg >= 0 else ''
    chgtxt = '%s %s%s (%s%.2f%%)' % (arrow, sign, format(chg, ',.%df' % nd), sign, pct)
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down',
                           group_unit=UNIT_SHFE_GROUP))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
# 单位同为「元/吨」= 国内盘分组单位 -> 走 unit_class 隐藏重复单位（2026-09-13 契约）
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="%s">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>'
              % (DATA_ASOF, unit_class('元/吨', UNIT_SHFE_GROUP)))

_lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']
_lme_map = {m['slug']: m for m in _lme}
LME_DEFS = [
    ('lcpt', 'LME 铜'), ('lalt', 'LME 铝'), ('lznt', 'LME 锌'),
    ('lldt', 'LME 铅'), ('lnkt', 'LME 镍'), ('ltnt', 'LME 锡'),
]
lme_list = []
for slug, name in LME_DEFS:
    m = _lme_map[slug]
    if m['price'] is None:
        lme_list.append((slug, name, 'LME', '--', '美元/吨', '暂无数据', 'flat'))
        continue
    arrow = UP if m['chg'] >= 0 else DOWN
    val = format(m['price'], ',.2f')
    sign = '+' if m['chg'] >= 0 else ''
    chg = '%s %s (%s%.2f%%)' % (arrow, sign + format(m['chg'], ',.2f'), sign, m['chg_pct'])
    lme_list.append((slug, name, 'LME', val, '美元/吨', chg, 'up' if m['chg'] >= 0 else 'down'))
lme_html = ''.join(card(*c, group_unit=UNIT_LME_GROUP) for c in lme_list)

html = _replace_block(html, '<div class="price-cards" id="priceCardsShfe">', shfe_html)
html = _replace_block(html, '<div class="price-cards price-cards-lme" id="priceCardsLme">', lme_html)

# ============ 3. 解析今日/往期两个区 ============
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_r = html.find(TAG_RIGHTS)
assert 0 <= i_t < i_a < i_r, 'markers not found'

m_today = html.find('<!-- ==================== 今日新增')
assert m_today != -1, '今日新增 marker missing'

today_raw = html[i_t:i_a]
arch_raw = html[i_a:i_r]

today_items = split_items(today_raw)
arch_items = split_items(arch_raw)

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it and cat != CAT_KQ]
arch_keep = [(cat, strip_new(it)) for cat, it in arch_items
             if '<div class="news-item' in it and cat != CAT_KQ and item_after_cutoff(it)]

# ── URL → (内容类, 地域) 索引：让存量条目也能按新分类体系重新分桶 ──
_url_theme = {}
for _fn in sorted(glob.glob('data/news_2026-*.json')):
    try:
        _lib = json.load(open(_fn, encoding='utf-8'))['news']
    except Exception:
        continue
    for _e in _lib:
        _u = _e.get('url', '')
        if _u and _e.get('region'):
            _url_theme[_u] = (_e.get('category', ''), _e.get('region', ''))


def _reclassify_by_url(cat, it):
    """用月库里的 LLM 分类结果覆盖旧桶名。查不到则原样返回。"""
    th_rg = _url_theme.get(item_url(it))
    return bucket(th_rg[0], th_rg[1]) if th_rg else cat


merge_seq = []
seen_url = set()
for cat, it in prev_today + arch_keep:
    url = item_url(it)
    if url in seen_url:
        continue
    seen_url.add(url)
    merge_seq.append((_reclassify_by_url(cat, it), it))

merge_seq = dedup_same_event(merge_seq)

# ============ 3.5 从累计库回补 30 天窗口 ============
CAT_MAP = dict(LEGACY_BUCKET)
CAT_MAP.update(THEME_BUCKET)
LIB_SKIP = {'矿权交易', '并购与投资'}
_lib_item = partial(_lib_item_raw, cat_map=CAT_MAP)

_lib_pool = []
for _fn in sorted(glob.glob('data/news_2026-*.json')):
    try:
        _lib = json.load(open(_fn, encoding='utf-8'))['news']
    except Exception:
        continue
    for _e in _lib:
        if _e.get('category') in LIB_SKIP:
            continue
        _odf = _e.get('orig_date_full', '') or ''
        if _odf < CUTOFF_DT.isoformat():
            continue
        _url = _e.get('url', '')
        if not _url or _url in seen_url:
            continue
        _it = _lib_item(_e)
        if not _it:
            continue
        _lib_pool.append((_odf, _url, _it))
_lib_pool.sort(key=lambda t: t[0], reverse=True)
for _odf, _url, _it in _lib_pool:
    seen_url.add(_url)
    merge_seq.append(_it)
print('library backfill added:', len(_lib_pool))

new_items = [
    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260920_10318184.htm',
                '全球矿产资源信息系统', '09-20',
                '西澳州艾雷隆铌矿钻探见矿 51 米 五氧化二铌品位 5%',
                '据矿业新闻网（Miningnews.net）报道，恩康特资源公司（Encounter Resources）在西澳州西奥伦塔地区艾雷隆（Aileron）项目格林（Green）矿床扩边钻探见到该项目迄今最高品位铌矿体：63 米深处见矿 51 米、五氧化二铌品位 5%，其中 88 米深处见矿 13 米、品位 10.4%，矿体真厚度尚不确定。格林矿床推测矿石资源量 1900 万吨、品位 1.6%，艾雷隆项目总资源量 1.2 亿吨、品位 0.77%；现场 3 台钻机正执行 7 万米钻探计划。')),
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/dwdt/202609/t20260920_869315.html',
                '中国地质调查局', '09-16',
                '四川冕宁-德昌稀土成矿带探获隐伏稀土矿体',
                '中国地质科学院矿产资源研究所牵头的「战略新兴产业矿产地质调查与区块优选」项目，在四川冕宁-德昌稀土成矿带探获隐伏稀土矿体。TZK0301 钻孔穿越约 114.5 米厚第四系覆盖层后，揭露视厚度超 200 米含矿破碎带，孔内发育 3 层隐伏矿体、累计视厚度约 22.4 米。该发现验证了时频电磁测量与伽马放射性测量组合方法在厚覆盖区识别隐伏稀土矿化的有效性，拓展了成矿带深部及覆盖区找矿空间。')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260920_10318182.htm',
                '全球矿产资源信息系统', '09-20',
                '多米尼加拟于 2027 年上半年公布首个稀土储量',
                '据 BNAmericas 网站报道，多米尼加共和国能矿部已汇总稀土项目 5000 多项样品分析结果，计划今年 11 月确定资源量，并在完成选冶、经济、环境和物流等可行性论证后，于 2027 年上半年宣布首个储量。能矿部长桑托斯同时强调与美国签署的关键矿产合作框架，该框架通过担保、贷款、股权投资、承购协议和保险等手段，动员政府与私营部门加大对采矿和加工项目的支持。')),
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104121119-south-american-legislation-reshapes-supply-europe-accelerates-magnet-del',
                'SMM 国际站', '09-18',
                '巴西关键矿产立法强化交易审查 欧洲磁材实现首批车企交付',
                'SMM 海外稀土周报显示，阿根廷众议院矿业委员会同意推进将稀土列入矿业法典并定为战略资产的议案，巴西国会同步推进关键矿产立法，赋予政府对矿业交易、股权变更和出口增值承诺更大审查权，未来南美供给需在政府审查、本地加工义务与长期承购安排下重新定价。产业端，Neo 材料爱沙尼亚磁材厂实现首批电动汽车驱动电机烧结钕铁硼磁体商业交付，一期 A 阶段产能 2000 吨/年、规划扩至 5000 吨/年；Ucore 获美国国防部追加 460 万美元，钐钆分离二期资金由 1840 万美元提高至 2300 万美元。',
                orig_title='South American Legislation Reshapes Supply, Europe Accelerates Magnet Delivery and Military-Civil Separation [SMM Rare Earth Overseas Weekly Review]')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/93ba19805c1e4952858008c8c296ea1f.html',
                '长江有色网', '09-20',
                '伦锌单周领涨有色 1.52% 挤仓行情下风险边界收窄',
                '隔周伦锌走出独立领涨行情，开盘 3880 美元/吨，最高 3947 美元/吨，尾盘收报 3941 美元/吨，单周上涨 59 美元、涨幅 1.52%；当周成交量 12532 手、环比减少 1498 手，持仓量 261291 手、环比减少 832 手。国内盘面同步跟涨，沪锌主力 2611 合约周五晚间收报 26745 元/吨，上涨 170 元、涨幅 0.64%，站稳箱体高位上沿。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/2f12f18919d1422d86fdacfbeff83a5d.html',
                '长江有色网', '09-20',
                '钴价 9 月累计跌幅达 7.17% 较年初跌逾 39%',
                '截至 9 月 18 日，长江现货 1# 钴报 28.5 万元/吨，9 月累计跌幅 7.17%，较年初均价 46.8 万元/吨下跌逾 39%。本轮下跌是需求疲软、成本塌陷与资金行为三重共振的结果，「金九」旺季需求预期落空。')),
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260920_10318186.htm',
                '全球矿产资源信息系统', '09-20',
                '弗里德兰：未来 10 年铜需求相当于过去 1 万年产量',
                '据矿业周刊（Miningweekly）报道，艾芬豪矿业创始人罗伯特·弗里德兰在彭博播客中表示，数据中心、电动汽车和再工业化推动铜需求增长而铜生产滞后，未来 10 年需要开采的铜相当于过去 1 万年的生产总量。他同时指出，霍尔木兹海峡关闭推高硫酸价格，而全球约 20% 的铜生产依赖硫酸浸出，贸易战与资源民族主义进一步加剧供应紧张。')),
    (CAT_SC, ni('https://news.smm.cn/news/104124454',
                '上海有色网', '09-20',
                '中国 8 月精炼铅进口量同比激增 404.16%',
                '海关统计数据在线查询平台显示，中国 2026 年 8 月精炼铅进口量为 9178.51 吨，环比下降 0.39%、同比上升 404.16%，其中自澳大利亚进口 6302.70 吨、环比上升 290.74%；当月精炼铅出口量仅 385.50 吨，环比下降 82.30%、同比下降 85.99%。')),
    (CAT_SC, ni('https://news.smm.cn/news/104124435',
                '上海有色网', '09-20',
                '中国 8 月原铝进口量同比下降 14.05%',
                '海关统计数据显示，中国 2026 年 8 月原铝进口量 185514.79 吨，环比上升 0.16%、同比下降 14.05%，其中自俄罗斯进口 178150.42 吨、环比上升 0.85%、同比上升 28.99%；当月原铝出口量 21859.32 吨，环比下降 30.69%、同比下降 14.69%。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://news.smm.cn/news/104124366',
                '上海有色网', '09-20',
                '中金岭南凡口铅锌矿 9 月 17 日恢复生产',
                '中金岭南（000060）公告，凡口铅锌矿因 8 月 1 日井下采场进路冒顶事故停产，现已按广东省应急管理厅要求完成整改并通过逐级验收，自 2026 年 9 月 17 日起恢复生产；复产公告暂未披露事故官方调查结论，也未量化停产造成的产量损失。公司 2026 年上半年归母净利润 11.42 亿元、同比增长 104.35%，营收同比增长 35.53%。')),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104124517-shenhuo-group-launches-50000-tonne-sodium-ion-battery-aluminum-foil-proj',
                'SMM 国际站', '09-20',
                '神火集团 5 万吨钠离子电池铝箔项目开工 建设期 24 个月',
                '神火集团年产 5 万吨钠离子高性能电池铝箔项目 9 月 16 日举行开工仪式，规划建设约 4 万平方米生产车间及智能仓储系统，配置 3 台 1850 毫米和 3 台 2150 毫米铝箔轧机等设备，主要生产 1070、1100 等合金牌号、厚度 8—20 微米的钠电池正负极用铝箔，建设期 24 个月。项目建成后可形成 16.5 万吨铝箔加工能力、新增就业 300 人以上。',
                orig_title='Shenhuo Group Launches 50,000-Tonne Sodium-Ion Battery Aluminum Foil Project')),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104124519-yunnan-aluminium-achieves-first-batch-production-of-large-diameter-rare-',
                'SMM 国际站', '09-20',
                '云铝股份大直径稀土铝合金圆锭实现首批生产',
                '云铝股份（000807）宣布，首批直径 305 毫米的铝镧合金油气滑热顶圆铸锭在昭通生产基地成功下线并已取得批量客户订单，成为中铝集团旗下首家实现大直径稀土铝合金热顶圆铸锭批量生产的企业。',
                orig_title='Yunnan Aluminium Achieves First Batch Production of Large-Diameter Rare-Earth Alloy Billets')),
    (CAT_HY, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260920_869329.html',
                '中国地质调查局', '09-17',
                '人民日报：我国已建成省级以上绿色矿山 5600 余家',
                '人民日报报道，我国已建成省级以上绿色矿山 5600 余家，覆盖勘查、开发、修复全生命周期的绿色变革正在推进。湖南柿竹园多金属矿通过技术攻关，钨选矿回收率由 26.8% 提高到 70% 以上、萤石回收率由不到 30% 提高到 65% 以上，累计盘活矿石量 1.5 亿吨；山东齐河—禹城富铁矿勘查区「十四五」新增富铁矿资源量 1.42 亿吨，勘查临时用地复垦复耕率达 100%。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/attacks-on-mining-operations-on-the-rise-in-pakistan-report',
                'MINING.COM', '09-20',
                '巴基斯坦俾路支省矿业设施年内遭 38 起袭击',
                '据 MINING.COM 报道，ACLED 数据显示巴基斯坦俾路支省 1—9 月共发生 38 起与采掘业相关的袭击事件，2026 年已有 30 多个矿业项目遭袭，近三年累计超过 130 起。近 90% 的分离主义袭击针对矿物项目的运输环节，武装人员多射击车辆轮胎瘫痪运输、破坏财产而非造成人员伤亡，意在制造不稳定氛围；Reko Diq 铜矿与 Saindak 铜金矿等外资参与的重点项目由私营和国家安全力量保护。',
                orig_title='Attacks on mining operations on the rise in Pakistan: report')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104124518-alba-ceo-companys-aluminum-output-at-80-of-pre-war-levels-exports-via-je',
                'SMM 国际站', '09-20',
                '巴林铝业产量恢复至战前 80% 改道吉达与苏哈尔港出口',
                '巴林铝业（Alba）首席执行官 Ali Al Baqali 表示，公司当前铝产量约为战前水平的 80%，出口改经沙特红海吉达港和阿曼苏哈尔港。',
                orig_title="Alba CEO: Company's Aluminum Output at 80% of Pre-War Levels, Exports via Jeddah and Sohar Ports")),
    (CAT_GJ, ni('https://www.ccmn.cn/news/ZX018/202609/13f3b7d2d5544c16bcbf3b19a0ed1784.html',
                '长江有色网', '09-20',
                '50% 铝关税反噬北美铝轧制业 Novelis 金斯敦工厂裁员约 80 人',
                '美国对进口铝加征 50% 关税后，产业反噬效应正从贸易成本端向实体生产端传导。全球头部铝轧制企业 Novelis 于 9 月 18 日宣布对其位于加拿大金斯敦的铝轧制设施实施劳动力缩减，涉及裁员约 80 人（10 名受薪岗位员工与 70 名小时工），占该工厂总用工量的三分之一。')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104124516-baise-high-tech-zone-signs-26b-in-aluminum-projects-at-asean-oriented-co',
                'SMM 国际站', '09-20',
                '百色高新区签约 5 个铝深加工项目 总投资约 26 亿元',
                '9 月 17 日，借助百色建设面向东盟的泛铝件制造基地大会，百色高新区签约 5 个铝深加工项目，总投资约 26 亿元（SMM 英文标题作 26 亿美元，正文表述为人民币 26 亿元，以正文为准）。项目锚定先进制造，聚焦新能源精密铝型材、电子铝箔、高性能铝基新材料、铜铝复合新材料以及导体电缆等高附加值产品。',
                orig_title='Baise High-Tech Zone Signs $2.6B in Aluminum Projects at ASEAN-Oriented Conference')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104124490-sk-on-to-supply-18gwh-lfp-batteries-to-neovolta-for-us-energy-storage-pr',
                'SMM 国际站', '09-20',
                'SK On 与 NeoVolta 签署 18GWh 磷酸铁锂电池供货协议',
                'SK On 9 月 19 日宣布与储能企业 NeoVolta Power 签署长期战略协议，2027—2031 年供应 9GWh 磷酸铁锂软包电芯，用于公用事业级及工商业储能，由其美国工厂生产；另有 9GWh 电芯供应及电池包回购安排，合计合作规模 18GWh。签约仪式 8 月 27 日在首尔 SK On 总部举行，标志其从高镍动力电池向储能磷酸铁锂扩张。',
                orig_title='SK On to Supply 18GWh LFP Batteries to NeoVolta for US Energy Storage Projects Through 2031')),
    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260920_10318185.htm',
                '全球矿产资源信息系统', '09-20',
                '克里蒂卡尔拟在罗马尼亚建稀土冶炼厂 估算投资 18.5 亿美元',
                '据 Mining.com 报道，克里蒂卡尔金属公司（Critical Metals）称其专利工艺可溶解坦布里兹项目 99% 以上异性石精矿并回收 19 种超纯稀土及关键金属产品，计划在罗马尼亚建设冶炼厂。该厂设计年处理异性石精矿 10 万吨，年产稀土及关键金属产品 27943 吨，并副产高纯二氧化硅 25670 吨；初步估算投资 18.5 亿美元，模型测算年收入 22 亿美元、净现值约 45 亿美元、内部收益率 55%、回报期约 2 年。')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104124414-guibao-technology-subsidiary-completes-100-million-yuan-capital-increase',
                'SMM 国际站', '09-20',
                '贵宝科技子公司完成 1 亿元增资 推进 5 万吨硅碳负极项目',
                '贵宝科技（300019）公告，已完成对全资子公司贵宝（眉山）新能源材料有限公司的 1 亿元增资并办理工商变更登记。该子公司负责在四川彭山经济开发区建设年产 5 万吨锂电池硅碳负极材料及专用粘合剂项目，规划总投资 5.6 亿元；增资后注册资本由 1 亿元增至 2 亿元，公司仍持股 100%。',
                orig_title='Guibao Technology Subsidiary Completes 100 Million Yuan Capital Increase to Accelerate Implementation of Silicon Carbon Anode and Other Projects')),
]

# ============ 并购关键词重归类 ============

CAT_MA2 = CAT_MA
_reclassify_ma = partial(_reclassify_ma_raw, cat_ma=CAT_MA2, ma_require=MA_REQUIRE)

unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((_reclassify_ma(_reclassify_by_url(cat, it), it), it))
new_items = unique_new

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（2026-09-14 新增，复用 verify_numbers） ============
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字。
# 候选池未落盘或未开 --fetch-detail 时源文基准为空 -> 自动 skip（不阻断生成）。
# 生产守门：置 VERIFY_NUMBERS_STRICT=1 时未落地即抛异常（CI / 上线前卡点）。
try:
    from verify_numbers import verify_new_items
    _num_issues = verify_new_items(new_items, REPORT,
                                   strict=os.environ.get('VERIFY_NUMBERS_STRICT') == '1')
    if _num_issues:
        print('[num-warn] 共 %d 条摘要存在数字未在源文找到，请人工核对' % len(_num_issues))
except Exception as _e:
    print('[verify_numbers] 跳过: %s' % _e)
_new_titles = [item_title(it) for _c, it in new_items]
if _new_titles:
    merge_seq = [x for x in merge_seq
                 if not any(same_event(item_title(x[1]), _t) for _t in _new_titles)]
for _i in range(len(new_items)):
    for _j in range(_i + 1, len(new_items)):
        if same_event(item_title(new_items[_i][1]), item_title(new_items[_j][1])):
            print('[warn] 今日新增内部疑似同事件重复: %s <-> %s'
                  % (item_title(new_items[_i][1])[:40], item_title(new_items[_j][1])[:40]))

arch_groups = render_cat_groups(merge_seq, mark_new=False)
today_groups = render_cat_groups(new_items, mark_new=True)

# ============ 5. 拼装新区 ============
n_today = len(new_items)
arch_n = len(merge_seq)
all_n = n_today + arch_n

new_today_block = ('<!-- ==================== 今日新增（%s 抓取） ==================== -->\n' % GRAB +
                   '<div class="section" id="todaySection">\n'
                   '<div class="section-title today"><span class="icon">🔥</span> 今日新增（%s 抓取）<span class="news-count" id="todayCount">%d条</span></div>\n'
                   % (GRAB, n_today) + ''.join(today_groups) + '</div>\n')

new_arch_block = ('<!-- ==================== 往期内容 ==================== -->\n'
                  '<div class="section" id="archiveSection">\n'
                  '<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近30天）'
                  '<span class="news-count" id="archiveCount">%d条</span></div>\n'
                  '<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n'
                  % arch_n + ''.join(arch_groups) + '</div>\n')

html = html[:m_today] + new_today_block + new_arch_block + html[i_r:]
html = html.replace('<!-- ==================== 今日新增 ==================== -->', '', 1)

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

# ============ 7. div 收支自检（2026-09-11 破损教训） ============
_body = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', '', html)
_open = len(re.findall(r'<div\b', _body))
_close = len(re.findall(r'</div>', _body))
assert _open == _close, 'div 收支不平衡: open=%d close=%d' % (_open, _close)

_buf = html.encode('utf-8')
assert len(_buf) > _ORIG_SIZE * 0.9, 'refuse to write suspiciously small index.html: %d bytes (orig %d)' % (len(_buf), _ORIG_SIZE)
with open(SRC + '.tmp', 'w', encoding='utf-8') as f:
    f.write(html)
os.replace(SRC + '.tmp', SRC)

print('OK index.html -> today=%d archive=%d all=%d size=%d div=%d/%d'
      % (n_today, arch_n, all_n, len(html), _open, _close))
