# -*- coding: utf-8 -*-
"""
生成 2026-11-11 矿业资讯速览 index.html（周三）
- 11-10 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-13）回补历史条目
- 换入 11-11 采集的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-10 收盘，全部由
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

REPORT = '2026-11-11'
GRAB = '2026-11-11'
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
                         r'\g<1>2026年11月11日 星期三', html)
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
    (CAT_SC, ni('https://news.smm.cn/news/VNWTAWV5FGFUJ5QTHUWR46J7XWIQPF3I2RF4BDQ',
                '上海有色网', '11-11',
                '海关总署：前 10 个月铜矿砂进口降 3.8%，铝材出口增 17.8%',
                '2026 年前 10 个月我国货物贸易进出口总值 44.81 万亿元、同比增 20%；10 月稀土出口 4,386 吨、同比增 1%，1—10 月累计 48,097.2 吨、同比减 8.7%；未锻轧铝及铝材 10 月出口 59.4 万吨、同比增 18.1%，1—10 月累计增 17.8%；铜矿砂及精矿 10 月进口 216.7 万吨、同比减 11.6%，1—10 月累计减 3.8%。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202611/t20261110_10359564.htm',
                '全球矿产资源信息系统', '11-10',
                'BMI：美国囤铜堆高库存，铜价短期承压',
                'BMI 报告称，铜价 9 月 10 日见顶 14,875 美元/吨后仍守在 14,000 美元/吨上方，但关税预期促使买家提前在美囤铜，CME 铜库存年初至 11 月 4 日累计增 61.9%，美国以外形成「人为短缺」；一旦关税力度减弱、溢价回吐，短期下行压力最大。矿端受限与 AI 需求仍构成中长期支撑，新项目从发现到投产约需 17 年。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/3002d702a1d6477588e7de49be7c058e.html',
                '长江有色网', '11-11',
                'LME 基本金属全线下跌，伦锡二连跌创七个半月新低',
                '11 月 10 日 LME 基本金属期货全线收跌，伦铜跌至今年 7 月底以来低位，伦锡连续第二个交易日下跌、收于七个半月新低。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/newscontent/CNTOCBN4QTSC2L3BEOVBYILPAZVOOIHVV6INVPY-china-extends-suspension-of-rare-earth-export-controls-until-january-2027',
                'SMM 国际站', '11-09',
                '中国将稀土出口管制暂停期延长至 2027 年 1 月',
                '商务部、海关总署 2026 年第 58 号公告，经批准，自 2026 年 11 月 11 日至 2027 年 1 月 10 日继续暂停实施 2025 年第 55、56、57、58 号公告及第 61、62 号公告，涉及中重稀土相关物项、稀土设备与原辅料、境外相关稀土物项等出口管制措施。',
                orig_title='China Extends Suspension of Rare Earth Export Controls Until January 2027')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/HX5YWFBWL7QMQAM2SWMDB6M764D5QNG37B4VW3I-canada-extends-tariff-remission-programme-to-june-2028-adjusts-eligible-goods',
                'SMM 国际站', '11-10',
                '加拿大将关税减免计划延至 2028 年 6 月，扩大适用商品',
                '加拿大把针对进口美国应税商品的关税减免计划再延一年至 2028 年 6 月 30 日，并扩大适用范围，新增制造业、农业、采矿与油气开采所用非钢类商品及公立教育机构采购；同时拟将在加可靠采购的拖车、铝线、纸板等排除在外。',
                orig_title='Canada extends tariff remission programme to June 2028, adjusts eligible goods')),

    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261110_10359563.htm',
                '全球矿产资源信息系统', '11-10',
                '民主党中期选举大胜，获美政府资助矿企面临更多审查',
                '随着民主党在中期选举中大胜，获特朗普政府数十亿美元支持的矿企面临更严格审查。美国稀土公司 1 月与商务部达成 16 亿美元协议、政府持股约 10%；沃尔坎元素获五角大楼 6.2 亿美元有条件贷款承诺及商务部 5,000 万美元股权投资；卡兹资源获最高 16 亿美元初步支持意向。议员质疑相关交易涉及利益输送。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261110_2942192.html',
                '自然资源部', '11-10',
                '唐菊兴：紧盯斑岩类型，我国找铜大有可为',
                '中国工程院院士唐菊兴表示，我国铜精矿外采率已达 75%，斑岩—矽卡岩—浅成低温热液成矿系统是铜矿增储绝对主力；一台 AI 训练服务器用铜 15—30 公斤，为普通服务器的 3—6 倍；新矿床从发现到投产约需 17 年，有效产能不足是主要矛盾。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202611/t20261110_10359565.htm',
                '全球矿产资源信息系统', '11-10',
                '澳大利亚拉斯普锌矿深部见高品位勘探目标',
                'Broken Hill Mines 为澳大利亚新南威尔士州拉斯普矿山深部 Plimer A Lode 设定勘探目标：矿石量 1,320 万—1,710 万吨，锌当量品位 8.4%—12.5%，银当量品位 291—432 克/吨，平均真厚度 12 米；靶区走向长 1,600 米、向北仍有 2,000 余米未验证，不含现有 480 万吨、9.2% 锌当量资源量。')),

    (CAT_ZK, ni('https://www.mining.com/gunnison-hits-rich-copper-and-zinc-in-arizona',
                'MINING.COM', '11-11',
                'Gunnison 亚利桑那 Strong & Harris 矿床确认高品位铜锌带',
                'Gunnison Copper（TSX: GCU；NYSE-A: GUNN）在其亚利桑那州 Strong & Harris 矿床确认一条高品位铜锌带，正评估增建选厂，为其开发方案增加一条加工路径。',
                orig_title='Gunnison hits rich copper and zinc in Arizona')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/us-critical-minerals-funding-to-withstand-congressional-shift-advisers-say',
                'MINING.COM', '11-11',
                '顾问机构：美关键矿产资金料挺过国会变局',
                'Clark Street Associates 认为，即便民主党掌控国会，华盛顿对关键矿产、采矿、加工与本土制造的投资势头仍将延续，此前已拨付的资金与相关授权构成缓冲。',
                orig_title='US critical minerals funding to withstand congressional shift, advisers say')),

    (CAT_GJ, ni('https://www.mining.com/market-volatility-adds-new-hurdle-to-critical-minerals-investment-report',
                'MINING.COM', '11-11',
                '报告：价格波动成为关键矿产投资新障碍',
                '一份新报告显示，至少四分之一的储能开发商、投资者与矿企表示，关键矿产价格波动使项目难以启动，融资成本上升，开发商被迫重新考虑供应链布局。',
                orig_title='Market volatility adds new hurdle to critical minerals investment: report')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/OPAPJSTPELWGAGG26MZQ3U7KTTYUQHLPSZB327Q-world-bank-sees-gold-holding-above-4000-through-2028-but-warns-silver-faces-steeper-correction',
                'SMM 国际站', '11-06',
                '世行：金价 2028 年前守在 4,000 美元上方，白银回调更深',
                '世界银行 10 月《商品市场展望》预测金价今年均价 4,600 美元/盎司、同比涨 33.6%，2027 年降 7.6% 至 4,250 美元，2028 年再降 5.9% 至 4,000 美元；报告同时警告白银面临更深回调。',
                orig_title='World Bank sees gold holding above $4,000 through 2028, but warns silver faces steeper correction')),

    (CAT_GJ, ni('https://news.smm.cn/news/G5KYLOAWB6XTZE7AWWAW7FRSR6Y36MASCWF5MQQ',
                '上海有色网', '11-10',
                '行业专家警告：印度锂、镍精炼计划面临原材料瓶颈',
                '多位行业人士在印度关键矿产精炼讨论中指出，印度锂、镍精炼计划面临原料供应瓶颈，建议配套电价低于 0.05 美元/千瓦时、原材料零关税进口及 90% 以上回收率管理等运营措施；并称澳大利亚、智利可成为重要锂供应国，印尼仍是主要镍来源。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/M7IR324M56USM4V7QVR5OU7IFP5N4FPIXV6RAMA-smm-analysis-australian-lithium-miners-shift-focus-from-capacity-growth-to-cost-competition',
                'SMM 国际站', '11-06',
                '澳洲锂矿商从扩产转向成本竞争',
                '澳矿季报显示锂精矿成本分化加剧：Greenbushes 现金成本约 418 澳元/吨，Pilgangoora 产量创 26.76 万吨纪录、FOB 成本降至 539 澳元/吨（环比降 12%），Wodgina 约 674 澳元/吨；Mt Marion 升至 1,029 澳元/吨，重启中的 Bald Hill 约 1,498 澳元/吨。',
                orig_title='[SMM Analysis] Australian Lithium Miners Shift Focus from Capacity Growth to Cost Competition')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261110_10359566.htm',
                '全球矿产资源信息系统', '11-10',
                '克里蒂卡尔金属 500 万澳元入股巴西稀土项目',
                '美国上市的克里蒂卡尔金属（Critical Metals Corp）将通过子公司以 500 万澳元认购动力矿产（Power Minerals）私募股份，交易后持股约 8%、成为战略股东；后者在巴西米纳斯吉拉斯州运营铁山（Morro do Ferro）稀土项目，含镨钕镝铽等永磁稀土元素。')),

    (CAT_MA, ni('https://news.smm.cn/news/AFHEVRAOTWUZYVWPZYFLZSIZ7MAAUO4NUNRPYMA',
                '上海有色网', '11-05',
                'IFC 与 Appian 的 10 亿美元矿业基金已部署 70%',
                'Appian Capital Advisory 称，国际金融公司（IFC）2025 年设立的 10 亿美元矿业投资工具已有约 70% 投出，落入加纳 Asante Gold 金矿、纳米比亚 Omico Copper 铜项目与巴西 Atlantic Nickel 镍铜钴项目；公司预计年底前投完剩余资金。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.mining.com/discovery-beats-forecasts-despite-higher-gold-costs',
                'MINING.COM', '11-10',
                'Discovery 三季度盈利超预期，Porcupine 拟扩产翻倍',
                'Discovery Mining 三季度调整后盈利 8,300 万美元、每股 10 美分，较低折旧抵消 Porcupine 矿山成本上升；公司计划通过扩建现有矿山、重启 Dome 露天矿，把 Porcupine 年产金量提高一倍以上。',
                orig_title='Discovery beats forecasts despite higher gold costs')),

    (CAT_HY, ni('https://www.mining.com/allied-gold-pours-first-gold-at-ethiopias-kurmuk-mine',
                'MINING.COM', '11-10',
                'Allied Gold 埃塞俄比亚 Kurmuk 金矿产出首金',
                'Allied Gold（TSX、NYSE: AAUC）埃塞俄比亚 Kurmuk 金矿产出首金，成为公司最新且成本最低的运营矿山；公司目标 2029 年实现年产金约 80 万盎司。',
                orig_title='Allied Gold pours first gold at Ethiopia’s Kurmuk mine')),

    (CAT_HY, ni('https://news.smm.cn/news/PTG2RMJBBXAQZL76Q6SIZY4VEAMFF2YGWCICPZQ',
                '上海有色网', '11-11',
                '天赐材料三年向亿纬锂能供 45 万吨电解液',
                '11 月 5 日天赐材料公告，全资子公司九江天赐与亿纬锂能签订供货协议，2027—2029 年预计供应电解液 45 万吨，按需求预测上下浮动 20% 执行，协议有效期至 2029 年 12 月 31 日；公司称若充分履行将对三年业绩产生积极影响。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475307',
                '中国有色金属报', '11-10',
                '豫光 39 亿元稀贵金属材料智造项目开工',
                '11 月 6 日河南豫光金铅先进稀贵金属材料智造项目开工，总投资 39 亿元，依托自主「新一代绿色高效提炼稀贵金属技术」，系统成本降低 26% 以上、综合能耗降低 25% 以上、年碳减排 3.35 万吨以上，废水实现零外排。')),
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
    ('海关总署', CAT_SC),
    ('BMI', CAT_SC),
    ('LME 基本金属', CAT_SC),
    ('稀土出口管制', CAT_ZC),
    ('加拿大', CAT_ZC),
    ('民主党', CAT_ZC),
    ('唐菊兴', CAT_ZK),
    ('拉斯普', CAT_ZK),
    ('Gunnison', CAT_ZK),
    ('Clark Street', CAT_GJ),
    ('价格波动', CAT_GJ),
    ('世行', CAT_GJ),
    ('印度', CAT_GJ),
    ('澳洲锂矿', CAT_GJ),
    ('克里蒂卡尔', CAT_MA),
    ('Appian', CAT_MA),
    ('Discovery', CAT_HY),
    ('Allied Gold', CAT_HY),
    ('天赐材料', CAT_HY),
    ('豫光', CAT_HY),
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
