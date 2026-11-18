# -*- coding: utf-8 -*-
"""
生成 2026-11-19 矿业资讯速览 index.html（周四）
- 11-17 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-16）回补历史条目
- 换入 11-19 采集的 11-17 至 11-19 条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-17 收盘，全部由
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

REPORT = '2026-11-19'
GRAB = '2026-11-19'
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
                         r'\g<1>2026年11月19日 星期四', html)
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
    (CAT_SC, ni('https://www.mining.com/copper-price-craters-as-ai-tariff-trades-unwind-and-asia-copper-week-hears-of-recessionary-like-demand',
                'MINING.COM', '11-18',
                '铜价跌至 4 月以来最低，顶级生产商一月市值蒸发 1,860 亿美元',
                '11 月 18 日 Comex 12 月期铜一度跌 6.7% 至 5.5835 美元/磅（12,309 美元/吨），为 4 月初以来最低，午间成交已逾 8.2 万手；LME 三个月铜跌 3.4% 至 12,772.50 美元/吨。AI 相关交易与关税预期降温、美元走强叠加关键技术位失守触发抛售，铜价三周累计跌 16%、较 9 月 9 日纪录低 19%，年内 22% 涨幅回吐，大型铜企股价跌 5%~9%、市值一月蒸发 1,860 亿美元。',
                orig_title='Copper price craters as AI, tariff trades unwind, wiping $186 billion off top producers in a month')),

    (CAT_SC, ni('https://news.metal.com/newscontent/IRU7AYAV53TZPXT2QMJFVBVM52GEXI2VAUN7UZI-tin-falls-106-on-fed-bets-brazil-export-revenue-peaks',
                'SMM 国际站', '11-19',
                '加息预期升温，LME 锡 30 天跌 10.6% 至 45,059 美元/吨',
                'LME 三个月锡 11 月 17 日收 45,059 美元/吨，30 天累计跌 10.6%，为 3 月以来最低，11 月 18 日盘中再跌 6% 至 42,175 美元/吨。市场对 12 月加息定价概率达 95%，美元指数升至 2025 年 4 月以来最高；LME 锡库存增 25 吨至 3,600 吨，现货对三个月升水由 687.01 美元/吨降至 244.76 美元/吨。巴西 10 月出口精锡 925 吨、均价 54,123 美元/吨、收入 5,010 万美元。',
                orig_title='Tin falls 10.6% on Fed bets; Brazil export revenue peaks')),

    (CAT_SC, ni('https://news.metal.com/newscontent/UKNYIGBGGTXPXTGYODZCSQNNK3YCBJD4HBAHIJI-nickel-jumps-38-as-anglo-flags-brazil-ferronickel-closure-risk',
                'SMM 国际站', '11-19',
                '印尼减产预期叠加巴西镍厂关停风险，LME 镍单日涨 3.8%',
                'LME 三个月镍 11 月 17 日涨 3.8% 至 16,462 美元/吨，为当日唯一明显上涨的基本金属。Anglo American 致函欧洲不锈钢客户称，若欧盟否决其以约 5 亿美元向 MMG 出售巴西镍业务，将把 Barro Alto 与 Codemin 两座铁镍厂转入维护并最终关闭，两厂 2025 年镍金属产量合计 3.97 万吨；欧盟委员会预计 12 月 21 日前作出决定。',
                orig_title='Nickel jumps 3.8% as Anglo flags Brazil ferronickel closure risk')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202611/t20261113_2942491.html',
                '自然资源部', '11-13',
                '四部门公告新一批国家级绿色矿山名单，296 家矿山入选',
                '11 月 10 日自然资源部、生态环境部、国家金融监督管理总局、国家林业和草原局联合发布《关于新一批国家级绿色矿山名单的公告》。经省级推荐、审核论证、抽查核实与社会公示，共 296 家矿山通过遴选纳入国家级绿色矿山名录；名录实行动态管理，不符合要求的矿山将被及时移出。')),

    (CAT_ZC, ni('https://news.smm.cn/news/IXHW3TCYCOBDPSM7L7QXRINFCLNEEZGFNRPCP3Y',
                '上海有色网', '11-19',
                '印尼要求采矿收益至少七成归国家，必要时直接控股',
                '印尼总统普拉博沃 11 月 14 日宣布大幅收紧矿业利益分配，要求所有采矿许可证项目至少 70% 收益归国家所有，必要时政府将直接持有矿业企业控股权，并已向能矿部长下达指令。总统府说明该 70% 针对采矿许可证管理产生的收益而非产量本身；同时所有出口须经政府指定机构统一办理，以防瞒报数量。具体计算方式与国家控股触发条件尚未出台。')),

    (CAT_ZC, ni('https://news.smm.cn/news/4IK53RICMZKX26CY75GWOWGABWO6XFJQJ336EIY',
                '上海有色网', '11-19',
                '广期所氢氧化锂期货 11 月 26 日上市，首批 6 个合约',
                '广期所 11 月 13 日发布通知，氢氧化锂期货合约自 2026 年 11 月 26 日起上市交易，首批合约为 LI2706 至 LI2711 共 6 个。上市首日交易保证金为合约价值的 11%、涨跌停板幅度为挂牌基准价的 18%，次日起涨跌停板为上一交易日结算价的 9%，交易手续费为成交金额的万分之一；氢氧化锂期权同日发布上市有关事项。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/QHSBBEW5BEDYDY42WSLEDQIIQO2HRWGX2P4M6UQ',
                '上海有色网', '11-19',
                '印度斯坦锌业拟投约 85 亿美元，金属产能翻倍至 200 万吨',
                '印度斯坦锌业 11 月 16 日表示，计划未来 3 至 5 年投资约 8,000 亿卢比（约 85 亿美元），将金属年产能由 110 万吨提升至 200 万吨，其中新增锌冶炼产能 76.5 万吨、铅冶炼产能 20 万吨，资金来自内部积累与举债。公司预计未来 5 至 10 年印度锌需求翻番，目标将生产成本控制在 1,000 美元/吨以下（本财年上半年为 776 美元/吨）。')),

    (CAT_HY, ni('https://news.smm.cn/news/YKW36B3JBVH4EZZQLG5EO4UIN3UJHJXQARX5NCI',
                '上海有色网', '11-19',
                '美两家开发金融机构放弃为哈萨克斯坦钨矿提供 16 亿美元融资',
                '据路透社报道，美国进出口银行（EXIM）与美国国际开发金融公司（IDFC）都不会为哈萨克斯坦一处钨矿项目提供合计约 16 亿美元资金。IDFC 官员称协议不具约束力、不应理解为供资承诺，项目尚未通过其四阶段审查的第一阶段，目前也无在谈交易；此前两家机构曾分别表达约 9 亿美元与 7 亿美元的融资意向。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475392',
                '中国有色金属报', '11-18',
                '前 10 月国内原镁产量 96.12 万吨，同比增长 17.51%',
                '中国有色金属工业协会镁业分会统计，10 月国内原镁产量约 9.1 万吨，环比增 5.69%、同比微降 0.2%；1—10 月累计 96.12 万吨，同比增 17.51%。区域分化持续：陕西累计 66.82 万吨、增 28.65%，山西 13.25 万吨、降 16.98%，内蒙古 2.65 万吨、降 16.93%，新疆 4.84 万吨、增 5.68%。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/dwdt/202611/t20261118_872790.html',
                '中国地质调查局', '11-18',
                '烟台中心在胶东成矿带新发现 5 个金矿（化）点，圈定靶区 10 处',
                '中国地质调查局烟台海岸带地质调查中心「重要金多金属矿集区资源调查评价」项目完成年度野外工作，4 个子项目野外质量检查均获优秀级。累计完成机械岩心钻探 14,191 米、1:5 万矿产地质调查 1,611 平方千米，新发现金矿（化）点 5 个、萤石矿化点 1 个、铜矿化点 1 个、铅锌矿化点 1 个，圈定找矿靶区 10 处；滕家矿区深部见厚大金矿体，前垂柳矿区新发现多层隐伏金矿体及 3 条银铅锌多金属矿化蚀变带。')),

    (CAT_ZK, ni('https://www.mining.com/collective-hits-gold-in-rock-classed-as-waste-at-apollo',
                'MINING.COM', '11-19',
                'Collective 在哥伦比亚 Apollo 矿废石中见厚大金银矿化',
                'Collective Mining（TSX/Nasdaq: CNL）在哥伦比亚 Apollo 矿床拟建采坑内的废石区发现金银矿化：17 个浅部边部钻孔中 15 个见矿超过露天开采边界品位，其中一孔自 3.75 米起见 107.85 米、金 0.79 克/吨、银 14 克/吨，另一孔自 106.5 米起见 146.1 米、金 0.66 克/吨、银 19 克/吨、铜 0.04%，延伸至坑底以下并超出资源边界 60 米。投行认为矿坑边界低估了浅部边部带，把废石转为入选矿石有望改善露采经济性。',
                orig_title='Collective hits gold in rock classed as waste at Apollo')),

    (CAT_ZK, ni('https://www.mining.com/ai-strikes-copper-gold-where-explorers-gave-up-in-1969',
                'MINING.COM', '11-18',
                'Earth AI 复勘澳洲 1969 年放弃区，圈出逾 3 公里铜金铂族矿化',
                '美国 Earth AI 在新南威尔士州 Fontenoy 项目发现延伸逾 3 公里的铜金及铂族金属矿化系统，该区半个多世纪前曾被先行者判为规模小、不连续而放弃。据合作方 Legacy Minerals（ASX: LGM）披露，公司已完成 35 个金刚石钻孔、累计 20,919 米，正推进取得项目 80% 权益并出资补充钻探，以支持按 JORC 标准编制首个资源量估算。',
                orig_title='AI strikes copper-gold where explorers gave up in 1969')),

    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261118_2942791.html',
                '自然资源部', '11-18',
                '「梦想」号完成 2,000 米级深海泥浆回收系统海试，形成自主超深水钻探技术体系',
                '「梦想」号大洋钻探船历时 33 天完成我国首套 2,000 米级深海无隔水管泥浆回收循环钻井系统海试，在南海北部 142.7 米与 2,004.8 米水深完成全流程作业及 5 个回次取心试验，打破同类系统 1,419 米的国际最大作业水深纪录。至此该船 4 种钻探模式全部通过功能验证，取心能力提升至 5,000 米级，可为深海采矿与海洋油气勘查提供装备支撑。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/perpetua-eyes-55-5-million-deal-to-unlock-us-tungsten-supply',
                'MINING.COM', '11-18',
                'Perpetua 洽谈 5,550 万美元钨供应协议，拟锁定一半未来产量',
                'Perpetua Resources（Nasdaq/TSX: PPTA）与一家未披露的航空航天与防务企业签署非约束性备忘录，对方拟以最高 5,550 万美元非股权资金，换取其未来钨产量最多一半的购买权，属公司「工业钨加速计划」（I-TAP）的一部分。10 月公司刚获得美国陆军 DOTC 为期 36 个月、4,000 万美元资助，用于评估在爱达荷 Stibnite 项目生产钨精矿的技术经济可行性。',
                orig_title='Perpetua eyes $55.5 million deal to unlock US tungsten supply')),

    (CAT_MA, ni('https://www.mining.com/general-flash-raises-128-million-to-scale-us-critical-metals-production',
                'MINING.COM', '11-18',
                'General Flash 融资 1.28 亿美元，扩产美国关键金属',
                '马萨诸塞州剑桥市初创公司 General Flash 完成种子轮与 A 轮合计 1.28 亿美元股权融资，投资方包括 Lux Capital、Construct Capital、Lowercarbon Capital 等。公司以闪速电解工艺由金属氧化物直接制取高纯钨、钛、锆、钽及稀土，瞄准美国防务与半导体供应链；美方规定自 2027 年 1 月 1 日起多数关键材料供应链排除中国供应，而中国占全球精炼产能逾 80%。',
                orig_title='General Flash raises $128 million to scale US critical metals production')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261117_10364804.htm',
                '矿业权市场', '11-17',
                '新疆挂牌出让和静县哈尔干金多金属矿等 5 个探矿权',
                '新疆维吾尔自治区公共资源交易中心受自治区自然资源厅委托，以挂牌方式出让和静县哈尔干金多金属矿勘查等 5 个探矿权，报名与竞价均通过自治区公共资源交易平台线上进行。竞买人须为境内注册的营利法人或事业单位法人，且未被列入全国矿业权人勘查开采信息公示系统严重失信主体、信用中国严重失信名单等。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261118_10366140.htm',
                '矿业权市场', '11-18',
                '四川峨边桥儿沟磷铅锌矿勘查探矿权挂牌成交并公示',
                '四川省政务服务和公共资源交易服务中心公示，四川省峨边县桥儿沟磷铅锌矿勘查探矿权挂牌出让成交。成交结果公示期间无异议的，竞得人须在公示结束后 5 个工作日内到四川省自然资源厅办理探矿权出让合同签订事宜，并按合同约定时限申请办理探矿权登记。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/newscontent/HFWEADRVDCWC4ZCBBTPG3RJYHTZLUVPJARXSXTA-smm-analysis-zimbabwe-holds-january-2027-concentrate-export-deadline-sulphate-ramp-up-vs-stockpile-risk',
                'SMM 国际站', '11-18',
                '津巴布韦坚持 2027 年 1 月锂精矿出口禁令，矿企争取推迟至 7 月',
                '津巴布韦矿业与矿业发展部长 Polite Kambamura 11 月 2 日表示，2027 年 1 月起该国只允许出口硫酸锂，过渡期配额将有序管理，并要求 Bikita、Kamativi、Gwanda 三家工厂按期投产。矿业商会委托的调查显示，矿企希望禁令推迟至 2027 年 7 月以完成建厂；预计 2027 年硫酸锂产量 20.8 万吨、锂精矿产量 230 万吨（今年约 220 万吨），若按期执行到 2027 年底精矿库存将达 140 万吨。',
                orig_title='[SMM Analysis] Zimbabwe Holds January 2027 Concentrate Export Deadline: Sulphate Ramp-Up vs Stockpile Risk')),

    (CAT_GJ, ni('https://www.mining.com/central-banks-rethink-gold-as-global-risks-mount',
                'MINING.COM', '11-18',
                'OMFIF：央行重新审视黄金储备，地缘风险权重上升',
                '官方货币与金融机构论坛（OMFIF）报告《持有力：储备、技术与投资者如何重塑黄金市场》基于 2026 年四场闭门工作组会议指出，央行管理黄金储备时正把地缘政治不确定性纳入与传统金融风险并列的考量，储备多元化目标与地缘脆弱性之间的权衡更趋复杂。报告同时提示，代币化等技术手段无法自动复制实物黄金对央行的吸引力。',
                orig_title='Central banks rethink gold as global risks mount')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/7VG5JV3SIUMBQPZSH2O6DYKJEHV7T4DUUL4SCPY-smm-news-zambia-aims-to-boost-ev-and-battery-production-to-maximize-value-from-critical-minerals',
                'SMM 国际站', '11-19',
                '赞比亚招引电池与电动车投资，延长关键矿产价值链',
                '赞比亚发展署（ZDA）在赞比亚矿业 Insaka CEO 圆桌会上呼吁在矿产地附近投资电动车、电池及零部件制造，强调政策可预期与经洛比托走廊出口的增值产品选择，但未公布投资额、产能规模或投产时间。锂已列入赞比亚 2024—2028 年国家关键矿产战略，南部省 Mapatizya 一带见有矿化，仍需商业性验证。',
                orig_title='[SMM News] Zambia Aims to Boost EV and Battery Production to Maximize Value from Critical Minerals')),
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
    ('隔夜金属普跌', CAT_SC),
    ('高盛', CAT_SC),
    ('锡现货升水', CAT_SC),
    ('再生资源回收体系', CAT_ZC),
    ('印度', CAT_ZC),
    ('加拿大', CAT_ZC),
    ('铜冶炼产能', CAT_HY),
    ('智利铜产量', CAT_HY),
    ('原镁产量', CAT_HY),
    ('中国铜业', CAT_ZK),
    ('阿米代尔', CAT_ZK),
    ('梦想', CAT_ZK),
    ('General Flash', CAT_GJ),
    ('Perenti', CAT_GJ),
    ('津巴布韦', CAT_GJ),
    ('欧盟 46 个', CAT_GJ),
    ('天赐材料', CAT_MA),
    ('AngloGold', CAT_MA),
    ('红豆山', CAT_KQ),
    ('桥儿沟', CAT_KQ),
    ('老熊塘', CAT_KQ),
    ('梅花岭', CAT_KQ),
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
