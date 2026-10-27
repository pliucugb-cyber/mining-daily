# -*- coding: utf-8 -*-
"""
生成 2026-10-27 矿业资讯速览 index.html（周二）
- 10-26 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-28）回补历史条目
- 换入 10-27 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-26 收盘 + LME 10-26 收盘（10-27 国内未开盘），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（本批 ky.mnr 无新增合规公告，仅易县花岗石类按口径剔除）
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

REPORT = '2026-10-27'
GRAB = '2026-10-27'
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
                         r'\g<1>2026年10月27日 星期二', html)
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
    (CAT_ZK, ni('https://www.mining.com/codelco-bhp-launch-40m-copper-hunt-in-northern-chile',
                'MINING.COM', '10-26',
                '智利国家铜业与必和必拓启动 Anillo 铜矿勘探，必和必拓最高投入 4,000 万美元',
                '双方 10 月 21 日于 LME 周期间正式签署协议，共同推进安托法加斯塔大区 Anillo 铜矿项目勘探，必和必拓承诺最高投入 4,000 万美元，用于踏勘、地球物理测量、地质研究与钻探计划。项目仍处早期勘探阶段，下一阶段将判断是否值得进入更高级别勘探乃至矿山开发；Codelco 希望借外部资本、技术与管理盘活其 230 万公顷矿权组合。',
                orig_title='Codelco, BHP launch $40M copper hunt in northern Chile')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202610/t20261026_10344941.htm',
                '全球矿产资源信息系统', '10-26',
                '加拿大戴维森钼铜钨项目更新初步经济评价，税后净现值升至 12.3 亿加元',
                'MRM 公司 10 月 22 日公布更新的初步经济评价（PEA）：按 8% 折现率计算的税后净现值由 2025 年 12 月的 10.3 亿加元升至 12.3 亿加元，税后内部收益率由 32% 升至 33%，回报期由 2.3 年缩短至 1.5 年，主因选矿流程由重选改为浮选。初始投资 7.501 亿加元，矿山寿命 20 年、日处理矿石 1 万吨，年均产钼 1,327 万磅、铜 150 万磅、钨（WO3）151 万磅，计划 2027 年开展预可行性研究。')),

    (CAT_ZK, ni('https://news.metal.com/newscontent/104179415-flash-victorio-molybdenum-resource-expands-ahead-of-new-economic-assessment',
                'SMM 国际站', '10-26',
                'Spartan 更新新墨西哥 Victorio 钨钼资源量，探明加控制资源 8,454 万短吨',
                '更新后的资源量估算显示，探明与控制资源合计 8,454 万短吨、品位 0.09% 钼，含钼 1.4785 亿磅（约 6.71 万吨）；推断资源 1.0184 亿短吨、品位 0.06%，含钼 1.3002 亿磅（约 5.90 万吨）。按每短吨 50 美元金属总值边界，两类资源较 2012 年历史估算分别增长 9.5% 与 31.9%，将支撑 2026 年四季度编制的初步经济评价。',
                orig_title='Victorio Molybdenum Resource Expands Ahead of New Economic Assessment')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202610/t20261021_2940830.html',
                '自然资源部', '10-21',
                '自然资源部通报矿业权登记管理暂行办法征求意见情况，共收到意见建议 66 条',
                '自然资源部 10 月 21 日公告，《矿业权登记管理暂行办法（征求意见稿）》于 2026 年 7 月 28 日至 8 月 13 日在部门网站向社会公开征求意见，共收到社会各界提出的意见建议 66 条。该部表示将对 66 条意见逐条深入研究、最大限度采纳合理内容，办法将按程序修改完善后发布。')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/104176910-mexico-and-india-initiate-anti-dumping-reviews-on-chinese-products-including-aluminium-cookware-and-pet-film',
                'SMM 国际站', '10-25',
                '墨西哥对华铝制炊具启动第二次日落复审，印度对华 PET 薄膜作出终裁',
                '墨西哥经济部 9 月 28 日应国内生产商申请，对原产于中国的铝制炊具启动第二次反倾销日落复审，倾销调查期为 2025 年 7 月至 2026 年 6 月，复审期间现行措施继续有效，利害关系方须在公告后 28 个工作日内登记。印度贸易救济总局 9 月 29 日对来自中国、孟加拉国和泰国的 PET 薄膜作出肯定性终裁，建议征收 5 年反倾销税，对中国产品为每吨 54 至 361 美元。',
                orig_title='Mexico and India Initiate Anti-Dumping Reviews on Chinese Products, Including Aluminium Cookware and PET Film')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474857',
                '中国有色金属报', '10-23',
                'LME 批准美国肯塔基州欧文斯伯勒为铜交割点，美国注册铜库存 13.71 万吨',
                '10 月 19 日，伦敦金属交易所批准美国肯塔基州欧文斯伯勒（Owensboro）作为铜交割地点，将在首家仓库企业取得该地点铜仓储资质审批 3 个月后正式启用。目前新奥尔良是美国规模最大的 LME 铜交割枢纽，其余获批地点包括巴尔的摩、芝加哥、底特律与莫比尔；LME 数据显示美国注册仓库铜库存 137,125 吨，花旗估算含场外库存在内约 110 万吨。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474751',
                '中国有色金属报', '10-20',
                '全国首单经全仓登登记的镍现货仓单转让业务落地上海',
                '中信寰球商贸与上海鑫尧实业完成全国首单经全国性大宗商品仓单注册登记中心（全仓登）登记的镍现货仓单转让：仓单由中储全球交割中心签发，全仓登办理转让登记并锁定货权，上海清算所按钱货对付原则完成资金清算。此举针对现货市场虚假仓单、重复质押、一货多卖等痛点，为有色金属现货仓单规范流转提供可复制样板。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202610/t20261026_10344943.htm',
                '全球矿产资源信息系统', '10-26',
                '国际有色金属普涨贵金属续跌，LME 锌涨 2.06%、COMEX 黄金跌破 4,000 美元',
                '伦敦金属交易所铜价收于每吨 14,285 美元、上涨 1.33%，铝 3,040.50 美元涨 1.16%，锌 3,746 美元涨 2.06%，锡 50,605 美元涨 1.21%，铅 1,904.50 美元涨 0.34%，镍 15,840 美元跌 0.94%。纽约商品交易所黄金收于 3,994 美元/盎司、跌 0.77%，白银 53.88 美元/盎司跌 1.30%，铂 1,562.4 美元跌 0.92%，钯 1,051.5 美元跌 0.47%。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474853',
                '中国有色金属报', '10-23',
                '9 月碳酸锂产量 10.2 万吨环比增 6.5%，电池级现货价月内跌 18.8%',
                '中国有色金属工业协会锂业分会统计，9 月全国碳酸锂产量约 10.2 万吨、环比增 6.5%，氢氧化锂约 2.9 万吨、环比降 12.5%，锂盐合计折碳酸锂当量约 12.8 万吨、环比增 2.1%。电池级碳酸锂现货由月初 15.75 万元/吨跌至月末 12.85 万元/吨、降幅 18.8%，主力合约由 15.786 万元/吨跌至 11.842 万元/吨、降幅 25.0%；9 月底广期所碳酸锂仓单 31,990 吨，环比减少 13,634 吨。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261026_10344939.htm',
                '全球矿产资源信息系统', '10-26',
                '前三季度世界粗钢产量 13.675 亿吨同比降 0.7%，中国降 2.9%',
                '世界钢铁协会对 70 个成员国的统计显示，9 月世界粗钢产量 1.424 亿吨、同比降 0.2%，前三季度累计 13.675 亿吨、同比降 0.7%。中国 9 月产量 7,360 万吨增 0.1%、前三季度 7.248 亿吨降 2.9%；印度前三季度 1.3 亿吨增 5.6%，越南 2,320 万吨增 29.1%，美国 6,490 万吨增 5.8%，欧盟 27 国 9,450 万吨降 0.8%、其中德国 9 月 260 万吨降 13.0%。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474918',
                '中国有色金属报', '10-26',
                '2025 年我国铝型材产量 1,990 万吨降 7.7%，工业型材占比升至约 59%',
                '中国有色金属加工工业协会数据显示，2025 年我国铝型材产量 1,990 万吨、同比下降 7.7%，为连续第二年下降；其中工业型材 1,175 万吨、同比微增 0.4%，占比升至约 59%，建筑型材回落至 815 万吨、同比降 17.3%。新能源汽车挤压结构件 2025 年产量 180 万吨、同比增 28.6%，光伏型材 405 万吨增 2.5%，轨道交通车体型材 13 万吨增 23.8%。')),

    (CAT_HY, ni('https://news.smm.cn/news/104176705',
                '上海有色网', '10-26',
                '洛阳钼业前三季度净利 240.2 亿元同比增 68.21%，铜产品量价齐升',
                '洛阳钼业三季报显示，前三季度营业收入 2,072.90 亿元、同比增长 42.48%，归母净利润 240.20 亿元、同比增长 68.21%。公司称业绩提升主要因铜产品量价同比双升、钼钨产品价格走高，叠加巴西金矿业务并表；9 月已完成中期利润分配，每 10 股派发现金红利 0.95 元、合计派现 20.32 亿元。')),

    (CAT_HY, ni('https://news.smm.cn/news/104179380',
                '上海有色网', '10-26',
                '明泰铝业三季度销量淡季不淡，在建项目达产后新增高端铝材产能 120 万吨',
                '明泰铝业在投资者交流中表示，第三季度销量呈淡季不淡状态，工业自动化、智能装备、新能源电池材料等领域订单饱满，在售订单约两个月以上、加工费稳定。项目建设提速：鸿晟新材汽车及绿色能源用铝项目已建成两条气垫炉和一台辊底炉，全部达产后新增 50 万吨高端铝材热处理产能；义瑞新材 72 万吨铝基新材料智能制造项目一期热粗轧已投产、二期精轧年底投产，新增产能 70 万吨，公司目标产销规模突破 200 万吨。')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104179386-lithium-battery-eve-energy-q1-q3-net-profit-up-86-ess-battery-shipments-reach-6752gwh',
                'SMM 国际站', '10-26',
                '亿纬锂能前三季度净利 52.4 亿元同比增 86.11%，储能电池出货 67.52GWh',
                '亿纬锂能三季报显示，前三季度营业收入 733.9 亿元、同比增长 63.08%，净利润 52.4 亿元、同比增长 86.11%；动力电池出货 66.17GWh，储能电池出货 67.52GWh。公司此前在投资者关系活动中表示，四季度排产预计环比增长，产能已确定订满。',
                orig_title='EVE Energy Q1-Q3 net profit up 86%, ESS battery shipments reach 67.52GWh')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://www.mining.com/local-miner-outbids-freeport-for-colombia-exploration',
                'MINING.COM', '10-26',
                '哥伦比亚 OP Gold 提高报价击败自由港，保住塞萨尔 60 平方公里勘探区块',
                '哥伦比亚国家矿业署最终评标显示，本土企业 OP Gold Capital 将对国家的额外付款比例由 1.5% 提高至 2.5%，击败报出 2% 的自由港麦克莫兰，保住塞萨尔省 60 平方公里勘探区块，并另获第 3 号区块。10 月 9 日哥方与 5 家企业签署 8 个铜、金及多金属合同，紫金矿业通过南美勘探子公司获得安蒂奥基亚省两个区块。',
                orig_title='Local miner outbids Freeport for Colombia exploration')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-27/1225622711.PDF',
                '巨潮资讯网', '10-27',
                '厦钨新能拟由控股子公司投建年产 4 万吨磷酸铁（锰）锂项目',
                '厦钨新能 10 月 27 日公告，由控股子公司作为投资建设主体，投建年产 40,000 吨磷酸铁（锰）锂项目。磷酸铁（锰）锂属磷酸铁锂的改性路线，公司主业为正极材料；项目投资金额、选址与建设周期以公告原文为准。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-27/1225626689.PDF',
                '巨潮资讯网', '10-27',
                '中铝国际披露越南项目中标',
                '中铝国际 10 月 27 日发布关于越南项目中标的公告，公司作为有色金属工业工程承包商在东南亚市场再获订单。合同金额、工期与业主信息以公告原文为准。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-27/1225626813.PDF',
                '巨潮资讯网', '10-27',
                '兴业银锡披露对外投资收购威领股份进展，标的同日发布详式权益变动报告书',
                '兴业银锡 10 月 27 日发布关于对外投资收购威领股份的进展公告；标的公司威领股份同日披露详式权益变动报告书。交易对价、股权比例与后续审批、交割安排以公告原文为准。',
                embed='pdf')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/strike-curbs-output-at-canadas-largest-copper-mine',
                'MINING.COM', '10-26',
                '泰克资源 Highland Valley 铜矿罢工，约 1,200 名工人停工、矿场限产',
                '泰克资源证实，工会 USW 第 7619 分会在不列颠哥伦比亚省 Highland Valley 铜矿发起罢工，矿场转入限产运行。该矿为加拿大最大铜矿，工会覆盖约 1,200 名工人，944 名参与投票者全部支持罢工；2025 年该矿产铜 127,100 吨，约占泰克总产量 453,500 吨的 28%，公司称产量受影响程度取决于罢工持续时间。',
                orig_title="Strike curbs output at Canada's largest copper mine")),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104173852-smm-analysis-indonesian-nickel-output-cut-talk-gathers-pace-but-the-case-for-cutting-diverges-across-the-supply-chain',
                'SMM 国际站', '10-22',
                '印尼镍减产传闻升温：MHP 与镍锍拟压减 50%、镍铁压减 20%，沪镍一度涨 3.05%',
                '市场传闻印尼将把混合氢氧化物沉淀（MHP）与镍锍产量压减 50%、镍铁（NPI）压减 20%，带动 10 月 21 日沪镍主力合约上涨 3.05%。SMM 分析认为，减产在不同环节的可行性差异明显，矿端与冶炼端的成本、出口政策及项目投产节奏并不一致，政策能否落地仍存不确定性。',
                orig_title='[SMM Analysis] Indonesian Nickel Output-Cut Talk Gathers Pace, but the Case for Cutting Diverges Across the Supply Chain')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104179441-early-mining-begins-at-malawis-kanyika-project',
                'SMM 国际站', '10-26',
                'Globe Metals 马拉维 Kanyika 铌项目启动提前开采，目标 2028 年初投产',
                'Globe Metals & Mining 宣布马拉维 Kanyika 铌项目已开始提前开采，按每批约 5,000 吨挖掘并堆存矿化物料供后续选厂调试，同时提供品位验证大样与非矿石料用于道路、地基与厂区平台。规划采区推定品位约 0.45% 五氧化二铌、0.015% 五氧化二钽，公司仍以 2028 年初首次产出为目标。',
                orig_title="Early mining begins at Malawi's Kanyika project")),
    (CAT_GJ, ni('https://www.mining.com/bc-tory-landslide-raises-mining-hopes-rights-fears',
                'MINING.COM', '10-27',
                '加拿大不列颠哥伦比亚省保守党大胜，矿业盼加速审批、原住民权益引担忧',
                '不列颠哥伦比亚省保守党在省选中以压倒性优势胜出，矿业界期待新政府加快矿山许可审批、加大勘探激励；与此同时，原住民团体对土地权利与环评程序可能弱化表达担忧。该省是加拿大重要矿产与勘探基地，政策走向将影响铜、金及关键矿产项目的推进节奏。',
                orig_title='British Columbia Conservative landslide raises mining hopes, Indigenous rights fears')),
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

# —— 分桶 PIN（按内容口径：技改扩产属 🏭、勘查投入属 🔍，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('明泰铝业', CAT_HY),
    ('铝型材', CAT_HY),
    ('洛阳钼业', CAT_HY),
    ('亿纬', CAT_HY),
    ('粗钢', CAT_HY),
    ('仓单', CAT_SC),
    ('交割点', CAT_SC),
    ('戴维森', CAT_ZK),
    ('Victorio', CAT_ZK),
    ('Kanyika', CAT_GJ),
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
