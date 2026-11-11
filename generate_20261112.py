# -*- coding: utf-8 -*-
"""
生成 2026-11-12 矿业资讯速览 index.html（周四）
- 11-11 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-14）回补历史条目
- 换入 11-12 采集的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-11 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：今日新增公告走 #rightsCards 既有窗口，不进主列表
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

REPORT = '2026-11-12'
GRAB = '2026-11-12'
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
                         r'\g<1>2026年11月12日 星期四', html)
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
    (CAT_SC, ni('https://news.smm.cn/news/43ANZYYC5VK5LP3QHYBVKF2XK24XXGX24Q7FNII',
                '上海有色网', '11-11',
                '沪铝库存降至年内新低，LME 铝库存较年初降逾五成',
                '上期所数据显示，11 月 6 日当周沪铝库存连降二十一周，周度减少 30.58% 至 132,605 吨，创年内新低；LME 铝库存降至 226,850 吨，较年初降逾五成，俄产铝在可交割库存中占比继续上升。')),

    (CAT_SC, ni('https://news.smm.cn/news/HU46JDL6IY7CAA3D24SCC6NW3RQQOJK7DJTK6JA',
                '上海有色网', '11-06',
                '高盛下调金价目标：2026 年底 4,150 美元、2027 年底 4,800 美元',
                '高盛 11 月 5 日报告把 2026 年底金价目标由 4,650 美元/盎司下调至 4,150 美元、2027 年底由 5,400 美元下调至 4,800 美元，主因美联储 12 月加息预期压制投资需求；仍预计 2026—2027 年央行月均购金 60 吨。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX006/202611/b12480e5cbff4b62b8cf843a3534dcee.html',
                '长江有色网', '11-11',
                '锂电出口管制阶段性暂停，电池与正负极材料办证要求放宽',
                '商务部、海关总署 11 月 9 日公告，自 11 月 11 日至 2027 年 1 月 10 日暂停实施 2025 年第 55、56、57、58 号及第 61、62 号公告；其中第 58 号涉及锂电池、正极材料、石墨负极材料及配套设备与技术的出口管制。')),

    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX018/202611/69f8e62c143249feacce8f74767c657e.html',
                '长江有色网', '11-11',
                '广期所微调多晶硅、碳酸锂合约手续费与下单限额',
                '广州期货交易所 11 月 11 日公告，对多晶硅 PS2711、碳酸锂 LC2711 合约的交易手续费标准与下单限额作出微调；当日长江综合多晶硅均价 40,750 元/吨持平，电池级碳酸锂均价 90,500 元/吨、日内跌 500 元。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202611/t20261111_872410.html',
                '中国地质调查局', '11-11',
                '中意共建深地科学联合实验室启动首批 6 项合作基金',
                '11 月 7 日深部探测与亚洲四维地形国际研讨会期间，中国地质科学院与意大利帕多瓦大学共建的深地科学联合实验室启动首批 6 项合作研究基金项目，聚焦高温高压矿物物性、成矿过程及其动力学机制、地幔—地壳相互作用等方向。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202611/t20261111_10360829.htm',
                '全球矿产资源信息系统', '11-11',
                '卡梅尔堡稀土矿「岩石到混合稀土碳酸盐」工艺通过测试',
                '南非 CM 方案冶金实验室验证阿尔多罗资源卡梅尔堡项目工艺，可从矿石中提取品位 76%至78% 的混合稀土碳酸盐及品位 80% 的碳酸锶；该项目资源量 8.04 亿吨、TREO 当量品位 2.9%，规模大于芒廷帕斯。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261111_10360830.htm',
                '全球矿产资源信息系统', '11-11',
                '美洲稀土公司开始小批量加工豪莱克溪矿石',
                '澳交所上市的美洲稀土公司（ARE）已在美国诺维克斯公司设施小规模加工怀俄明州豪莱克溪矿石，生产镨钕氧化物并后续制备稀土金属；试验由全资子公司怀俄明稀土公司执行，目标是制备一块重 200 克的钕镨金属锭。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475267',
                '中国有色金属报', '11-09',
                '中国铜业普朗矿区首次发现矽卡岩型铜铁-金-钨矿体',
                '中国铜业所属云南铜业、迪庆有色联合昆明理工大学、中国地质科学院矿产资源研究所、中铝勘查等单位，依托深地国家科技重大专项在普朗矿区首次发现矽卡岩型铜铁-金-钨矿体，证实斑岩矿体外围具备找金潜力，开辟新的勘查方向。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/6PDHDXYSNR5DW542KHQXEFICFF5YLFDG6SD7QQY',
                '上海有色网', '11-11',
                '津巴布韦维持 2027 年 1 月锂精矿出口禁令',
                '津巴布韦矿业和矿业发展部长 Polite Kambamura 表示，政府维持 2027 年 1 月起只出口硫酸锂的期限，未给锂精矿出口留延期空间；生产商曾主张需到 2027 年 6 月才能建成当地加工设施。')),

    (CAT_GJ, ni('https://news.smm.cn/news/4WVJ6PIS2KZUG62PBTYH3B2F5S7FB2MUJ23F64A',
                '上海有色网', '11-11',
                '住友金属下调 2026 财年净利预期 26%，菲律宾镍资产计提减值',
                '住友金属矿山把 2026 财年净利润预期下调 26% 至 1,610 亿日元（约 10 亿美元），因菲律宾 Coral Bay Nickel 计提 426 亿日元减值、该资产计划 2028—2030 财年停产；年精炼铜产量指引下调至约 40 万吨。')),

    (CAT_GJ, ni('https://news.smm.cn/news/VUUKEWTCKGYRTZJJJYJDRS7IMHBZGEIRWJPNGHQ',
                '上海有色网', '11-11',
                '巴林铝业三季度销量环比降 26%，产量回升 38%',
                '巴林铝业（Alba）三季度铝产品销量 207,430 吨、环比降 26%，产量回升至 214,192 吨、环比增 38%；前三季度销量 800,792 吨、同比降 33%，三季度净利润 1,850 万巴林第纳尔（约 4,905 万美元）、同比降 72.5%。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261111_10360828.htm',
                '全球矿产资源信息系统', '11-11',
                '刚果（金）敦促美国把战略矿产协议转为实际投资',
                '刚果（金）经济部长穆科科·桑巴在巴黎联合指导委员会会议后表示，衡量美刚战略矿产伙伴关系成功与否的标准是落地项目而非协议本身；双方联合声明称美国私企兴趣上升、项目链在扩大，但未出现新的投资承诺。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/ZBHOCKSKYZYXXPN3LJU4OZZBIWDPS4XGJQOXE7Y-milestone-simandou-north-mine-project-fully-completed-and-put-into-production',
                'SMM 国际站', '11-11',
                '西芒杜北段矿山-铁路-港口全产业链建成投产',
                '宝武西芒杜矿山第二系列 CS 区下坡输送系统全线重载试运行一次成功，标志北段项目矿山、铁路、港口全产业链建成投产，由生产建设期转入生产运营期。',
                orig_title='Milestone! Simandou North Mine Project Fully Completed and Put into Production!')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/MUVG367DM3RKPTXKFQ22HQVXPSL4TRIUIIDBJIA-flash-highland-valley-strike-reaches-vancouver-port-picket-lines-deepening-molybdenum-logistics-risk',
                'SMM 国际站', '11-11',
                'Highland Valley 罢工波及温哥华港，钼物流风险升级',
                '据当地媒体 11 月 9 日报道，支持 Highland Valley 铜矿罢工工人的纠察线已出现在温哥华港，覆盖该矿铜精矿、钼精矿等产品；工会称正阻止相关物料外运，但尚无具体码头、钼精矿货载或装运延迟得到确认。',
                orig_title='Flash: Highland Valley Strike Reaches Vancouver Port Picket Lines, Deepening Molybdenum Logistics Risk')),

    (CAT_GJ, ni('https://www.mining.com/usa-rare-earth-begins-brazil-shipments-to-pentagon',
                'MINING.COM', '11-11',
                'USA Rare Earth 首次向美国国防部专设实体发运巴西稀土',
                'USA Rare Earth（USAR）已从巴西 Serra Verde 的 Pela Ema 矿山向美国国防部资助的专设实体 US SIIE LLC 发运混合稀土碳酸盐，10 月启动商业规模发运、首批销售定于本月，属 15 年期 100% 包销协议；协议为钕镨设 110 美元/公斤、镝 575 美元/公斤、铽 2,050 美元/公斤底价。',
                orig_title='USA Rare Earth begins Brazil shipments to Pentagon')),

    (CAT_GJ, ni('https://www.mining.com/lithium-americas-flagship-thacker-pass-costs-jump-31',
                'MINING.COM', '11-11',
                'Thacker Pass 一期成本上调 31% 至 38.3 亿美元',
                'Lithium Americas 把内华达州 Thacker Pass 锂项目一期成本上调 31% 至 38.3 亿美元，资本开支增加 8.95 亿美元、资金需求增加约 9.95 亿美元；2026 年一期支出指引升至 17 亿—20 亿美元，仍维持 2028 年投产、满产年产 4 万吨电池级碳酸锂。',
                orig_title='Lithium Americas flagship Thacker Pass costs jump 31%')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/altius-to-buy-tnr-gold-in-86-million-royalty-deal',
                'MINING.COM', '11-11',
                'Altius 以 1.22 亿加元收购 TNR Gold，增持阿根廷铜锂权益金',
                'Altius Minerals 同意以 1.22 亿加元（8,600 万美元）收购 TNR Gold，取得阿根廷 Los Azules 铜矿 0.36% 净冶炼收益权益金与赣锋 Mariana 盐湖项目 1.35% 权益金，并把阿拉斯加 Shotgun 金矿分拆给原股东；对价较 TNR 前收盘溢价 60%。',
                orig_title='Altius to buy TNR Gold in $86-million royalty deal')),

    (CAT_MA, ni('https://www.mining.com/evermetal-acquires-uk-critical-metals-recycler-advanced-alloys',
                'MINING.COM', '11-11',
                'EverMetal 收购英国关键金属回收商 Advanced Alloys',
                'EverMetal Holdings 收购英国谢菲尔德的关键金属回收商 Advanced Alloys，交易金额未披露；标的处理镍、钴及钨、钽、铌等特种金属与超级合金车屑，此次收购与其去年 8 月买入的美国 CAI Custom Alloys 组成跨大西洋平台。',
                orig_title='EverMetal acquires UK critical metals recycler Advanced Alloys')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.metal.com/newscontent/EO3OKCHVCOLWGXFKFXSVB52CG7CZZKHUWGK7UHQ-jintian-copper-produces-first-automotive-grade-recycled-copper-under-car-to-car-initiative',
                'SMM 国际站', '11-11',
                '宁波金田铜业产出首批汽车级再生电解铜，纯度 99.997%',
                '宁波金田铜业与中国汽车数据、吉利汽车合作的「车到车」循环项目产出首批汽车级再生电解铜，纯度达 99.997%；项目旨在建立可追溯的闭环回收链，商业化规模产量尚未披露。',
                orig_title='Jintian Copper Produces First Automotive-Grade Recycled Copper Under Car-to-Car Initiative')),

    (CAT_HY, ni('https://news.metal.com/newscontent/WUW2FRSMIGOGX46IBXQTAG6WVV3DV6AN6ZMHK4I-linyi-city-issues-orange-alert-for-heavy-pollution-affecting-lead-smelters-in-shandong',
                'SMM 国际站', '11-11',
                '临沂发布重污染橙色预警，山东铅冶炼与再生铅供应受扰',
                '山东临沂 11 月 10 日 10 时发布重污染天气橙色预警，并计划 11 月 12 日 12 时启动Ⅱ级应急响应，可能扰动山东地区冶炼企业生产与原料运输；具体影响待观察减排清单与企业实际执行。',
                orig_title='Linyi City Issues Orange Alert for Heavy Pollution, Affecting Lead Smelters in Shandong')),
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
    ('沪铝库存', CAT_SC),
    ('高盛', CAT_SC),
    ('锂电出口管制', CAT_ZC),
    ('广期所', CAT_ZC),
    ('帕多瓦', CAT_ZK),
    ('深地科学联合实验室', CAT_ZK),
    ('卡梅尔堡', CAT_ZK),
    ('豪莱克溪', CAT_ZK),
    ('中国铜业', CAT_ZK),
    ('津巴布韦', CAT_GJ),
    ('住友金属', CAT_GJ),
    ('巴林铝业', CAT_GJ),
    ('刚果（金）', CAT_GJ),
    ('西芒杜', CAT_GJ),
    ('Highland Valley', CAT_GJ),
    ('USA Rare Earth', CAT_GJ),
    ('Thacker Pass', CAT_GJ),
    ('Altius', CAT_MA),
    ('EverMetal', CAT_MA),
    ('金田铜业', CAT_HY),
    ('临沂', CAT_HY),
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
