# -*- coding: utf-8 -*-
"""
生成 2026-09-25 矿业资讯速览 index.html
- 09-24 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-27）回补历史条目
- 换入 09-24~09-25 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-24 收盘 + LME 09-24 收盘（东财日K末点=09-24，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（ky.mnr 09-23/09-24 有新公告，另行注入）
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

REPORT = '2026-09-25'
GRAB = '2026-09-25'
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
                         r'\g<1>2026年09月25日 星期五', html)
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
    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260924_10321822.htm',
                '矿业权市场', '09-23',
                '河南汝州张沟铝土矿普查探矿权挂牌出让',
                '河南省自然资源厅以挂牌方式出让《河南省汝州市张沟铝土矿普查探矿权》，勘查矿种铝土矿，面积4.0243平方千米，位于平顶山市汝州市，勘查工作程度空白区，拟出让年限5年，起始价20.12万元，出让收益率1.2%，挂牌期2026年11月11日至11月27日。',
                )),

    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260924_10322842.htm',
                '全球矿产资源信息系统', '09-24',
                '科特迪瓦费尔凯金矿 900 米深仍见矿',
                '多峰矿产（Many Peaks Minerals）在科特迪瓦东北部费尔凯（Ferke）金矿项目瓦里克远景区钻探，于地表以下900多米深处见矿，把金矿化垂向深度扩大70%：524米处见矿116米、金品位2.78克/吨，970米处见矿116.5米、金品位1.76克/吨，实际厚度分别约63.5米和110米。该矿区今年4月公布矿石资源量2670万吨、金品位1.54克/吨（含金130万盎司）。',
                )),
    (CAT_ZK, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0924/62082.html',
                '中国有色金属工业协会', '09-24',
                '江西物化探大队推进新疆于沟钼多金属矿普查',
                '江西省地质局物化探大队承接的新疆若羌县于沟钼多金属矿普查项目，位于新疆若羌与青海茫崖交界的阿尔金山，矿区平均海拔4500多米、部分测线海拔超过5200米。项目组于6月29日进场，投入磁法、重力、激电中梯、激电测深及测井等综合物探手段，查明矿体规模、形态、产状与厚度，为下一步钻探验证提供依据。',
                )),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474279',
                '中国有色金属报', '09-24',
                '沪铜现货升水突破千元大关',
                '据SMM数据，9月22日早盘铜现货升水突破1000元/吨，此后升至1100~1400元/吨，长江现货铜升贴水均价达1350元/吨。上期所铜仓单持续处于低位、可流通货源紧张，叠加双节前下游刚性备货，支撑升水高位坚挺；进口铜精矿现货加工费（TC）已跌至-221.89美元/干吨的历史低位，市场预计10—11月国内多家铜冶炼厂集中检修。',
                )),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474282',
                '中国有色金属报', '09-24',
                'BMI 上调今年国际锡均价预测至 5.1 万美元/吨',
                '惠誉解决方案旗下BMI将2026年国际锡均价预测从4.9万美元/吨上调至5.1万美元/吨；9月22日伦敦金属交易所三个月期锡价最高为54470美元/吨。BMI预计今年AI领域投资规模将达7850亿美元，全球精炼锡产量将从2024年的41.91万吨增至2030年的47.834万吨，同期全球锡消费量从41.34万吨增至54.43万吨，供需缺口进一步扩大。',
                )),
    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/chanyeshuju/2026/0924/62087.html',
                '中国有色金属工业协会', '09-24',
                '8 月份有色金属价格同比上涨 28.8%',
                '据商务部商务大数据，8月份全国生产资料市场价格环比上涨1.1%。主要品种中有色金属价格环比上涨3.9%、同比上涨28.8%，其中铜、锌、铝价格环比分别上涨4.0%、3.9%和3.8%；钢材价格环比下降1.0%、同比下降4.1%，螺纹钢、槽钢、普通高速线材环比分别下降1.4%、1.3%和0.9%。',
                )),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474278',
                '中国有色金属报', '09-24',
                '美联储加息落地 机构预计短期沪铝有望触及 2.47 万元/吨',
                '广金期货分析认为，美伊冲突导致中东电解铝产能复工困难，受损电解槽单条生产线完整复产周期普遍需要6~12个月；国内电解铝运行产能截至8月已达上限。需求端新能源汽车单车用铝量220~300千克，AI数据中心用铝快速增长。截至9月21日电解铝社会库存69.8万吨、处于低位；美联储加息落地后利空情绪释放，预计短期沪铝价格有望达到2.47万元/吨一线。',
                )),
    (CAT_SC, ni('https://news.smm.cn/news/104133825',
                '上海有色网', '09-24',
                'SMM 日评：内盘金属多数走弱 碳酸锂跌逾 4%',
                'SMM 9月24日日报显示，内盘基本金属多数下跌，沪锌以0.36%的涨幅领涨、沪铅以0.79%的跌幅领跌，沪镍跌0.66%、沪铜跌0.57%，氧化铝主连跌1.14%；碳酸锂主连跌4.79%、多晶硅主连跌1.7%。贵金属方面沪金跌1.34%、沪银跌3.15%，铂主连跌3.57%、钯主连跌2.58%；截至15:09美元指数下跌0.05%报101.08。',
                )),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0924/62083.html',
                '中国有色金属工业协会', '09-24',
                '上期所镍期货国际化业务实现全流程贯通',
                '上期所镍期货境外交易者交割月移仓业务顺利完成，标志镍期货国际化业务实现从交易、结算到交割的全流程闭环。自4月22日至8月底，镍期货日均成交规模35.7万手、日均持仓规模34.3万手，注册品牌涵盖16个境内外品牌；已有38家境外中介在上期所完成备案，参与主体覆盖全球18个国家和地区。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474274',
                '中国有色金属报', '09-24',
                '中矿资源赞比亚卡通巴选矿厂建成投产',
                '9月21日，中矿资源卡通巴矿业有限公司选矿厂完成建设期各项工作任务，正式进入生产运营阶段。卡通巴铜矿是中矿资源在赞比亚首个从零起步自主开发、自主运营的项目，选矿厂投产标志项目由工程建设阶段迈入生产运营阶段，将进一步提升项目资源利用效率。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474286',
                '中国有色金属报', '09-24',
                '中铝科学院赤泥炼铁与废阴极制电池正极材料取得突破',
                '中铝科学院未来材料研发中心在固废高值化利用、危废定向转化新能源材料两个方向取得技术突破。针对拜耳法赤泥颗粒细、铁铝矿物难分离、传统工艺能耗高等痛点，创新设计「高温煅烧造粒—低温流态化氢还原」两步法新工艺；同时提出熔盐电化学一步法重构策略，将铝电解废阴极炭块直接转化为高性能铝离子电池正极材料。',
                )),
    (CAT_HY, ni('https://news.smm.cn/news/104134137',
                '上海有色网', '09-24',
                '江特电机：推进茜坑锂矿开发以提升原料自给率',
                '江特电机在投资者活动记录表中表示，公司已于2024年取得自然资源部颁发的茜坑锂矿《采矿许可证》，系我国第一个在自然资源部办理的锂云母型锂矿采矿权证；公司已将茜坑出矿列为首要经营目标，前置手续正依法依规办理。2026年上半年公司营收9.57亿元、同比减少1.87%，归母净利润亏损2.13亿元，主因茜坑尚未开采、锂矿石原料全部外购。',
                )),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134461-guinea-expands-mining-cooperation-with-glencore-aims-to-boost-revenue-and-industrialization',
                'SMM 国际站', '09-24',
                '几内亚拟将嘉能可合作扩展至氧化铝、能源与黄金领域',
                '几内亚计划将其与嘉能可的合作从铝土矿扩展至氧化铝精炼、能源、黄金和基本金属领域，目标是扩大矿业收入、推动矿产本地加工与工业化，并加强与中国、中东等市场及国际矿业企业的合作。',
                orig_title='Guinea Expands Mining Cooperation with Glencore, Aims to Boost Revenue and Industrialization')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134456-dak-nong-aluminum-project-in-vietnam-achieves-full-operation-with-110-electrolysis-cells-tapping-aluminum',
                'SMM 国际站', '09-25',
                '越南得农电解铝项目一期 110 台电解槽全部出铝',
                '由中国有色金属建设股份有限公司（NFC）总承包的越南得农电解铝项目一期110台电解槽于2026年9月15日全部实现出铝，标志一期工程全面建成投产，项目由启动阶段转入稳定运行。',
                orig_title='Dak Nong Aluminum Project in Vietnam Achieves Full Operation with 110 Electrolysis Cells Tapping Aluminum')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134442-hindustan-copper-advances-776m-capex-funding-via-qip-bonds-for-vision-2030-expansion',
                'SMM 国际站', '09-24',
                '印度斯坦铜业股东批准 7.76 亿美元扩产融资',
                '印度斯坦铜业（HCL）年度股东会议批准两项融资安排：定向机构配售（QIP）不超过9698万股，以及非公开发行有担保或无担保非可转换债券；资金用于推进「2030愿景」下718.89亿卢比（约7.76亿美元）的五年资本开支计划。公司计划到2029-30财年把矿石产能从目前约400万吨/年提升至1220万吨/年。',
                orig_title='Hindustan Copper Advances $776M Capex Funding via QIP, Bonds for Vision 2030 Expansion')),
    (CAT_GJ, ni('https://www.mining.com/rio-tinto-to-expand-metals-trading-beyond-own-output',
                'MINING.COM', '09-24',
                '力拓计划将金属贸易扩展至第三方货源与衍生品',
                '力拓计划把金属贸易业务扩展到第三方货源与衍生品领域，以从其全球资产组合中获取更多价值。公司不打算复制独立大宗商品贸易商的模式，但考虑在首席商务官领导下显著扩大现有商业业务，方向包括在存在区域性过剩或短缺的氧化铝市场开展第三方贸易，并利用北美 Kennecott 的铜冶炼富余产能；商业团队目前约有20名交易员。',
                orig_title='Rio Tinto to expand metals trading beyond own output')),
    (CAT_GJ, ni('https://www.mining.com/kinross-gold-cuts-output-boosts-shareholder-payout',
                'MINING.COM', '09-24',
                'Kinross 下调 2026—2027 年产量指引约 8%',
                'Kinross Gold 因智利 La Coipa 的天气与冶金问题、美国内华达 Round Mountain 采矿表现疲弱，把2026—2027年产量指引中值下调约8%至每年184万~186万盎司金当量，上年同期指引为190万~210万盎司；今年全维持成本（AISC）指引上调至1850~1900美元/盎司。公司同时把2026年股东回报目标由自由现金流的40%提高至50%，年内已返还股东约8亿美元。',
                orig_title='Kinross Gold cuts output, boosts shareholder payout')),
    (CAT_GJ, ni('https://www.mining.com/tungsten-west-elmet-ink-1-8-billion-offtake-deal-for-hemerdon-mine',
                'MINING.COM', '09-24',
                'Tungsten West 与 Elmet 签 8 年承购协议',
                '英国德文郡 Hemerdon 钨锡矿运营方 Tungsten West 与美国 Elmet Technologies 签订具有约束力的8年期供应与承购协议，涉及 Hemerdon 每年1000吨（含WO₃）产量，按当前市价与汇率货值超过14亿英镑（约18亿美元）。英国国家财富基金此前已向 Tungsten West 投资至多7100万英镑，并就采购 Hemerdon 年产钨的至多50%进行独家谈判。',
                orig_title='Tungsten West, Elmet ink $1.8 billion offtake deal for Hemerdon mine')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/jgbg/202609/t20260924_10322841.htm',
                '全球矿产资源信息系统', '09-24',
                '刚果（金）拟设立矿业投资促进机构',
                '刚果（金）正在筹备成立一个矿业投资促进机构，作为该国与美国矿产伙伴关系相关改革的内容之一，目的是减少官僚环节、提高对西方投资的吸引力。该机构对所有国家投资者开放，由财政和经济部牵头，改革重点为矿业公司登记、许可、税收与合规，初期重点面向投资额超过10亿美元的合资项目，计划于今年开始运作。',
                )),
    (CAT_GJ, ni('https://news.smm.cn/news/104133802',
                '上海有色网', '09-24',
                '美国进出口银行 70 亿美元支持阿根廷能源与矿业项目',
                '美国政府宣布将通过美国进出口银行在2027年前为阿根廷能源、矿业和基础设施项目提供最高70亿美元贷款支持，资金主要用于帮助当地项目购买美国设备、聘用美国企业，并扩建铁路、管道、港口和电力网络。美方表示，该安排旨在把阿根廷西北部锂、铜资源以及南部 Vaca Muerta 页岩油气区更有效地连接到国内港口，扩大矿产与油气出口。',
                )),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225581060.PDF',
                '巨潮资讯网', '09-25',
                '盛屯矿业完成收购西藏海腾实业 65% 股权交割',
                '盛屯矿业公告，下属公司四川盛烽源矿业收购刘宗俊持有的西藏海腾实业有限责任公司65%股权的交割工作已完成，西藏海腾实业已完成工商变更登记，公司已支付股权转让款合计68,850万元，剩余尾款2,000万元将按协议约定在满足付款条件时支付。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225581915.PDF',
                '巨潮资讯网', '09-25',
                '嘉友国际签订布隆迪锂辉矿合作协议',
                '嘉友国际与布隆迪国家矿业公司 SONALEK MINING COMPANY LTD、矿山运营方 SUNTIAL HK LIMITED 共同签订《布隆迪锂辉矿合作协议》，合作期限7年。嘉友国际将为矿山开采设备采购以及仓库、道路等物流基建资金需求提供预付款等配套支持，同时作为独家物流供应商并享有锂辉石矿产品独家销售代理权。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225581833.PDF',
                '巨潮资讯网', '09-25',
                '中稀有色 1.42 亿元转让东电化广晟稀土 37% 股权',
                '中稀有色公开挂牌转让所持广东东电化广晟稀土高新材料有限公司37%股权，挂牌价格不低于14,175.20万元；挂牌期间征集到一个意向受让方东电化（中国）投资有限公司，成交价14,175.20万元，双方已于9月23日签订产权交易合同，交易完成后公司将不再持有该公司股权。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225581246.PDF',
                '巨潮资讯网', '09-25',
                '贵研铂业向贵研半导体材料增资 1 亿元',
                '贵研铂业董事会审议通过向全资子公司贵研半导体材料（云南）有限公司增资10,000.00万元的议案，以货币出资方式增资且全部计入注册资本，用于缓解该子公司生产经营资金压力、优化资本结构。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225583141.PDF',
                '巨潮资讯网', '09-25',
                '五矿发展重大资产置换申请文件获上交所受理',
                '五矿发展公告，公司重大资产置换、发行股份及支付现金购买资产并募集配套资金暨关联交易的申请文件获得上海证券交易所受理，相关交易报告书（申报稿）同步披露修订说明。',
                embed='pdf')),
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
