# -*- coding: utf-8 -*-
"""
生成 2026-11-10 矿业资讯速览 index.html（周二）
- 11-09 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-12）回补历史条目
- 换入 11-10 采集的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-09 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：11-10 无新增出让/成交公告（自然资源部最新为 11-07），
  #rightsCards 沿用既有窗口数据，不进主列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""

import re, datetime, json, glob, os
import sys
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

REPORT = '2026-11-10'
GRAB = '2026-11-10'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年11月\d{2}日 星期.',
                         r'\g<1>2026年11月10日 星期二', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-\d{2}-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-\d{2}-\d{2} 更新',
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
for _fn in sorted(glob.glob('data/news_????-??.json')):
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

# 2026-10-29 一次性清理：chinania.org.cn 源已禁用且死链已从月库/前端库清除，
# 但现有 index.html 往期区仍残留其卡片（arch_keep 继承自旧 html），
# 此处统一剔除，确保重生成的 index.html 不再渲染该死链。
merge_seq = [(c, it) for c, it in merge_seq if 'chinania.org.cn' not in it]

merge_seq = dedup_same_event(merge_seq)

# ============ 3.5 从累计库回补 30 天窗口 ============
CAT_MAP = dict(LEGACY_BUCKET)
CAT_MAP.update(THEME_BUCKET)
LIB_SKIP = {'矿权交易', '并购与投资'}
_lib_item = partial(_lib_item_raw, cat_map=CAT_MAP)

_lib_pool = []
for _fn in sorted(glob.glob('data/news_????-??.json')):
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
    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/HBTIS4NMHB4TKVZ3QVPQZAUBI52AKHB2DX7OIWA',
                '上海有色网', '11-09',
                '沪铜周度库存降逾两成，创 2024 年以来新低',
                '上期所数据显示，11 月 6 日当周沪铜库存减少 24.13% 至 33,848 吨，创 2024 年以来新低；国际铜库存持稳于 9,526 吨。LME 铜库存 11 月 5 日增至四个月新高 318,675 吨后回落至 316,675 吨，纽铜库存升至 807,930 短吨。')),

    (CAT_SC, ni('https://news.smm.cn/news/63EQBNXSCVEQZ5CCJVILLB5FX6VLNQD2DXHQZCY',
                '上海有色网', '11-09',
                '道明证券：铜价或再跌 500 美元/吨，美国囤货支撑或消退',
                '道明证券认为，民主党掌控国会后美国精炼铜关税落地概率下降，叠加 AI 数据中心铜需求预估存疑，铜价仍有下行压力，再跌 500 美元/吨并不意外；该行估算美国铜库存约 160 万吨。BMI 预测今年铜均价 13,500 美元/吨、2027 年 12,900 美元/吨。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/S74UGXSFXUCSZE6FCV6INV6AASHJM3GE3IS26AY-citigroup-slashes-lithium-price-forecasts-amid-slowing-battery-demand-and-rising-supply-concerns',
                'SMM 国际站', '11-09',
                '花旗下调锂价预测，碳酸锂 3 个月目标降至 12,000 美元/吨',
                '花旗将碳酸锂、氢氧化锂 3 个月目标价由 20,000、17,000 美元/吨下调至 12,000 美元/吨，锂辉石由 2,000 美元/吨降至 1,200 美元/吨，并下调至 2028 年底各期预测；该行称 2027 年需求走弱构成「锂价重置」。',
                orig_title='Citigroup Slashes Lithium Price Forecasts Amid Slowing Battery Demand and Rising Supply Concerns')),

    (CAT_SC, ni('https://news.smm.cn/news/KVJ4MXJLNUKB4JSTBWQOHIISUXL2ATZJ45SEWMY',
                '上海有色网', '11-09',
                '中国央行 10 月增持黄金 83 万盎司，连续 24 个月',
                '11 月 7 日数据显示，中国 10 月末黄金储备 7,830 万盎司，较 9 月末增加 83 万盎司，连续 24 个月增持；受金价回落影响，黄金储备估值降至 3,064.11 亿美元，缩水约 171 亿美元。10 月外汇储备 34,051.78 亿美元。')),

    (CAT_SC, ni('https://www.mining.com/copper-price-bounces-after-worst-week-since-march-amid-scramble-for-metal-in-china',
                'MINING.COM', '11-10',
                '铜价反弹，洋山铜溢价升至 230 美元/吨纪录高位',
                '11 月 9 日，洋山铜溢价升至每吨 230 美元的纪录高位，上海现货升水两周内翻三倍，上期所可交割库存已不足中国一日消费量；铜价上周创 3 月以来最大单周跌幅后出现反弹。',
                orig_title='Copper price bounces after worst week since March amid scramble for metal in China')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/4MYV2QQJE4RQNAZWXRN5LMXPFRABVQI3K2VKOQY',
                '上海有色网', '11-09',
                '广期所发布氢氧化锂期货、期权合约及业务细则',
                '11 月 6 日，广期所公告〔2026〕66 号发布《氢氧化锂期货合约》《氢氧化锂期权合约》及期货期权业务细则，经董事会审议通过并报中国证监会，自发布之日起实施；上市交易时间及有关事项另行通知。')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/NLVLFB5I5E63LDWBVRAOCQDSPYUIVDYQLPVVYZA-zimbabwe-maintains-jan-2027-deadline-for-lithium-sulphate-only-exports-rejects-extension-requests',
                'SMM 国际站', '11-09',
                '津巴布韦维持 2027 年 1 月锂硫酸盐出口期限，驳回延期请求',
                '津巴布韦矿业部 11 月 9 日决定维持 2027 年 1 月选矿期限，届时仅允许出口硫酸锂，要求 Bikita、Kamativi 与 Gwanda 工厂尽快投产；生产商曾申请延至 2027 年 6 月，锂生产商协会称七家主要生产商中仅一家建成硫酸锂厂。',
                orig_title='Zimbabwe Maintains Jan 2027 Deadline for Lithium Sulphate-Only Exports, Rejects Extension Requests')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475281',
                '中国有色金属报', '11-09',
                '欧盟新一批 46 个战略原材料项目直面投产考验',
                '欧盟委员会 10 月公布新一批 46 个战略性原材料项目，覆盖 16 个成员国铜、锂、镍、钴、石墨、稀土等矿种，预计需约 211 亿欧元资本投入，已动员公共资金超 20 亿欧元；战略身份只带来审批提速，不附自动拨款。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/HC4QXJLSPEXRL7EOYBYILSMDGGWPVHAEAINGXDY-india-approves-29652m-scheme-to-boost-domestic-lithium-nickel-processing-capacity',
                'SMM 国际站', '11-06',
                '印度批准 2.9652 亿美元计划，建设本土锂镍加工产能',
                '印度批准 2,814 crore 卢比（296.52 百万美元）计划，用于建立本土锂、镍加工产能，降低关键矿产进口依赖。',
                orig_title='India Approves $296.52M Scheme to Boost Domestic Lithium, Nickel Processing Capacity')),

    (CAT_GJ, ni('https://www.mining.com/igos-nova-nickel-mine-bows-out-with-production-beat',
                'MINING.COM', '11-09',
                'IGO 的 Nova 镍矿停产谢幕，三种金属产量均超指引',
                'IGO 位于西澳的 Nova 镍矿完成最后阶段生产并关闭，停产前镍、铜、钴产量均超指引；该矿区将改造为锂加工设施。',
                orig_title='IGO’s Nova nickel mine bows out with production beat')),

    (CAT_GJ, ni('https://www.mining.com/codelco-pucobre-clear-key-hurdle-for-870-million-copper-mine',
                'MINING.COM', '11-09',
                'Codelco 与 Pucobre 打通 8.7 亿美元铜矿关键审批',
                '智利国家铜业与 Pucobre 的合资铜矿项目通过关键审批环节，项目投资 8.7 亿美元，计划 2027 年开工建设，配套太阳能供电与海水供水系统。',
                orig_title='Codelco, Pucobre clear key hurdle for $870 million copper mine')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://news.metal.com/newscontent/6UODXYMN4YRCRIEGBAOL4LC6X6ACDIVSFGOAAIQ-smm-news-brunswick-exploration-drills-302m-173-li2o-at-anais-dyke-in-qu',
                'SMM 国际站', '11-09',
                'Brunswick 魁北克 Anais 岩脉见 302 米、1.73% 锂品位',
                'Brunswick Exploration 公布魁北克 Anatacau Main 项目 Anais 岩脉 AN-26-17 孔，自 295.25 米见矿 302.05 米、品位 1.73% 氧化锂，其中自 426 米起 142 米品位 1.97%；真厚度按视厚度 80% 估算。',
                orig_title='Brunswick Exploration Drills 302m @ 1.73% Li₂O at Anais Dyke in Québec')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475267',
                '中国有色金属报', '11-09',
                '中国铜业普朗矿区首次发现矽卡岩型铜铁-金-钨矿体',
                '10 月 27 日，云南铜业、迪庆有色联合昆明理工大学、中国地质科学院矿产资源研究所、中铝勘查等单位，在普朗矿区首次发现矽卡岩型铜铁-金-钨矿体，证实斑岩矿体外围具备找金潜力，拓宽矿区找矿空间。')),

    (CAT_ZK, ni('https://www.mining.com/american-rare-earths-begins-testing-us-rare-earth-metal-production',
                'MINING.COM', '11-09',
                'American Rare Earths 启动美国稀土金属连续化中试',
                'American Rare Earths 将怀俄明州 Halleck Creek 矿石投入连续化加工试验，以推进本土稀土金属与磁材供应链建设。',
                orig_title='American Rare Earths begins testing US rare earth metal production')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.metal.com/newscontent/N4PPNBMQAKNRQI6FHKH26HFJGXDCPMZDF67IRRI-smm-news-eramet-in-talks-to-sell-stakes-in-argentina-lithium-and-indonesia-nickel-operations',
                'SMM 国际站', '11-09',
                'Eramet 洽谈出售阿根廷锂与印尼镍业务股权',
                'Eramet 11 月 9 日表示，正洽谈出售阿根廷锂与印尼镍业务少数股权以改善财务，已有多家伙伴对 Centenario 锂项目少数股权表达兴趣；公司同意以 7,100 万美元出售阿根廷 Arizaro 盐湖未开发矿权，预计年底交割。Centenario 现有产能 2.4 万吨/年碳酸锂当量，长期潜力 15 万吨/年。',
                orig_title='Eramet in talks to sell stakes in Argentina lithium and Indonesia nickel operations')),

    (CAT_MA, ni('https://news.metal.com/newscontent/52DMTV2GIITMKB5OX4OLUBNWXB2S5DVCTRY4XTA-critical-metals-acquires-european-lithium-gains-full-control-of-wolfsberg-lithium-project',
                'SMM 国际站', '11-09',
                'Critical Metals 完成收购 European Lithium',
                'Critical Metals 11 月 6 日完成对 European Lithium 的收购，后者成为其全资子公司，公司由此完全掌控奥地利 Wolfsberg 锂项目。',
                orig_title='Critical Metals Acquires European Lithium, Gains Full Control of Wolfsberg Lithium Project')),

    (CAT_MA, ni('https://www.mining.com/meridian-weighs-400-million-investment-decision-for-cabacal-mine',
                'MINING.COM', '11-10',
                'Meridian 评估 4 亿美元 Cabaçal 铜金矿投资决策',
                'Meridian 为其巴西 Cabaçal 铜金矿已收到二十多份融资方案，正评估约 4 亿美元的建设投资决策。',
                orig_title='Meridian weighs $400 million investment decision for Cabaçal mine')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-07/1225662666.PDF',
                '巨潮资讯网', '11-07',
                '中铝国际拟签几内亚 120 万吨氧化铝项目 EPC，金额约 65.5557 亿元',
                '11 月 6 日，中铝国际董事会审议通过，拟与中铝几内亚签署几内亚 120 万吨氧化铝项目 EPC 总承包合同，合同总金额约 65.5557 亿元，负责氧化铝生产线及配套设施的设计、采购与施工；交易构成关联交易，尚需股东会批准。',
                embed='pdf')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://news.metal.com/newscontent/UDG2CNX5UISWNKNAAWSXIN4IELP6PRB4STJQHQI-greenwing-atana-eye-binding-deal-for-san-jorge-lithium-project-800k-investment-path-to-375-stake-set',
                'SMM 国际站', '11-09',
                'Greenwing 与 Atana 就阿根廷 San Jorge 锂盐湖签约束性协议',
                'Greenwing Resources 计划 3 个月内与 Atana Elements 就阿根廷 San Jorge 锂盐湖项目签署约束性文件：Atana 出资 80 万美元入股，累计投入约 1,530 万美元可获最多 37.5% 权益，预可研后有权以 1.25 亿美元收购剩余 62.5%；项目初始资源量 107 万吨碳酸锂当量、锂浓度 195mg/L。',
                orig_title='Greenwing, Atana Eye Binding Deal for San Jorge Lithium Project; $800K Investment, Path to 37.5% Stake Set')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475262',
                '中国有色金属报', '11-09',
                '中国铝业前三季度利润总额 387.28 亿元，同比增 86.44%',
                '中国铝业 2026 年前三季度营业收入 1,865.94 亿元、同比增 5.69%，利润总额 387.28 亿元、同比增 86.44%，归母净利润 179.16 亿元、同比增 64.83%，经营性现金流 409.92 亿元；自有矿石产量同比提高 31.97%，设备综合运转率 97.75%。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475270',
                '中国有色金属报', '11-09',
                '榆林新材料试制 3102 牌号铝合金铸轧带材',
                '榆林新材料集团试制出 6.0×1260 毫米规格 3102 牌号铝合金铸轧带材，该牌号以锰元素强化，具防锈、成型与焊接性能，用于换热器、散热构件与装饰板材，丰富了企业铝基新材料产品谱系。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475283',
                '中国有色金属报', '11-09',
                '地勘行业谋篇「十五五」，新疆三年发现中型以上矿床 184 处',
                '10 月 28—29 日，第二十一届全国地质勘查行业改革与发展大会在西安召开；新疆 2023—2025 年实施地质勘查项目 1,410 个，发现评价中型以上矿床 184 处，大型资源基地由 13 个增至 18 个；广西「十四五」以来新探获大中型矿床 153 处。')),
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

# —— 分桶 PIN（按内容口径：勘查成果属 🔍、政策属 📜、企业事故/产能属 🏭，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('沪铜', CAT_SC),
    ('道明证券', CAT_SC),
    ('花旗', CAT_SC),
    ('央行', CAT_SC),
    ('洋山铜溢价', CAT_SC),
    ('广期所', CAT_ZC),
    ('津巴布韦', CAT_ZC),
    ('欧盟', CAT_GJ),
    ('印度', CAT_GJ),
    ('Nova', CAT_GJ),
    ('Codelco', CAT_GJ),
    ('Brunswick', CAT_ZK),
    ('普朗', CAT_ZK),
    ('American Rare Earths', CAT_ZK),
    ('Eramet', CAT_MA),
    ('Critical Metals', CAT_MA),
    ('Meridian', CAT_MA),
    ('中铝国际', CAT_MA),
    ('Greenwing', CAT_KQ),
    ('利润总额', CAT_HY),
    ('榆林新材料', CAT_HY),
    ('地勘行业', CAT_HY),
]


def _pin_cat(title, cat):
    for _kw, _c in _PIN_CAT:
        if _kw in (title or ''):
            return _c
    return cat


new_items = [(_pin_cat(item_title(_it), _c), _it) for _c, _it in new_items]

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
# 2026-10-25 A03：严格模式下校验失败/校验器故障必须非零退出、不写正式产物
# （旧实现吞异常后继续 → strict 守门形同虚设）。分类见 generate_site.py 同段注释。
_STRICT_NUM = os.environ.get('VERIFY_NUMBERS_STRICT') == '1'
try:
    from verify_numbers import verify_new_items
    _num_issues = verify_new_items(new_items, REPORT, strict=_STRICT_NUM)
    if _num_issues:
        print('[num-warn] 共 %d 条摘要存在数字未在源文找到，请人工核对' % len(_num_issues))
except AssertionError as _e:
    if _STRICT_NUM:
        print('[verify_numbers] 严格模式：数字落地校验未通过，终止生成（不写 index.html）：%s' % _e)
        sys.exit(1)
    print('[num-warn] %s' % _e)
except Exception as _e:
    if _STRICT_NUM:
        print('[verify_numbers] 严格模式：数字校验器故障，终止生成（不写 index.html）：%s' % _e)
        sys.exit(1)
    print('[verify_numbers] 警告：数字校验未执行（工具故障）：%s' % _e)
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

# ============ 7. div 收支自检 ============
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
