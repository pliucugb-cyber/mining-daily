# -*- coding: utf-8 -*-
"""
生成 2026-09-24 矿业资讯速览 index.html
- 09-23 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-24）回补历史条目
- 换入 09-23~09-24 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-23 收盘 + LME 09-22 收盘（东财日K末点=09-22，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（ky.mnr 09-23 有新公告，另行注入）
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

REPORT = '2026-09-24'
GRAB = '2026-09-24'
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
                         r'\g<1>2026年09月24日 星期四', html)
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
    (CAT_KQ, ni('https://www.mining.com/blue-moon-reports-7-metre-tungsten-interval-gains-access-to-public-land',
                'MINING.COM', '09-23',
                'Blue Moon 获准进入公共土地 施普林格钨矿见矿 7 米',
                'Blue Moon Metals 公布其施普林格（Springer）钨矿项目钻获 7 米钨矿段，并取得公共土地准入，公司目标在 2027 年四季度重启该矿山的采矿与选矿。',
                orig_title='Blue Moon reports 7 metre tungsten interval, gains access to public land')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260923_10321797.htm',
                '全球矿产资源信息系统', '09-23',
                '加拿大斯特金福尔斯稀土矿钻探见矿 214.5 米 TREO 品位 0.80%',
                '沃尔塔金属有限公司（Volta Metals）公布加拿大安大略省斯特金福尔斯（Sturgeon Falls）项目最新钻探结果：SL26-28 孔在 103.5—318.0 米见矿 214.5 米、总稀土氧化物（TREO）品位 0.80%，其中 291.0—292.5 米见矿 1.5 米、TREO 品位 7.37%。三个孔均见镓矿化；公司 2026 年计划完成 5452 米钻探，明年一季度更新施普林格矿床资源量（现推定矿石资源量 5660 万吨、TREO 品位 0.7%）。',
                )),
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104131670-meridian-mining-completes-caba',
                'SMM 国际站', '09-23',
                'Meridian 完成巴西 Cabaçal 铜金项目可行性研究',
                'Meridian Mining 完成其位于巴西马托格罗索州 Cabaçal 铜金项目的最终可行性研究：矿山服务年限 13.9 年，矿石处理能力首期 250 万吨/年、第 4 年起扩至 450 万吨/年，全生命周期平均铜回收率 92.8%、累计产铜约 18.06 万吨；初始资本开支约 3.22 亿美元，含 10% 预备费。',
                orig_title='Meridian Mining Completes Cabaçal Copper-Gold DFS, Targets 4.5 Mt/y Processing Expansion')),
    (CAT_ZK, ni('https://www.mining.com/selkirk-coppers-minto-posts-494m-value-nearly-triple-its-build-costs',
                'MINING.COM', '09-23',
                'Selkirk Copper 育空 Minto 项目初步经济评估估值 4.94 亿美元',
                'Selkirk Copper 公布育空地区 Minto 铜矿项目初步经济评估（PEA）结果，估值 4.94 亿美元，接近其 1.86 亿美元初始建设成本的三倍。',
                orig_title="Selkirk Copper's Minto posts $494M value, nearly triple its build costs")),
    (CAT_ZK, ni('https://news.smm.cn/news/104131166',
                '上海有色网', '09-23',
                '驰宏锌锗保有铅锌资源量超 3200 万吨 未来 3~5 年力争增长',
                '驰宏锌锗在投资者活动记录表中表示，截至 2025 年末公司保有铅锌资源量超 3200 万吨，新获取的乌蒙矿业硝洞探矿权保有铅锌金属量 232 万吨；未来 3 至 5 年资源保有量将保持不降低并力争增长。公司将通过深挖自有矿山深边部及外围找矿、参与矿权招拍挂、推进风险勘查合作以及引入控股股东优质资源等方式，系统性提升资源储备规模。',
                )),
    (CAT_ZC, ni('https://news.smm.cn/news/104131658',
                '上海有色网', '09-23',
                '美国国防部招标铟锰镁钛四种关键金属 推军工矿产供应链本土化',
                '美国国防部下属国防工业基地联盟 2026 年 8 月 21 日发布招标公告，面向国内企业征集铟、锰、镁、钛四种关键金属的投资方案，覆盖采矿、选冶、精炼、金属制造到回收全产业链，提交截止日期为 9 月 17 日。这是 2025 年中以来该联盟第三次围绕关键矿产和先进国防技术开展投资征集。',
                )),
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/flfg/202609/t20260923_10321796.htm',
                '全球矿产资源信息系统', '09-23',
                '挪威施压未果 欧盟坚持反对北极新油气钻探',
                '欧盟发言人表示，尽管挪威施压要求改变立场，欧盟仍坚持 2021 年北极政策联合声明，支持禁止在北极开展新的油气钻探、且不购买其生产的油气。挪威是欧洲最大天然气供应国，称即使未获欧盟支持仍将在巴伦支海继续开发油气。欧盟计划 10 月 20 日公布新的北极政策。',
                )),
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202609/t20260923_2939031.html',
                '自然资源部', '09-23',
                '自然资源部将彭泽县丰岭矿区灰岩矿移出国家级绿色矿山名录',
                '自然资源部公告，因彭泽县丰岭矿区建筑石料用灰岩矿资源枯竭、采矿许可证到期后已依法注销且矿山关闭，依据《国家级绿色矿山名录移出管理工作要求》等规定，决定将其移出国家级绿色矿山名录。',
                )),
    (CAT_SC, ni('https://news.smm.cn/news/104131580',
                '上海有色网', '09-23',
                '黑钨精矿不到一个月跌近 5% 均价跌破 40 万元/标吨',
                '据 SMM 报价，黑钨精矿（≥65%）9 月 23 日均价 398500 元/标吨、较前一交易日跌 0.5%，与 8 月 26 日的 418500 元/标吨相比下跌 20000 元/标吨、跌幅 4.78%。头部钨企下调 9 月下半月长单报价，55% 黑钨精矿采购价降至 40 万元/标吨、较上轮下调 1.3 万元/标吨；下游接货寥寥、散单成交稀少。',
                )),
    (CAT_SC, ni('https://news.smm.cn/news/104131331',
                '上海有色网', '09-23',
                'SMM 日评：基本金属普跌 沪镍独涨 0.97% 碳酸锂跌 3.2%',
                '9 月 23 日日间收盘，内盘基本金属普跌，仅沪镍上涨 0.97%；沪铅跌 0.61%、沪锌跌 0.64%，氧化铝主连跌 1.21%。碳酸锂主连跌 3.2%、多晶硅跌 1.44%、工业硅涨 0.94%。外盘基本金属全线飘绿，伦锌跌 1.24% 领跌、伦铜跌 0.85%、伦铝跌 0.78%；COMEX 黄金跌 0.14%、白银涨 0.27%。',
                )),
    (CAT_SC, ni('https://news.smm.cn/news/104127726',
                '上海有色网', '09-23',
                '8 月锂辉石进口 90.66 万实物吨再创新高 折碳酸锂当量约 7.6 万吨',
                '海关数据显示，2026 年 8 月中国锂辉石进口量 90.66 万实物吨，较 7 月的 73.93 万吨环比增长约 22.6%，折合碳酸锂当量约 7.6 万吨 LCE、环比增长约 18%；8 月碳酸锂进口 30391 吨，环比增加 14%、同比增加 39%。因低品位原矿占比偏高，进口矿实际可转化的锂盐供给增量相对温和。',
                )),
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260923_10321799.htm',
                '全球矿产资源信息系统', '09-23',
                '国际铜价逼近历史高点后回落 LME 铜收于 14770.50 美元/吨',
                '周二国际矿产品价格多数下跌，LME 铜期货收于 14770.50 美元/吨（约 9.97 万元/吨）、上涨 0.73%，盘中逼近历史高点后回落；铝 3259.50 美元/吨、铅 1931.00 美元/吨、锌 3909.50 美元/吨小幅下跌，镍 16565.00 美元/吨、锡 54215.00 美元/吨上涨。纽约黄金收于 4364.3 美元/盎司、上涨 0.49%，白银 67.06 美元/盎司、上涨 1.59%。',
                )),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104131631-lme-aluminum-inventory-declines-031-to-241400-mt-on-september-23',
                'SMM 国际站', '09-23',
                'LME 铝库存降至 24.14 万吨 单日减少 750 吨',
                '9 月 23 日 LME 铝库存 241400 吨，较前一交易日减少 750 吨、降幅 0.31%；过去一周减少 2225 吨（-0.91%），过去一个月减少 5550 吨（-2.25%）。',
                orig_title='LME Aluminum Inventory Declines 0.31% to 241,400 mt on September 23')),
    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202609/t20260923_10321795.htm',
                '全球矿产资源信息系统', '09-23',
                '2025/26 财年澳大利亚黄金产量 303 吨 同比增 4 吨',
                '瑟比顿联合公司（Surbiton Associates）称，2025/26 财年澳大利亚黄金产量 303 吨（约 970 万盎司），较上一财年增长 4 吨，按现价计价值约 600 亿美元。纽蒙特博丁顿（Boddington）金矿二季度产量环比增长 4.9 万盎司，卡迪亚（Cadia）金矿因地震停产环比下降 6 万盎司。',
                )),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104131653-metlen-invests-',
                'SMM 国际站', '09-23',
                'METLEN 投资 2500 万欧元升级希腊再生铝产线',
                'METLEN Energy & Metals 将投资近 2500 万欧元用于其希腊 EP.AL.ME. 再生铝业务，加装高自动化分选、处理与熔炼设备，使这家希腊最大独立再生铝生产商能够处理更复杂的废料流，特别是此前难以高效利用的报废产品回收废料，并与希腊原铝业务形成更紧密的一体化。',
                orig_title='METLEN Invests €25M in Greek Recycled Aluminum Plant, Boosting Scrap Processing and Integration')),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104131627-azerbaijan-plans-new-200000-ty-aluminum-smelter-attracts-foreign-investors',
                'SMM 国际站', '09-23',
                '阿塞拜疆拟新建年产 20 万吨电解铝厂',
                '阿塞拜疆经济部长 Jabbarov 在 9 月 22 日总统主持的会议上表示，该国正筹划新建一座年产能约 20 万吨的电解铝厂，已吸引外国投资者关注。该项目独立于 Azeraluminium 现有产能，是阿塞拜疆依托能源价格、运输通道与中亚及南高加索原料打造区域加工枢纽规划的一部分。',
                orig_title='Azerbaijan Plans New 200,000 t/y Aluminum Smelter, Attracts Foreign Investors')),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104131686-smm-chromium-flash-madagascars-kraoma-moves-to-restart-brieville-chrome-mining-after-years-of-inactivity',
                'SMM 国际站', '09-23',
                '马达加斯加 KRAOMA 拟重启 Brieville 铬矿开采',
                '马达加斯加国有铬生产商 Kraomita Malagasy（KRAOMA）正准备重启其 Brieville 铬矿开采。公司临时管理层已启动改革并与员工协商，利用反腐调查追回的部分资金结清 6 个月欠薪，并拨款用于 Brieville 复产；该公司自 2019 年以来未再出口铬矿。',
                orig_title="[SMM Chromium Flash] Madagascar's KRAOMA Moves to Restart Brieville Chrome Mining After Years of Inactivity")),
    (CAT_GJ, ni('https://www.mining.com/us-eyes-up-to-7-billion-for-argentina-mining-energy',
                'MINING.COM', '09-23',
                '美国拟向阿根廷矿业与能源提供最高 70 亿美元融资',
                '美国拟通过进出口银行（EXIM）为阿根廷矿业与能源项目提供最高 70 亿美元融资，帮助当地企业采购美国设备，这是华盛顿构建安全矿产供应链努力的一部分。',
                orig_title='US eyes up to $7 billion for Argentina mining, energy')),
    (CAT_GJ, ni('https://www.mining.com/glencore-to-help-build-us-minerals-stockpile-with-500m-exim-financing',
                'MINING.COM', '09-23',
                '嘉能可获 5 亿美元 EXIM 融资 参与建设美国矿产储备',
                '嘉能可将为美国一项矿产储备计划采购与交付原料，该储备旨在为美国制造商提供缓冲，相关安排包含美国进出口银行 5 亿美元融资。',
                orig_title='Glencore to help build US minerals stockpile with $500M EXIM financing')),
    (CAT_GJ, ni('https://www.mining.com/ex-gold-fields-ceo-targets-1b-africa-critical-minerals-fund',
                'MINING.COM', '09-23',
                '前 Gold Fields 首席执行官牵头筹建 10 亿美元非洲关键矿产基金',
                'Gold Fields 前首席执行官 Chris Griffith 与矿业及金融界资深人士合作，拟募集 10 亿美元资金，投向非洲关键矿产领域。',
                orig_title='Ex-Gold Fields CEO targets $1B Africa critical minerals fund')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104131701-smm-chromium-flash-rising-attacks-on-pakistans-balochistan-mining-routes-threaten-chromite-supply-chain',
                'SMM 国际站', '09-23',
                '巴基斯坦俾路支省矿业运输通道遇袭增加 铬矿供应链承压',
                '武装冲突地点与事件数据项目（ACLED）记录显示，2026 年 1—9 月巴基斯坦俾路支省与采掘活动相关的袭击事件达 38 起，三年累计超过 130 起；近 90% 针对矿产项目的袭击发生在道路上，袭击者以运输矿物与物资的车辆为目标。铬矿是该省开采矿种之一，安全形势或加大巴基斯坦铬矿供应与物流压力。',
                orig_title="[SMM Chromium Flash] Rising Attacks on Pakistan's Balochistan Mining Routes Threaten Chromite Supply Chain")),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104131668-capstone-copper-agrees-to-sell-cozamin-mine-to-luca-mining-for-up-to-us385-million',
                'SMM 国际站', '09-23',
                'Capstone 以最高 3.85 亿美元向 Luca Mining 出售墨西哥 Cozamin 铜矿',
                'Capstone Copper 签署最终协议，将位于墨西哥萨卡特卡斯州的 Cozamin 铜银锌铅矿出售给 Luca Mining，总对价最高 3.85 亿美元：交割时现金 2.75 亿美元、Luca 股票 1500 万美元、交割一周年应付递延对价 3500 万美元，另有最高 6000 万美元与 2027—2029 年 LME 铜均价挂钩的或有付款。',
                orig_title='Capstone Copper Agrees to Sell Cozamin Mine to Luca Mining for Up to US$385 Million')),
    (CAT_MA, ni('https://news.smm.cn/news/104131621',
                '上海有色网', '09-23',
                '印度 Lohum 拟收购印尼与菲律宾镍矿 目标产能提升十倍',
                '印度关键矿物生产商 Lohum 首席执行官 Rajat Verma 表示，公司正寻求收购印度尼西亚和菲律宾的镍矿，并计划在未来 18 个月内将镍年产能由目前的 1000 吨提升至 10000 吨，同时拟募资 100 亿卢比股权资金与 200 亿卢比债务资金。公司还在津巴布韦投资 1 亿美元布局锂资源，已获得 10 处锂矿区块开采权。',
                )),
    (CAT_MA, ni('https://news.smm.cn/news/104131679',
                '上海有色网', '09-23',
                '鲁北化工拟约 2.09 亿元增资源海科技 保障 20 万吨钛白粉项目投产',
                '鲁北化工公告，为保障年产 20 万吨联产法钛白粉绿色生产项目（一期）按期投产，拟通过全资子公司金海钛业以约 2.09 亿元对控股孙公司源海科技增资，其中 2 亿元计入注册资本、904.58 万元计入资本公积。增资完成后源海科技注册资本由 1 亿元增至 3 亿元，金海钛业持股由 70% 升至 90%。',
                )),
    (CAT_MA, ni('https://news.smm.cn/news/104131673',
                '上海有色网', '09-23',
                '星源卓镁拟投资 2.8 亿元建轻量化精密结构件项目',
                '星源卓镁公告，公司 9 月 21 日与奉化经济开发区管委会签署投资协议，拟以全资子公司为实施主体在奉化经济开发区投资 2.8 亿元建设轻量化精密结构件智能制造项目，资金来源为自有资金或自筹资金。',
                )),
    (CAT_MA, ni('https://www.mining.com/highlander-lines-up-330m-corani-silver-project-debt',
                'MINING.COM', '09-23',
                'Highlander 为秘鲁 Corani 银矿项目安排 3.3 亿美元债务融资',
                'Highlander Silver 为秘鲁已获全部许可的 Corani 银矿项目安排了 3.3 亿美元债务融资，向项目建设资金需求再进一步。',
                orig_title='Highlander lines up $330M Corani silver project debt')),
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
