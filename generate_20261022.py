# -*- coding: utf-8 -*-
"""
生成 2026-10-22 矿业资讯速览 index.html（周四）
- 10-21 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-23）回补历史条目
- 换入 10-22 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-21 收盘 + LME 10-19 收盘（10-22 周四 05:30 未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，本批新增 3 宗（江西临川金山东区铜、云南大姚菜西拉铜、
  江西横峰童湾里石英岩转让），不进主页列表（由 tmp/add_rights_1022.py 注入月库）
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

REPORT = '2026-10-22'
GRAB = '2026-10-22'
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
                         r'\g<1>2026年10月22日 星期四', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/dwdt/202610/t20261021_870778.html',
                '中国地质调查局', '10-21',
                '国内首台套地质钻探智能泥浆系统在秦皇岛完成中试验证',
                '由中国冶金地质总局与中国地质科学院探矿工艺研究所联合研发的国内首台套地质钻探智能泥浆系统在河北秦皇岛完成中试验证。该系统针对地质岩心钻探施工工况定制，集成自动配浆、泥浆性能自动测试、固相控制、废浆处理装备及智能控制平台，可实现「配浆—性能测试—泥浆净化—废浆无害化处理」全流程自动化作业，提升泥浆作业控制精度与钻探绿色施工能力。')),

    (CAT_ZK, ni('https://www.mining.com/endurance-gold-expands-zones-at-reliance-as-pea-work-ongoing',
                'MINING.COM', '10-21',
                'Endurance Gold 不列颠哥伦比亚 Reliance 钻探扩边，金锑矿化并见',
                'Endurance Gold 公布加拿大不列颠哥伦比亚省 Reliance 项目 25 个钻孔、逾 10200 米钻探结果：Imperial 矿带被 DDH26-140 向西北延伸 50 米，见 5.2 米厚、金品位 5.89 克/吨、锑 0.19%；下 Imperial 带被 DDH26-137 向东南延伸 55 米，见 16.2 米厚、金 2.24 克/吨、锑 0.06%。项目现有推断资源 1960 万吨、金品位 2.3 克/吨，含金 145 万盎司，初步经济评价正推进。',
                orig_title='Endurance Gold expands zones at Reliance as PEA work ongoing')),

    (CAT_ZK, ni('https://www.mining.com/spain-hunts-hidden-metals-with-223m-plan',
                'MINING.COM', '10-21',
                '西班牙启动 1.97 亿欧元国家矿产勘查计划，航空物探覆盖 10 万平方公里',
                '西班牙地质与矿业研究所（IGME）宣布数周内启动航空磁法、放射性及重力测量，覆盖 10 万平方公里，涉及中部伊比利亚、奥萨—莫雷纳和南葡萄牙三个地质区。该计划属 2026—2030 年国家矿产勘查计划，估算投资 1.97 亿欧元（约 2.23 亿美元），其中 1.15 亿欧元用于国有矿企 Hunosa 与私营企业作业；重点靶区包括韦尔瓦 San Silvestre（铜及锗镓铟）与萨拉曼卡 Morille（钨锡铌钽锂）。',
                orig_title='Spain hunts hidden metals with $223M plan')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202610/t20261021_2940830.html',
                '自然资源部', '10-21',
                '《矿业权登记管理暂行办法（征求意见稿）》收到意见建议 66 条',
                '自然资源部 10 月 21 日公告，《矿业权登记管理暂行办法（征求意见稿）》于 2026 年 7 月 28 日至 8 月 13 日在该部网站向社会公开征求意见，共收到社会各界意见建议 66 条。该部表示将对 66 条意见建议逐条深入研究，并最大限度采纳相关合理内容。')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/104162853-china-proposes-tighter-solar-technology-export-controls-what-next-for-the-ex-china-region-smm-analysis',
                'SMM 国际站', '10-16',
                '商务部、科技部拟修订禁止限制出口技术目录，涉光伏 12 项技术',
                '10 月 16 日，商务部、科技部公布《禁止出口限制出口技术目录》修订草案，涉多晶硅、硅片、电池制造共 12 项光伏技术及含相关技术的关键核心设备，并自公告日起对相关技术实施临时出口前登记，登记不当然取得出口授权。新增条目公开征求意见至 11 月 15 日；拟禁止类含单线三氯氢硅产能 25 万吨/年以上的冷氢化流化床工艺。',
                orig_title='China Proposes Tighter Solar Technology Export Controls: What Next for the Ex-China Region?')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104171510',
                '上海有色网', '10-21',
                '国家统计局：9 月精炼铜产量 126.00 万吨，同比增 1.10%',
                '国家统计局 10 月 21 日数据显示，9 月精炼铜（电解铜）产量 126.00 万吨、同比增 1.10%，1—9 月累计 1128.20 万吨、同比增 3.30%。9 月氧化铝产量 840.00 万吨、同比增 5.50%，1—9 月 7003.60 万吨、增 3.90%；9 月锌产量 60.70 万吨、同比降 5.50%，铅产量 62.80 万吨、增 0.30%。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261021_10341247.htm',
                '全球矿产资源信息系统', '10-21',
                'ILZSG：2027 年精炼锌转为过剩 2.5 万吨，铅过剩扩至 16.3 万吨',
                '国际铅锌研究小组（ILZSG）报告称，2027 年全球精炼锌市场由今年短缺 8.8 万吨转为过剩 2.5 万吨，精炼铅过剩量由 9 万吨扩大至 16.3 万吨。2027 年精炼锌消费增 1.2% 至 1419 万吨（中国增速由 1.8% 降至 0.3%），产量增 2% 至 1421 万吨、矿山锌增 3% 至 1278 万吨；精炼铅需求增 1% 至 1392 万吨、供应增 1.5% 至 1408 万吨。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474701',
                '中国有色金属报', '10-19',
                'INSG：2026 年全球镍市转为过剩 1.9 万吨，2027 年扩至 7 万吨',
                '国际镍业研究组织（INSG）10 月 13 日会议后报告，2026 年全球原生镍需求约 385 万吨、同比增 7.6%，产量 387 万吨，市场由 4 月预测的短缺 3.2 万吨转为过剩 1.9 万吨；2027 年需求 400 万吨、产量 407 万吨，过剩扩大至 7 万吨。印尼已批准 2026 年镍矿生产配额低于上年，2027 年配额申请截至 11 月 15 日。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474793',
                '中国有色金属报', '10-20',
                '再生铜杆开工率降至 9.35%，精废价差一度归零',
                '节后再生铜杆行业开工率仅 9.35%，精废价差由节前 1250 元/吨压缩，10 月中旬一度降至 0 元/吨。反向开票执行趋严、利废企业检查加密，不含税原料流通基本停滞；含税货源不足、票点突破 15%，8 月再生铜原料进口量环比降 19.04%，企业被迫减产停产，铝代铜产业化进程加快。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/68fad2b035d8413d8a627d567f6151ab.html',
                '长江有色网', '10-21',
                '碳酸锂主力合约跌 4.71% 至 95040 元/吨，电碳均价 10.1 万元/吨',
                '10 月 21 日碳酸锂期货主力合约震荡回落，收跌 4.71%、报 95040 元/吨。现货方面，长江综合 99.5% 电池级碳酸锂均价 101000 元/吨，较上一交易日跌 2000 元；99.2% 工业级均价 98000 元/吨，同跌 2000 元。市场交易重心围绕弱预期与成本支撑博弈。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474691',
                '中国有色金属报', '10-20',
                '中铝郑州研究院铝电解降碳技术突破，全氟化碳排放强度降 77%',
                '中铝郑州研究院牵头的「基于降低全氟化碳排放的铝电解节能降碳技术」取得重大突破，使我国铝电解全氟化碳等效二氧化碳排放强度由 1.12 吨/吨铝降至 0.26 吨/吨铝以下，降幅超 77%。该技术已在全国 20 余家电解铝企业推广、覆盖产能超 600 万吨，吨铝直流电耗平均降低 47 千瓦时以上。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474711',
                '中国有色金属报', '10-19',
                '安宁股份 6 万吨/年能源级钛材料项目产出第一炉海绵钛',
                '四川安宁铁钛股份有限公司投资建设的年产 6 万吨能源级钛（合金）材料全产业链项目近日产出第一炉海绵钛，单炉产量约 13 吨，产品质量达到设计要求，项目已进入试生产阶段。下一步公司将优化工艺、逐步释放产能。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474690',
                '中国有色金属报', '10-20',
                '新疆有色大红柳滩冶炼项目一期二阶段开工',
                '9 月 27 日，新疆有色集团大红柳滩冶炼项目一期二阶段开工仪式在洛浦县昆冈产业园区举行。项目由新疆昆仑蓝钻矿业开发有限责任公司实施，将实现本地锂资源就地深加工转化，完善南疆新能源产业链条，是集团冲刺千亿元产值目标的重要支撑。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474794',
                '中国有色金属报', '10-21',
                '中国有色集团出席哈萨克斯坦阿克托盖 30 万吨/年铜冶炼厂项目启动',
                '当地时间 10 月 20 日，中国有色集团董事长文岗在阿斯塔纳拜会哈萨克斯坦总统托卡耶夫，并受邀出席阿克托盖 30 万吨/年铜冶炼厂项目筹备启动仪式。该项目由哈萨克矿业集团（KAZ Minerals）投资。中国有色集团深耕哈萨克斯坦 20 余年，已建成哈首座电解铝厂及巴夏库、阿克托盖铜矿选厂等工程。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474759',
                '中国有色金属报', '10-20',
                '一汽研发总院攻克镁合金电机壳体加工难题，单套降重 10 公斤',
                '一汽研发总院智铣青年突击队完成镁合金电机壳体阶段性攻关，单套壳体降重 10 公斤、核心指标达成率 100%。团队采用「大前角锋利刀具+高转速小切深」方案并自研工装，将加工变形量降低 60%、精度稳定在 0.008 毫米以内，已完成 4 类镁合金产品试制并实现电机总成装配。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/hudbay-mitsubishi-approve-copper-world-construction',
                'MINING.COM', '10-21',
                'Hudbay 与三菱批准 21 亿美元 Copper World 铜矿建设，2029 年投产',
                'Hudbay Minerals 与日本三菱批准美国亚利桑那州 Copper World 铜矿建设，初始投资 21 亿美元，较 2023 年预可研的 13 亿美元增加 59%（范围调整带来 2 亿美元增量）。按铜价 5 美元/磅、8% 折现率测算，项目税后净现值 12 亿美元、内部收益率 17%；投产前十年年均产铜 10.2 万吨，计划 2029 年下半年首次产出。三菱持股 30%、Hudbay 70%。',
                orig_title='Hudbay, Mitsubishi approve Copper World construction')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-21/1225612361.PDF',
                '巨潮资讯网', '10-21',
                '海南矿业前三季度预盈 6 亿至 7 亿元，同比增 92.31% 至 124.36%',
                '海南矿业业绩预增公告：预计 2026 年前三季度归母净利润 6 亿元至 7 亿元，同比增加 2.88 亿元至 3.88 亿元、增幅 92.31% 至 124.36%；扣非净利 5 亿元至 6 亿元。主因锂资源板块三季度产量环比增逾 24%、销量增逾 33%，电池级氢氧化锂价格同比涨 116%，叠加布伦特油价同比涨约 33%。',
                embed='pdf')),

    (CAT_MA, ni('https://news.smm.cn/news/104171411',
                '上海有色网', '10-21',
                '西部矿业前三季度净利 67.89 亿元，同比增 130.5%',
                '西部矿业三季报显示，2026 年前三季度营业收入 597.88 亿元、同比增 23.42%，归母净利润 67.89 亿元、同比增 130.5%；第三季度营收 203.45 亿元、增 20.94%，归母净利润 26.2 亿元、增 143.48%。公司称增长主要系铜、锌及其含金、含银产品价格较上年同期上涨。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-20/1225611067.PDF',
                '巨潮资讯网', '10-20',
                '湖南裕能拟投不超 20 亿元建六期磷酸铁锂项目，建设期 12 个月',
                '湖南裕能 10 月 19 日董事会审议通过投资建设六期磷酸铁锂项目，投资总额不超过 20 亿元、资金来源为企业自筹。项目位于湘潭市雨湖区鹤岭镇，总建筑面积约 8 万平方米，建设期 12 个月，将购置磷酸铁锂成套生产线设备，进一步完善磷酸铁锂产能布局。',
                embed='pdf')),

    (CAT_MA, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474568',
                '中国有色金属报', '10-13',
                '广东鸿图设立全资子公司推进镁合金压铸产能建设',
                '广东鸿图 10 月 9 日公告，拟在肇庆市高要区设立全资子公司广东鸿镁新材料技术有限公司，作为镁合金压铸项目实施主体，采取「厂房租赁、设备产线自投」模式。拟租赁厂房面积约 16130.25 平方米、租赁期 12 年，租赁期内租金总额预计不超过 3800 万元。')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/brazil-court-halts-belo-suns-300m-gold-project',
                'MINING.COM', '10-21',
                '巴西最高法院暂停 Belo Sun 3 亿美元 Volta Grande 金矿安装许可',
                '巴西联邦最高法院部分准许联邦公共检察署请求，暂停恢复 Belo Sun 帕拉州 Volta Grande 金矿（投资 3 亿美元）安装许可的裁定，直至其与巴西国家印第安人基金会（Funai）的和解协议获司法批准。该项目探明加概略储量约 380 万盎司黄金，原规划 17 年矿山寿命、年均产金约 20.5 万盎司。',
                orig_title='Brazil court halts Belo Sun’s $300M gold project')),

    (CAT_GJ, ni('https://www.mining.com/chiles-rare-earth-ambitions-hit-refining-bottleneck',
                'MINING.COM', '10-21',
                '智利稀土受制于分离精炼短板，海外加工成本高 20%~150%',
                'GEM Mining Consulting 报告指出，智利虽有稀土采矿与金属化项目——Aclara 与 CAP 合资的 Huachipato 示范厂 10 月 7 日投产、日产能最高 175 公斤金属，但缺乏工业级分离与磁体制造能力。中国占全球稀土分离精炼 91%、永磁体制造 94%；中国以外建厂资本成本高出 20% 至 150%，运营成本高约 50%。',
                orig_title='Chile’s rare earth ambitions hit refining bottleneck')),

    (CAT_GJ, ni('https://www.mining.com/mauritanias-first-uranium-mine-comes-into-view-despite-funding-security-issues',
                'MINING.COM', '10-20',
                'Aura Energy 毛里塔尼亚 Tiris 铀矿可研估值 5 亿美元，2028 年底投产',
                'Aura Energy 公布毛里塔尼亚 Tiris 铀矿银行级可研：项目估值 5 亿美元，建设成本增至 3.5 亿美元（增 52%），税后内部收益率 28%，铀价假设上调 12% 至 90 美元/磅；储量增至 3730 万磅氧化铀、品位 227ppm，26 年矿山寿命产铀 4610 万磅。公司尚需落实约 4 亿美元开发资金，计划 12 月作出最终投资决定、2028 年底首次产出。',
                orig_title='Mauritania’s first uranium mine comes into view despite funding, security issues')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202610/t20261021_10341249.htm',
                '全球矿产资源信息系统', '10-21',
                'FT 矿业峰会：政府深度介入关键矿产，西方重建加工链仍困难',
                '在伦敦举行的《金融时报》金属与矿业峰会上，与会者认为政府已从监管者变为投资方，美国国防部已承诺为关键矿产提供约 1000 亿美元。但稀土供应链集中格局短期难改，Ionic Rare Earths 董事卢瑟福表示，西方矿企把资金投向矿业上游合理，发展下游加工需要政府前所未有的协调与资源投入。')),

    (CAT_GJ, ni('https://www.mining.com/mining-industry-entering-largest-investment-supercycle-in-history-canadas-energy-minister-says',
                'MINING.COM', '10-20',
                '加拿大能源部长：全球矿业正进入史上最大投资超级周期',
                '加拿大能源与自然资源部长霍奇森（Tim Hodgson）在伦敦表示，全球正进入「金属与矿业史上最大的投资超级周期」，关键矿产已不再是普通工业商品，而是决定各经济体能否增长与竞争的投入品。加方 9 月提出 240 页《建设加拿大强大法案》，拟将重大项目审批压缩至由单一联邦机构在一年内完成。',
                orig_title='Mining industry entering largest investment supercycle in history, Canada’s energy minister says')),
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
