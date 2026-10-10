# -*- coding: utf-8 -*-
"""
生成 2026-10-10 矿业资讯速览 index.html（周六）
- 10-09 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-11）回补历史条目
- 换入 10-10 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-09 收盘 + LME 10-09 收盘（周末休市），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易），不进主页列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
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

REPORT = '2026-10-10'
GRAB = '2026-10-10'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年10月\d{2}日 星期.',
                         r'\g<1>2026年10月10日 星期六', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104149175-smm-flash-news-q2-metals-extends-cisco-lithium-mineralization-100-m-north-hole-cs26-096-returns-1345-m-120-li2o',
                'SMM 国际站', '10-09',
                'Q2 Metals 魁北克 Cisco 锂矿向北延伸 100 米，单孔见矿 134.5 米',
                'SMM 国际站报道，Q2 Metals 在加拿大魁北克 Cisco 锂矿项目将浅部锂矿化向北延伸 100 米。钻孔 CS26-096 自地表见矿 134.5 米、氧化锂品位 1.20%，其下另见 101.6 米、品位 1.02% 的矿段，且该下部矿段完全位于 2026 年 4 月资源量估算所用概念采坑之外。此前 CS26-095、CS26-094 分别见矿 70 米、品位 1.28% 与 29.2 米、品位 1.53%。公司今夏已完成 43 个孔、19,521 米钻探，5 台钻机将施工至 12 月中旬。',
                orig_title='Q2 Metals extends Cisco lithium mineralization 100 m north, hole CS26-096 returns 134.5 m @ 1.20% Li₂O')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104149229-smm-chromium-flash-zimbabwe-tightens-chrome-export-controls-as-13-mineral-leakage-cases-reach-courts',
                'SMM 国际站', '10-09',
                '津巴布韦收紧铬矿出口管制，13 起锂铬出口违规案进入司法程序',
                'SMM 国际站援引津巴布韦《先驱报》10 月 9 日报道，津巴布韦已将 19 起涉嫌矿产出口违规案件诉至法院，其中 13 起涉及锂与铬。矿业部、津巴布韦矿产销售公司（MMCZ）、税务局与警方正加强协同以收紧出口管制。MMCZ 另披露大岩墙成矿带沿线登记铬洗选厂 33 家、未登记 36 家、在建 10 家，将引入出口货物全成分化验以防低报损失，并把未登记洗选厂纳入规范营销体系。',
                orig_title='[SMM Chromium Flash] Zimbabwe Tightens Chrome Export Controls as 13 Mineral-Leakage Cases Reach Courts')),

    (CAT_ZC, ni('https://news.smm.cn/news/104149180',
                '上海有色网', '10-09',
                '印度取消贵金属进口 IGST 豁免，金银铂进口须缴 3% 税',
                '上海有色网援引金十数据报道，印度政府未延长今年 3 月 31 日到期的贵金属进口 IGST 豁免，自 4 月 1 日起银行和政府指定机构进口黄金、白银及铂金均须按 3% 税率缴纳综合商品与服务税。印度财政部税务秘书什里瓦斯塔瓦周四正式确认这一安排。对全球最大黄金消费市场之一而言，这将增加进口商资金占用与融资成本；符合条件企业可进项抵扣，但进口时须先行缴税。政策核心是统一不同进口渠道税收待遇，而非限制进口。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104149227',
                '上海有色网', '10-09',
                '欧盟将 KGHM 两个铜项目列为战略项目，总值 24.4 亿美元',
                '上海有色网援引文华财经报道，波兰铜生产商 KGHM 表示，欧盟委员会已依《关键原材料法案》（CRMA）将该公司两项重大投资指定为战略项目，两项目总价值 95 亿兹罗提（约 24.4 亿美元）。Retków-Grodziszcze 采矿项目计划到 2055 年开采逾 1 亿吨矿石、产出近 150 万吨铜和逾 5,000 吨白银；KGHM 还将把 Legnica 冶炼厂改造为回收设施，预计年产约 13.5 万吨电解铜和 250 吨镍。指定可提供审批简化、行政协调与优惠融资渠道。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104149248-smm-chromium-flash-south-africas-august-hc-fecr-exports-rise-20-mom-to-117180-mt-led-by-canada-and-us-shipments',
                'SMM 国际站', '10-09',
                '南非 8 月高碳铬铁出口环比增 20% 至 11.72 万吨，加拿大美国接货激增',
                'SMM 国际站报道，南非 2026 年 8 月高碳铬铁出口 11.718 万吨，环比 7 月修正后的 9.7618 万吨增 20.0%、同比增约 45.8%，但仍低于 6 月的 12.331 万吨。加拿大进口由 1,054 吨跃至 26,373 吨成为最大目的地，美国增 128.0% 至 26,029 吨，两国合计占 44.7%。中国降 27.5% 至 20,505 吨、份额由 29.0% 降至 17.5% 退居第四。Merafe 预计重启的 Wonderkop、Boshoek 冶炼厂年底前完成爬产。',
                orig_title="[SMM Chromium Flash] South Africa's August HC FeCr Exports Rise 20% MoM to 117,180 mt")),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104148679-central-bank-gold-rush-39-tonnes-in-august-',
                'SMM 国际站', '10-09',
                '全球央行 8 月净购金 39 吨，中国增持 20 吨居首',
                'SMM 国际站援引 GOLDINVEST 报道，世界黄金协会数据显示，8 月各国央行净购黄金 39 吨，其中中国增持 20 吨居首，乌兹别克斯坦和波兰各增 8 吨；截至 8 月底年内官方购金累计 170 吨。报道指出，央行按多年储备计划配置黄金、对价格不敏感，这解释了在美元走强、美债收益率高企背景下金价仍相对稳定的原因。',
                orig_title='Central bank gold rush: 39 tonnes in August – China leads buying wave')),

    (CAT_SC, ni('https://news.smm.cn/news/104149120',
                '上海有色网', '10-09',
                '包钢股份、北方稀土四季度稀土精矿交易价 38,769 元/吨，环比涨 0.53%',
                '上海有色网报道，北方稀土 10 月 9 日晚公告，根据稀土精矿定价方法及 2026 年三季度稀土氧化物价格，四季度稀土精矿交易价格调整为不含税 38,769 元/吨（干量，REO=50%），REO 每增减 1%、不含税价格增减 775.38 元/吨。该价格较三季度的 38,565 元/吨上涨 204 元/吨、环比涨 0.53%，基本符合市场预期。至此包钢股份与北方稀土的稀土精矿关联交易价格在二季度大幅上调、三季度小幅回落后，四季度重拾升势、整体高位趋稳。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202610/t20261009_10330915.htm',
                '全球矿产资源信息系统', '10-09',
                '周四国际锡价大跌 5.62%，LME 基本金属普跌',
                '全球矿产资源信息系统报道，周四国际原油冲高后回落，有色金属价格普遍下跌，锡价跌幅超过 5%。伦敦金属交易所（LME）锡收于 51,200.00 美元/吨、跌 5.62%；铜 14,293.50 美元/吨、跌 1.00%；铝 3,042.00 美元/吨、跌 2.55%；铅 1,863.00 美元/吨、跌 1.43%；锌 3,707.00 美元/吨、跌 1.46%；镍 15,550.00 美元/吨、跌 1.08%。纽约黄金收于 4,133.1 美元/盎司、涨 0.54%，白银 59.18 美元/盎司、跌 0.96%。')),

    (CAT_SC, ni('https://news.smm.cn/news/104149097',
                '上海有色网', '10-09',
                '节后首周钴产业链弱势运行，钴盐价格持续阴跌',
                '上海有色网周度观察报道，国庆节后钴产业链延续弱势，需求低迷与成本下移共同压制价格。电解钴现货报价持稳于 25.5 万~27 万元/吨、均价 26.25 万元/吨，节后涨幅 0.19%；硫酸钴均价 5.9 万元/吨、较 9 月 30 日跌 2.47%；氯化钴均价 6.85 万元/吨、跌 3.52%；四氧化三钴均价 22.5 万元/吨、跌 5.26%。氯化钴 9 月产量环比明显回落，多家企业扩大减停产，新增采购不足。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474434',
                '中国有色金属报', '10-09',
                '中国铜业复杂锌基资源绿色冶炼技术达到国际领先水平',
                '中国有色金属报报道，经 6 年攻关，由中国铜业所属呼伦贝尔驰宏牵头完成的“多杂难处理锌基物料绿色冶炼与资源高效回收技术及应用”项目通过中国有色金属工业协会组织的科技成果评价，专家组认定整体技术达到国际领先水平。项目联合昆明理工大学、上海交通大学内蒙古研究院等单位，构建以氧压浸出—矿化沉铁为核心的短流程绿色冶炼技术体系，建成国内规模最大的多杂难处理锌基物料绿色冶炼标杆工程，实现年产 14 万吨锌、6 万吨铅，并配套生产硫酸、白银、黄金、精铟及海绵镉、铜精矿、钴精矿等副产品。')),

    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/1009/62130.html',
                '中国有色金属工业协会', '10-09',
                '宝钛集团国产 EB 炉量产 12 吨超大单重纯镍铸锭',
                '中国有色金属工业协会网转载报道，宝钛集团依托下属宝钛装备设计制造公司自主研发的 3150kW 冷阴极电子束冷床炉（EB 炉），实现 12 吨超大单重纯镍铸锭稳定量产，标志国产 EB 炉在大吨位高端纯镍熔炼与规模化量产领域取得实质性突破。纯镍熔点高、熔融态黏度大、高真空下易挥发，大吨位连续熔炼是行业公认难题；此前引进的德国热阴极 EB 炉存在灯丝易损耗、真空波动大等短板。该成果填补国内大单重纯镍量产技术空白，可直接轧制超宽超长整体镍板材、规避拼接焊缝缺陷。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474453',
                '中国有色金属报', '10-09',
                '易控智驾无人驾驶跑通露天煤矿采煤全工艺，逾 600 台无人矿卡投运',
                '中国有色金属报报道，2023 年易控智驾实现行业首个采煤无人驾驶项目落地。截至 2026 年 9 月，公司已有超过 600 台无人矿卡投入采煤生产场景，覆盖新疆、内蒙古等煤炭主产区的 10 余座露天煤矿，应用规模居行业首位，累计采煤运输量超 2 亿吨、运行里程超 2,000 万公里。报道称，与剥离运输相比，采煤运输直接连接工作面与破碎站，对跟随工作面变化、保持运输节奏及与装载卸载环节衔接的可靠性要求更高；在新疆能源石头梅一号露天煤矿，100 台无人矿卡参与采煤作业，部分线路重载上坡约 4 公里。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/rare-earth-recycling-can-bridge-us-supply-gap-as-mines-face-long-timelines-paladin-says',
                'MINING.COM', '10-09',
                'Paladin：稀土回收可弥补美国短期供应缺口',
                'MINING.COM 报道，电子废弃物回收商 Paladin EnviroTech 认为，在美国开发新矿与加工产能尚需时日的背景下，回收报废电子产品、风机等工业设备可为美国提供近期稀土来源。公司正扩大稀土回收业务，以应对美国制造商对海外供应（尤其是高性能永磁所需重稀土）的高度依赖。Paladin 目前稀土产量约 40 吨/年，其俄亥俄州工厂是配图所示设施。',
                orig_title='Rare earth recycling can bridge US supply gap as mines face long timelines, Paladin says')),

    (CAT_GJ, ni('https://www.mining.com/lithium-triangles-vast-resources-face-unsolved-extraction-hurdles',
                'MINING.COM', '10-09',
                '南美“锂三角”资源丰富但提取难题待解',
                'MINING.COM 报道，南美“锂三角”约占全球已探明锂资源的 43%，但卤水化学性质与水资源条件差异令地质禀赋难以转化为新增供应。地质学家 José Cabello 9 月在《安第斯地质》发表的综述，依据科研文献、公司披露与政府报告评估了阿根廷、玻利维亚、智利三国 43 个已评价盐湖的锂潜力。',
                orig_title="Lithium Triangle's vast resources face unsolved extraction hurdles")),

    (CAT_GJ, ni('https://www.mining.com/ivanhoe-copper-output-jumps-19-as-kamoa-kakula-rebounds',
                'MINING.COM', '10-09',
                '艾芬豪三季度铜产量环比增 19%，Kamoa-Kakula 回升',
                'MINING.COM 报道，艾芬豪矿业（TSX: IVN）三季度铜产量合计 76,401 吨，环比增 19%，产量正向 2025 年水平回归。其中位于刚果（金）的 Kamoa-Kakula 共生产 76,401 吨可销售产品铜（含 68,188 吨铜精矿），环比增 11.5%。',
                orig_title='Ivanhoe copper output jumps 19% as Kamoa-Kakula rebounds')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202610/t20261009_10330914.htm',
                '全球矿产资源信息系统', '10-09',
                '阿克拉拉资源扩大稀土元素分离品种至钇、钆、钐',
                '全球矿产资源信息系统援引矿业周刊报道，多伦多上市稀土开发商阿克拉拉资源公司（Aclara Resources）正扩大其美国路易斯安那州拟建稀土分离设施范围，考虑将钇、钆、钐列入分离对象，项目名为 Project Dynamo。该公司原计划仅分离镨钕镝铽四种元素，现已在位于弗吉尼亚州的中试厂加装溶剂萃取单元，并将中试规模与技术支撑人员各扩大一倍。公司称钇在智利彭科项目稀土中占比达 50%、在巴西卡里纳项目中占 30%，AI 与数据中心带动的发电基础设施投资将拉动钇需求。')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104149169-smm-news-zheli-mining-plans-lithium-sulphate-plant-in-zimbabwe-ahead-of-2027-export-ban',
                'SMM 国际站', '10-09',
                'Zheli Mining 拟在津巴布韦建硫酸锂厂，设备 12 月到货',
                'SMM 国际站报道，Zheli Mining 计划在津巴布韦建设硫酸锂厂，设备已发运、预计 12 月抵达，总经理 Kudakwashe Zimondi 在 MMCZ 锂业媒体行中披露。该厂将推动 Zheli 由锂辉石精矿生产向下游锂化学品延伸。其 Zvishavane 厂现有两条产线、合计给料能力约 900 吨/日，满产有望超 1,000 吨/日，原料来自 Mutapa Energy 旗下 Sandawana 锂矿的独家加工协议。津巴布韦政府设定的 2027 年进一步加工期限旨在减少低值锂产品出口。',
                orig_title='[SMM News] Zheli Mining Plans Lithium Sulphate Plant in Zimbabwe Ahead of 2027 Export Ban')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/mcewens-55m-ontario-asset-sale-fuels-gold-growth-plans',
                'MINING.COM', '10-09',
                'McEwen 以 5,500 万美元出售安大略两处非核心金矿资产',
                'MINING.COM 报道，McEwen（TSX: MUX）已同意将安大略两处非核心金矿资产以 5,500 万美元现金加股票出售给 Discovery Mining（TSX: DSV），以将资金转向目标 2030 年实现年产最多 30 万盎司黄金当量的扩产计划。交易包括 Lexam VG Gold 全资的 Fuller 资产、其持有的 Paymaster 60% 权益及 VG Holdings 的一块地表权，均位于蒂明斯矿区 Fox Complex 范围内；Fuller 约 210 公顷，Paymaster 约 179 公顷。',
                orig_title="McEwen's $55M Ontario asset sale fuels gold growth plans")),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104149170-rock-tech-lithium-announces-c596m-preliminary-capital-cost-for-red-rock-converter-in-ontario-canada',
                'SMM 国际站', '10-09',
                'Rock Tech 公布安大略 Red Rock 锂转化厂初步资本开支 5.96 亿加元',
                'SMM 国际站报道，Rock Tech Lithium 10 月 8 日公布其在加拿大安大略省 Red Rock 锂转化厂可行性研究的初步结果：总资本开支 5.96 亿加元（约合人民币 30.6 亿元），其中直接资本开支 5.46 亿加元、业主费用 0.50 亿加元，偏差约 20%；研究基于约 3 万吨/年锂盐产能。该可行性研究由中国中材国际（CEC）承担并将与加拿大伙伴推进本地化，最终报告预计 2026 年底完成，在获批前提下建设拟于 2027 年下半年启动。',
                orig_title='Rock Tech Lithium Announces C$596M Preliminary Capital Cost for Red Rock Converter in Ontario, Canada')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104149172-smm-flash-news-cleantech-lithium-signs-option-agreements-to-acquire-antofalla-lithium-project-in-argentina',
                'SMM 国际站', '10-09',
                'CleanTech Lithium 签署期权协议收购阿根廷 Antofalla 锂项目',
                'SMM 国际站报道，CleanTech Lithium 签署两份期权协议，拟全资收购阿根廷 Salar de Antofalla 南部的 Genoveva 与 Sal de Litio 1 两处资产（合称 Antofalla 项目），距其旗舰 Laguna Verde 项目约 80 公里。交易完成阿根廷律所 Beretta Godoy 尽职调查，采矿许可在满足存续要求下为永久许可。公司将首年分期支付 52.5 万美元，2027 年 10 月至 2031 年 5 月再支付 140 万美元，资金来自现有现金。CEO 称 Salar de Antofalla 是阿根廷最大的未开发盐湖。',
                orig_title='[SMM Flash News] CleanTech Lithium signs option agreements to acquire Antofalla lithium project in Argentina')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104149173-smm-flash-news-elevra-signs-spodumene-concentrate-supply-deal-with-lg-energy-solution-for-canadas-nal-project',
                'SMM 国际站', '10-09',
                'Elevra 与 LG 新能源签署加拿大 NAL 项目锂辉石承购协议',
                'SMM 国际站报道，澳大利亚锂生产商 Elevra 10 月 8 日签署协议，向韩国 LG 新能源（LGES）供应其位于加拿大魁北克 North American Lithium（NAL）项目的锂辉石精矿。协议覆盖三年期 24 万吨（dmt），自预计 2026 年首批发货起算；双方同意时 Elevra 还可额外供应最多 9 万吨。LGES 表示其在北美拥有 5 座独资及合资电池工厂，此举旨在强化北美供应链并满足该地区储能需求。',
                orig_title='[SMM Flash News] Elevra signs spodumene concentrate supply deal with LG Energy Solution for Canada NAL project')),

    (CAT_MA, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474458',
                '中国有色金属报', '10-09',
                '云南富民签约两个钛产业项目，总投资 6.1 亿元',
                '中国有色金属报报道，云南省昆明市富民县近日召开 2026 年钛产业链招商对接会，会上成功签约 2 个钛产业项目，总投资金额达 6.1 亿元。富民县人民政府与昆明滇钛投资有限公司现场签订《富民县散旦镇钛基新材料配套 600 万吨/年钛铁砂矿采选项目》等协议，围绕钛产业延链补链强链、培育特色钛产业集群推进合作。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-10/1225599838.PDF',
                '巨潮资讯网', '10-10',
                '兴业银锡披露要约收购威领股份事项最新进展',
                '巨潮资讯网披露，兴业银锡（内蒙古兴业银锡矿业股份有限公司）发布关于对外投资要约收购威领股份事项的进展公告，就该要约收购的最新推进情况作出说明。')),

    # ── 💼 矿权交易（仅入 rightsSection 数据层，不进主列表） ───
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

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
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
