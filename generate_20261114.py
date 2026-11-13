# -*- coding: utf-8 -*-
"""
生成 2026-11-14 矿业资讯速览 index.html（周六）
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

REPORT = '2026-11-14'
GRAB = '2026-11-14'
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
                         r'\g<1>2026年11月14日 星期六', html)
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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202611/t20261113_2942491.html',
                '自然资源部', '11-13',
                '四部门公布新一批国家级绿色矿山名单，296 家矿山入选',
                '自然资源部、生态环境部、国家金融监督管理总局、国家林业和草原局联合公告，经省级推荐、审核论证、抽查核实、社会公示等程序，共 296 家矿山通过遴选纳入国家级绿色矿山名录，接受社会监督。')),

    (CAT_ZC, ni('https://news.smm.cn/news/BRC6J2X733RHOJPV6M6FJAA2ZOT7NDHBB3K22GQ',
                '上海有色网', '11-13',
                '欧盟对涉华铜管作出反倾销初裁，中国其他企业税率 51.5%',
                '欧盟委员会 11 月 11 日对原产于中国、墨西哥、越南和乌兹别克斯坦的铜管作出反倾销初裁：宁波金田铜管临时税率 33.5%，中国其他企业 51.5%，墨西哥企业 18.2%，乌兹别克斯坦企业 5.6%至11%，越南企业 12.3%至14.4%。')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/3YFREFAJFFSJDNYADYSGQ6UQYQWKZIH7VIURKDA-india-launches-anti-dumping-probe-on-aluminium-products-from-china-malaysia-thailand-and-vietnam',
                'SMM 国际站', '11-13',
                '印度对涉华铝挤压型材发起反倾销调查，涉 14 个税号',
                '印度商工部贸易救济总局 11 月 9 日自主对原产于中国、马来西亚、泰国和越南的铝挤压型材、结构件及制品发起反倾销调查（案号 AD/OI/079/2026），覆盖 14 个 HS 税号并延伸至门窗、幕墙、光伏支架等下游制品，倾销调查期为 2025 年 4 月至 2026 年 6 月。',
                orig_title='India Launches Anti-Dumping Probe on Aluminium Products from China, Malaysia, Thailand, and Vietnam')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/WAWSTCJ4YILE53JLTY5T5XM2VAT67EGFW2E7STY',
                '上海有色网', '11-13',
                '电钴一周跳涨 4 万元/吨，钴系产品集体自年内低位反弹',
                'SMM 现货报价显示，11 月 13 日电解钴报 27~28 万元/吨、均价 27.5 万元/吨，较 11 月 6 日年内低点上涨 4 万元/吨、涨幅 17.02%；硫酸钴涨 16.78% 至 5~5.3 万元/吨，冶炼厂报价已无 5 万元/吨以下价位。')),

    (CAT_SC, ni('https://news.smm.cn/news/ORCORDO3LRYWHRBKS3URRUJSRBBG43QIMGPTHNA',
                '上海有色网', '11-13',
                '高盛：2027 年铜价 15,400 美元/吨的预测面临下行风险',
                '高盛 11 月 12 日报告称，受 AI 相关持仓与美国关税预期下调影响，其 2027 年铜价 15,400 美元/吨的预测面临下行风险；若持仓维持当前水平，2027 年均价或落至 14,600 美元/吨附近。LME 三个月期铜 13 日报 13,612 美元/吨。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/5TKDEV6MGV33DJ4VU6DKGXLC6BBZDOHWCFBRV3I-general-administration-of-customs-in-the-first-10-months-copper-semis-imports-fell-55-rare-earth-imports-fell-07-and-aluminum-semis-exports-rose-178',
                'SMM 国际站', '11-13',
                '海关总署：前 10 个月铜材进口降 5.5%、稀土进口降 0.7%、铝材出口增 17.8%',
                '海关总署数据显示，今年前 10 个月我国铜材进口同比下降 5.5%、稀土进口下降 0.7%，铝材出口同比增长 17.8%，铜、铝、稀土进出口呈「原料进、加工品出」的分化格局。',
                orig_title='General Administration of Customs: In the first 10 months, copper semis imports fell 5.5%, rare earth imports fell 0.7%, and aluminum semis exports rose 17.8%')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202611/t20261113_10363268.htm',
                '全球矿产资源信息系统', '11-13',
                '国际钯价单日大跌 5.21%，贵金属集体走弱',
                '纽约市场钯价收于 991.5 美元/盎司，单日下跌 5.21%；黄金收于 3,876.4 美元/盎司、跌 2.79%，白银收于 50.02 美元/盎司、跌 3.19%。同期铜价收于 13,604.5 美元/吨、跌 1.37%。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261113_2942463.html',
                '自然资源部', '11-13',
                '王登红：锂成矿多时代多旋回，找矿视野需跳出旧框架',
                '中国地质科学院矿产资源研究所研究员王登红表示，锂矿不止古老伟晶岩与第四纪盐湖两类，成矿具多时代、多旋回特征；西昆仑—松潘—甘孜「亚洲锂腰带」长约 2,800 余千米，集中一批超大型伟晶岩锂矿床。')),

    (CAT_ZK, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-11-13/9b0947c4-e116-4d85-a7e9-9e958862345a.PDF',
                '深圳证券交易所', '11-13',
                '天齐锂业雅江措拉锂矿资源储量核实报告通过评审备案',
                '天齐锂业公告，《四川省雅江县措拉矿区锂矿资源储量核实报告》已通过评审备案，为措拉锂矿后续开发建设与产能规划提供资源依据。',
                embed='pdf')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202611/t20261113_10363266.htm',
                '全球矿产资源信息系统', '11-13',
                '巴顿黄金更新南澳通基利亚金矿资源量，主矿 98.9 万盎司',
                '巴顿黄金更新南澳州高勒克拉通通基利亚项目资源量：总资源量 150 万盎司、品位 0.78 克/吨，主矿探明及推定资源量 98.9 万盎司；银资源量 280 万盎司、品位 2.71 克/吨。概略研究显示需投资 3.99 亿澳元建设年处理 550 万吨选厂，年产金 12 万盎司。')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261113_10362086.htm',
                '矿业权市场', '11-13',
                '内蒙古巴林右旗巴彦琥硕银矿探矿权挂牌成交，内蒙古山金竞得',
                '内蒙古自治区巴林右旗巴彦琥硕银矿勘查探矿权以网上挂牌方式出让并公示成交结果，竞得人为内蒙古山金地质矿产勘查有限公司，公示文号赤自然资示字〔2026〕1 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261113_10362084.htm',
                '矿业权市场', '11-13',
                '四川冕宁牙谷台子金多金属矿探矿权转让公示',
                '四川省冕宁县牙谷台子金多金属矿勘探探矿权转让公示，转让方为四川省核工业地质局二八一大队，受让方为四川省自然资源投资集团攀西有限责任公司，公示文号川探转公示〔2026〕15 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261113_10362082.htm',
                '矿业权市场', '11-13',
                '四川小金老熊塘金多金属矿详查探矿权转让公示',
                '四川省小金县老熊塘金多金属矿详查探矿权转让公示，受让方为成都宏德宝矿业有限责任公司，公示文号川探转公示〔2026〕13 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261113_10362083.htm',
                '矿业权市场', '11-13',
                '四川冕宁张家坪子金多金属矿勘探探矿权转让公示',
                '四川省冕宁县南河乡张家坪子金多金属矿勘探探矿权转让公示，按《矿业权出让交易规则》公示转让事项，异议由四川省政务服务和公共资源交易服务中心受理。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225671007.PDF',
                '巨潮资讯网', '11-13',
                '西部黄金子公司新疆美盛停产进展公告',
                '西部黄金就子公司新疆美盛停产事项披露进展公告，说明停产原因、复产安排及对公司生产经营的影响。',
                embed='pdf')),

    (CAT_HY, ni('https://news.metal.com/newscontent/5B3IRMVOPEI2M3BGMZDRI4YSHRAWVRB77PFSWEA-gongyi-city-launches-38-projects-worth-rmb-838bn-focusing-on-aluminium-based-new-materials',
                'SMM 国际站', '11-13',
                '河南巩义集中启动 38 个铝基新材料项目，聚焦板带箔与节能熔铸产线',
                '河南巩义市四季度集中启动 38 个铝基新材料项目，涵盖板带箔扩建、节能熔铸产线与源网荷储输电工程；郑州万泰铝业板带箔扩建已进入地坪固化与设备进场阶段。',
                orig_title='Gongyi City Launches 38 Projects Worth RMB 8.38bn, Focusing on Aluminium-Based New Materials')),

    (CAT_HY, ni('https://news.metal.com/newscontent/JMOSVLT6UFN2GQNXG65BIMMYYSHIFUQPAQ7A4RI-a-secondary-lead-smelter-in-east-china-cut-production-due-to-a-pollution-alert',
                'SMM 国际站', '11-13',
                '华东一大型再生铅冶炼厂因重污染橙色预警减产',
                'SMM 调研显示，华东地区一家大型再生铅冶炼厂受重污染天气橙色预警及Ⅱ级应急响应影响，自 11 月 12 日起减产，本轮限产或持续 6 天以上。',
                orig_title='A secondary lead smelter in east China cut production due to a pollution alert')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225671882.PDF',
                '巨潮资讯网', '11-13',
                '中国稀土披露发行股份购买资产并配套募资预案，股票复牌',
                '中国稀土披露发行股份购买资产并募集配套资金暨关联交易预案，交易预计构成关联交易与重大资产重组、不构成重组上市；公司股票同日复牌。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225671318.PDF',
                '巨潮资讯网', '11-13',
                '西藏矿业拟预挂牌转让白银扎布耶锂业 100% 股权',
                '西藏矿业公告，拟通过产权交易所预挂牌转让控股子公司白银扎布耶锂业有限公司 100% 股权，公开征集意向受让方。',
                embed='pdf')),

    (CAT_MA, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-11-13/7b5f8620-1865-41d7-8141-61902c718fef.PDF',
                '深圳证券交易所', '11-13',
                '新宙邦与亿纬锂能签订长期供货协议',
                '新宙邦公告与亿纬锂能签订《长期供货协议》，就锂电材料长期供应达成合作，具体供货量与价格按协议约定执行。',
                embed='pdf')),

    (CAT_MA, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-11-13/85e13380-0578-4c4e-8b1d-76904d1d61e6.PDF',
                '深圳证券交易所', '11-13',
                '金力永磁 20000 吨高性能稀土永磁材料项目推进',
                '金力永磁披露投资建设年产 20000 吨高性能稀土永磁材料绿色智造项目的进展公告，项目按既定计划推进。',
                embed='pdf')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/guinea-gold-mining-crackdown-leaves-10-dead-sparks-exodus',
                'MINING.COM', '11-13',
                '几内亚西吉里金矿整治冲突致 10 人死亡，逾 1200 人被捕',
                '几内亚 11 月 2 日实施非法采金禁令后展开整治，西吉里金矿区冲突造成 10 人死亡、13 人受伤，其中 5 人为外国公民；安全部队已逮捕超 1200 名涉嫌非法采矿人员，约 10 万人涌入马里首都巴马科，布基纳法索已接回 45406 名公民。',
                orig_title='Guinea gold mining crackdown leaves 10 dead, sparks exodus')),

    (CAT_GJ, ni('https://www.mining.com/hudbay-cuts-cost-outlook-as-copper-mountain-improves',
                'MINING.COM', '11-13',
                'Hudbay 下调成本指引，Copper Mountain 首次实现季度正自由现金流',
                'Hudbay 将年度铜现金成本指引下调至负 55 至负 35 美分/磅，第三季度铜产量同比增 25% 至 30152 吨、黄金产量增 30% 至 69513 盎司，营收翻倍至 7.659 亿美元；Copper Mountain 自 2023 年被收购以来首次实现季度正自由现金流。',
                orig_title='Hudbay cuts cost outlook as Copper Mountain improves')),

    (CAT_GJ, ni('https://www.mining.com/titan-us-military-team-up-on-graphite',
                'MINING.COM', '11-13',
                'Titan 与美国陆军合作建石墨加工厂，初始产能 1 万吨',
                'Titan Mining 与美国陆军就其安尼斯顿基地石墨加工设施达成商业条款清单，租期初始 50 年；纽约 Kilbourne 矿按初步经济评估可年产石墨精矿约 4 万吨、矿山寿命 13 年，净化微粉石墨初始产能 1 万吨。',
                orig_title='Titan, US military team up on graphite')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261113_10363267.htm',
                '全球矿产资源信息系统', '11-13',
                'Codelco 与印度阿达尼集团签约，共同勘探开发卡伯卡拉铜矿',
                '智利国家铜业公司（Codelco）与印度阿达尼集团签署协议，双方将共同勘探开发智利北部安托法加斯塔大区的卡伯卡拉（Cabecera）铜矿项目。')),
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
    ('绿色矿山', CAT_ZC),
    ('铜管', CAT_ZC),
    ('铝挤压型材', CAT_ZC),
    ('电钴', CAT_SC),
    ('高盛', CAT_SC),
    ('海关总署', CAT_SC),
    ('钯价', CAT_SC),
    ('王登红', CAT_ZK),
    ('措拉', CAT_ZK),
    ('通基利亚', CAT_ZK),
    ('巴彦琥硕', CAT_KQ),
    ('牙谷台子', CAT_KQ),
    ('老熊塘', CAT_KQ),
    ('张家坪子', CAT_KQ),
    ('新疆美盛', CAT_HY),
    ('巩义', CAT_HY),
    ('再生铅', CAT_HY),
    ('中国稀土', CAT_MA),
    ('扎布耶', CAT_MA),
    ('新宙邦', CAT_MA),
    ('金力永磁', CAT_MA),
    ('几内亚', CAT_GJ),
    ('Hudbay', CAT_GJ),
    ('Titan', CAT_GJ),
    ('Codelco', CAT_GJ),
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
