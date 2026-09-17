# -*- coding: utf-8 -*-
"""
生成 2026-09-18 矿业资讯速览 index.html
- 09-17 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-20）回补历史条目
- 换入 09-17~09-18 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-17 收盘 + LME 09-16 收盘（东财日K末点，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表
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

REPORT = '2026-09-18'
GRAB = '2026-09-18'
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
                         r'\g<1>2026年09月18日 星期五', html)
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

# ============ 4. 今日新增条目（09-17~09-18 抓取，均逐源核实真实发布日期） ============
# cnmn 列表日期失真第 6 次复现：候选池 96 条标 09-18，实为 08-25~09-17
# （474005/474000/474010/473992/474019 实为 09-15，474081/474087/474089/474090/474097/474099 实为 09-17）。
# 故选条前逐条抓详情页核过真实日期，chinania/geoglobal/mining.com 的日期取自 URL 或 RSS，可靠。
new_items = [
    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474005',
                '中国有色金属报', '09-15',
                '《矿产资源对外合作可持续发展自律倡议》发布',
                '9 月 10 日，中国五矿化工进出口商会在 2026（第二十八届）中国国际矿业大会「绿色矿产国际经贸合作交流活动」上发布《矿产资源对外合作可持续发展自律倡议》。该倡议由中国五矿化工进出口商会、中国矿业联合会、中国钢铁工业协会及近 30 家行业企业共同发起，旨在形成中国矿产供应链对外合作领域共同遵循的行业行为规范。倡议覆盖境外投资贸易、勘探开发、冶炼加工、金属深加工、再生矿产回收及上下游供应商与承包商，推动可持续发展要求融入投资决策、项目建设、生产运营和供应链管理全过程。')),
    (CAT_ZC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474000',
                '中国有色金属报', '09-15',
                '自然资源部发布第三批矿区生态修复典型案例 24 个',
                '9 月 11 日，2026（第二十八届）中国国际矿业大会举办矿区生态修复专题论坛，全国第三批矿区生态修复典型案例同期发布。此次发布的 24 个典型案例涵盖不同矿种，覆盖西北生态脆弱区、黄河流域、长江流域等区域，包括废弃矿区、生产矿山、矿业遗迹 3 个类型。自然资源部国土空间生态修复司表示，新修订的《矿产资源法》及其实施条例首次以国家立法形式设立专章，对矿区生态修复制度作出全面系统规定，实现从分散到集成的转变。')),
    (CAT_ZC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474010',
                '中国有色金属报', '09-15',
                '广期所明确多晶硅、碳酸锂新合约手续费与开仓限额',
                '广州期货交易所就多晶硅期货 PS2709、碳酸锂期货 LC2709 合约发布公告，明确两合约交易手续费与开仓限额标准。多晶硅 PS2709 合约交易手续费为成交金额的万分之一、日内平今仓为万分之二点五，非期货公司会员或客户单日开仓量不得超过 200 手；碳酸锂 LC2709 合约分别为万分之一点六和万分之三点二，单日开仓量不得超过 400 手。套期保值交易、做市交易的单日开仓数量不受上述标准限制。')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474081',
                '中国有色金属报', '09-17',
                '我国面向全球首发「智能填图」系统 重塑地质调查作业流程',
                '9 月 11 日，自然资源部在 2026（第二十八届）中国国际矿业大会上面向全球首次正式发布「智能填图（AI-GeoMapping）」系统。该系统由中国地质调查局自主研发，实现智能预研、智能采集、智能成图、智能编图全流程覆盖，可自动建立地质格架、划分填图单位、识别地质界线与接触关系、圈定火山机构、揭示隐伏地质体，并自动生成路线图、平面图、剖面图、柱状图、立体图与专题图等专业图件及配套报告。系统支持云端数据汇聚与模型动态更新，可实现同比例尺地质图智能接图、大比例尺到小比例尺智能缩编，并提供中英文等多语言输出。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202609/t20260917_10316045.htm',
                '全球矿产资源信息系统', '09-17',
                '澳大利亚诺斯曼金矿资源量增至 180 万盎司 增长一倍',
                '据 Miningnews.net 网站报道，辛克莱尔黄金公司（Sinclair Gold）在澳大利亚的诺斯曼（Norseman）项目金资源量增至 180 万盎司，较今年 2 月公布的 91.5 万盎司（品位 1.2 克/吨）增长一倍。目前该项目仍有 5 台钻机在施工，公司预计在本财年底将再次更新资源量。')),
    (CAT_ZK, ni('https://www.mining.com/newcores-wide-gold-hit-boosts-enchi-plan-in-ghana',
                'MINING.COM', '09-17',
                'Newcore 加纳 Enchi 项目见 69 米厚矿段 金品位 2.59 克/吨',
                'Newcore Gold 在加纳 Enchi 金矿项目 Boin 矿段打出迄今最宽最强矿段之一：钻孔 KBRC411 自 58 米深处见矿 69 米、金品位 2.59 克/吨，其中自 59 米见矿 24 米、品位 6.41 克/吨；另一钻孔 KBRC414 自 70 米见矿 32 米、品位 0.83 克/吨，其中含 6 米厚、品位 3.37 克/吨矿段。公司称该结果为未来矿山方案优化、把高品位矿化纳入后续研究提供了空间。此次公布的 7 个反循环钻孔共 960 米、覆盖 1.9 公里走向，全部见矿，最大垂深 125 米。',
                orig_title='Newcore’s wide gold hit boosts Enchi plan in Ghana')),
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260916_2938488.html',
                '自然资源部', '09-16',
                '自然资源部开展黄岩岛海域多学科综合地质调查',
                '为全面掌握我国管辖海域基础地质要素与生态环境状况，自然资源部中国地质调查局「海洋地质十号」船于 8 月 11 日至 9 月 8 日在我国黄岩岛海域开展了多学科综合地质调查。本次调查聚焦基础地质与生态状况摸底，成果将为该海域地质认识与海洋管理提供基础资料支撑。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104120543',
                '上海有色网', '09-17',
                'SMM 日评：美元下跌金属涨跌互现 沪铅锡镍涨逾 1%',
                'SMM 日评显示，9 月 17 日美元走弱，有色金属呈涨跌互现格局，沪铅、沪锡、沪镍涨幅均逾 1%，沪铜上涨 1%，碳酸锂涨超 3%。美元回落对以美元计价的基本金属形成一定支撑，但品种间分化明显，铅、锡、镍与锂表现强于板块整体。')),
    (CAT_SC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474089',
                '中国有色金属报', '09-17',
                '伦铝库存再创历史新低 沪铝库存连降 13 周',
                '上期所数据显示，9 月 11 日当周沪铝库存继续下降，已连降 13 周，周度库存下降 4.67% 至 347683 吨，降至 6 个半月以来新低。伦敦金属交易所铝库存自去年 11 月以来持续下滑，较年初下降逾五成，最新库存水平 243600 吨，再创新低。报道指出，LME 铝库存去化放缓并非海外供应格局扭转，而是库存结构性缺陷突出——剩余可交割仓单高度集中于俄铝，叠加纽铝库存仅小幅增至 1380 吨，全球显性库存持续收缩为铝价提供底部支撑。')),
    (CAT_SC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474099',
                '中国有色金属报', '09-17',
                '中国钨钼产业 8 月景气指数 52.8 仍处「偏热」区间',
                '中国钨钼产业月度景气指数监测结果显示，2026 年 8 月中国钨钼产业景气指数为 52.8，较 7 月回落 3.1 个百分点，仍处于「偏热」区间；先行指数为 71.2，较 7 月回落 2.4 个百分点；一致指数为 73.9，较 7 月回落 2.3 个百分点。构成景气指数的 9 项指标中，钨钼价格、出口额、主营业务收入和利润总额 4 项处于「偏热」区间，粗钢产量与钨钼生产指数 2 项处于「偏冷」区间。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0917/62019.html',
                '中国有色金属工业协会', '09-17',
                '云南铜业碳足迹认证实现全部外销终端产品覆盖',
                '云南铜业推进所属企业产品碳足迹认证，绿色低碳管理从「企业绿色」向「产品绿色」延伸。东南铜业于 2025 年 12 月率先完成阴极铜产品碳足迹认证；2026 年认证全面提速，赤峰云铜、滇中有色、西南铜业相继完成阴极铜产品认证，易门铜业完成阳极铜产品认证，昆明铜业完成铜排、电工圆线、电工用铜线坯、上引无氧铜线坯等 4 种铜加工产品认证，西南铜业同步完成硫酸产品认证。至此云南铜业全部外销终端产品品类实现碳足迹认证全覆盖。')),
    (CAT_HY, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474097',
                '中国有色金属报', '09-17',
                '中条山集团以尾矿为原料开辟文创与技术服务双赛道',
                '中条山集团旗下山西舜王建筑工程有限公司把铜尾矿砂加工成砚台、香薰罐与文创摆件等产品，走出「文化创意 + 技术服务」双赛道。企业将原本堆存的铜尾矿砂经脱模、修边、打磨、上色等工序制成纹理天然的文创坯体，在消化尾矿存量的同时形成新的产品线，为尾矿资源多元利用提供了可复制的样本。')),
    (CAT_HY, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=473992',
                '中国有色金属报', '09-15',
                '嘉能可科技重启中国本土化运营 亮出三大矿物加工技术',
                '在 9 月 10 日至 12 日举行的 2026 中国国际矿业大会期间，嘉能可科技（Glencore Technology）正式宣布重启中国本土化运营，将经全球矿山验证的矿物加工技术方案引入国内。本次展示超细研磨、高效浮选、难处理矿氧化浸出三大技术，涵盖 IsaMill 艾萨磨机、Jameson Cell 詹姆森浮选机与 Albion Process 阿尔比恩工艺，覆盖磨矿、浮选、浸出关键工序。其中艾萨磨机已在 23 个国家实现 144 套金属矿工业应用，詹姆森浮选机全球累计装机 500 台，阿尔比恩工艺针对难处理硫化精矿浸出回收率可达 99% 以上。')),
    (CAT_HY, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474019',
                '中国有色金属报', '09-15',
                '明月湖实验室研制镁合金电驱壳体 整体减重 30%',
                '明月湖实验室联合重庆卓通汽车工业有限公司研制出高性能镁合金电驱壳体，产品整体减重 30%，预计 2027 年上半年实现量产。研发团队从材料、结构、工艺三方面攻坚：材料端通过稀土元素掺杂与多元微合金化，综合性能较传统方案提升约 20%；结构端依托拓扑优化迭代设计，同等电量下百公里电耗可降低 4% 至 6%；工艺端采用半固态压铸技术提升致密度与尺寸精度。产品经多层防腐工艺处理，盐雾试验时长超 1080 小时。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260917_10316044.htm',
                '全球矿产资源信息系统', '09-17',
                '刚果（金）上半年铜出口 172 万吨创新高 钴出口降 6.4%',
                '据矿业周刊（Miningweekly）援引路透社报道，刚果（金）矿业部上半年统计报告显示，1—6 月该国铜出口量从上年同期的 165 万吨增至 172 万吨，创历史新高，其中出口至美国和欧洲的占比较 2025 年增长一倍。同期钴出口量从 43930 吨降至 41140 吨，降幅 6.4%，主要因金沙萨实施配额制度。刚果（金）是世界最大产钴国和第二大产铜国，正寻求关键矿产出口多元化。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260917_10316043.htm',
                '全球矿产资源信息系统', '09-17',
                '美国将于几个月内批准深海采矿许可',
                '据矿业周刊（Miningweekly）援引路透社报道，美国内政部长道格·伯古姆（Doug Burgum）在休斯敦举办的 G20 能源部长会议上称，深海开采许可证将在几个月内发放，这是美国以「能源补充」战略扩大本国及其盟友关键矿产供应链的措施之一。报道称，自去年重返白宫以来，特朗普政府一直在推动新兴的深海采矿业，但尚未颁发运营许可证。')),
    (CAT_GJ, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474090',
                '中国有色金属报', '09-17',
                '阿根廷拟将稀土列为国家战略资产',
                '阿根廷众议院矿业委员会同意推进一项法案，拟将稀土列为矿法第 3 条中的一类矿产，并宣布其为国家战略资产。目前至少有 3 项提案正在审查之中，均涉及稀土的法律地位，涵盖铽、镝、钪和钇等永磁体、电动汽车、清洁能源、电子、国防与通信行业的关键材料。各方虽同意立法确定稀土的经济开发地位，但对于是否将稀土纳入大型投资激励制度（RIGI）目录仍存不同意见。')),
    (CAT_GJ, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474087',
                '中国有色金属报', '09-17',
                '美国启动铟锰镁钛 4 种关键金属招标',
                '美国国防部下属国防工业基地联盟发布招标公告，面向其国内企业征集铟、锰、镁、钛 4 种关键金属的投资方案，提交截止日期为 2026 年 9 月 17 日，招标覆盖采矿、选冶、精炼、合金制造到回收的全产业链环节。这是 2025 年中以来该联盟第三次围绕关键矿产和先进国防技术开展投资征集。铟、锰、镁、钛均已被美国地质调查局列入关键矿产清单，此前美国已通过行政令与「金库计划」等推进关键矿产本土化。')),
    (CAT_GJ, ni('https://www.mining.com/critical-metals-says-it-has-cracked-eudialyte-hurdle-plans-2-2b-a-year-refinery-in-romania',
                'MINING.COM', '09-16',
                'Critical Metals 破解异性石冶炼难题 拟在罗马尼亚建精炼厂',
                'Critical Metals（Nasdaq: CRML）宣布其专利申请中的工艺可溶解格陵兰 Tanbreez 项目逾 99% 的异性石（eudialyte）精矿，并回收 19 种超高纯度稀土与关键金属产品，破解了异性石在冶金过程中易形成难过滤硅胶的行业难题。公司计划在罗马尼亚建设精炼厂，初步研究设定处理能力最高 10 万吨/年异性石精矿，年产约 27943 吨稀土及关键金属产品，CAPEX 约 18.5 亿美元，年收入约 22 亿美元、NPV10 约 45 亿美元、IRR 约 55%、投资回收期约 2 年。',
                orig_title='Critical Metals says it has ‘cracked’ eudialyte hurdle, plans $2.2B a year refinery in Romania')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104120869-fatal-accident-at-korea-zincs-onsan-smelter-involved-the-roasting-system-area-output-impact-remains-to-be-seen',
                'SMM 国际站', '09-17',
                '韩国锌业温山冶炼厂焙烧系统发生致命事故 产量影响待观察',
                '据 SMM 报道，9 月 16 日韩国锌业（Korea Zinc）蔚山温山冶炼厂 2 厂区发生坠落事故，一名承包商工人在冷凝室屋顶安装通风风机时身亡。事故发生地位于锌冶炼流程前端焙烧与硫酸系统区域，属外围施工，未损坏主体冶炼设备，但焙烧—制酸系统一旦停产，锌焙烧炉将无法正常运行。目前公司尚未发布减产、检修或停产通知，是否下达停工令及范围尚不明确。以该厂约 64 万吨/年名义产能测算，停产 3 至 7 天对应数千吨量级影响，仅为粗略参考。')),
    (CAT_GJ, ni('https://www.mining.com/almonty-to-supply-sandvik-tungsten-from-spanish-mine-tailings',
                'MINING.COM', '09-17',
                'Almonty 将从西班牙尾矿向山特维克供应钨',
                'Almonty Industries（Nasdaq: ALM）与瑞典山特维克（Sandvik）旗下 Wolfram Bergbau und Hütten 签署长期供货协议，由后者采购从 Almonty 西班牙 Los Santos 矿尾矿中回收的钨，协议采用照付不议（take-or-pay）结构。公司称该方案将比新建传统矿山更快形成钨精矿供应。中国约占全球钨产量的 80%，在 2025 年收紧出口管制后，欧美用户加快寻找替代来源，欧盟已将钨列入关键矿产联合采购计划。',
                orig_title='Almonty to supply Sandvik tungsten from Spanish mine tailings')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-18/1225570881.PDF',
                '巨潮资讯网', '09-18',
                '藏格矿业联手云图控股 1.71 亿美元收购刚果（布）钾盐项目 92% 股权',
                '藏格矿业（000408）公告，全资子公司藏格矿业发展拟通过藏格矿业国际与云图控股全资子公司应城市新都化工共同出资设立新加坡控股公司藏格联合资源（藏格国际 75%、新都化工 25%），由该公司以 171046592 美元（折合人民币约 11.57 亿元，不含交易税费）收购 Kanga Potash 92% 股权。标的核心资产为刚果共和国境内的 Kanga 钾盐矿采矿权及 Loango 钾盐矿勘探权。交易完成后藏格矿业将间接持有 KP 公司 69% 股权，按 75% 持股测算需承担投资 128284944 美元（约 8.68 亿元）；云图控股按 25% 对应总投资 42761648 美元（约 2.89 亿元）。两项议案均已获各自董事会审议通过，尚需境内外监管审批与备案。',
                embed='pdf')),
    (CAT_MA, ni('https://www.mining.com/luca-adds-3rd-mexican-property-in-60m-agnico-deal',
                'MINING.COM', '09-17',
                'Luca Mining 以 6000 万美元收购 Agnico 墨西哥金银铜项目',
                'Luca Mining（TSXV: LUCA）拟以 6000 万美元从 Agnico Eagle Mines 收购墨西哥哈利斯科州 El Barqueño 金银铜项目，由此获得在墨第三个资产。该矿权面积 320 平方公里，位于瓜达拉哈拉以西约 100 公里；交易初期无需现金支付，交割时向 Agnico 发行 1000 万美元股票，另设 3000 万美元钻探与商业生产挂钩的递延付款及 2000 万美元产量挂钩付款，Agnico 保留 2% 冶炼净收益权利金。项目历史估算（2025 年 12 月数据）含 843 万吨指示资源、金品位 1.24 克/吨、银 5.15 克/吨、铜 0.21%。项目部分矿权现受当地生态规划限制、尚未获批勘探钻探。',
                orig_title='Luca Mining adds 3rd Mexican property in $60M Agnico deal')),
    (CAT_MA, ni('https://www.mining.com/web/kcm-signs-498-million-deal-with-chinese-firm-for-copper-recovery-plant/',
                'MINING.COM', '09-17',
                '赞比亚 KCM 与中国恩菲签 4.98 亿美元铜尾矿回收厂协议',
                '韦丹塔（Vedanta）旗下孔科拉铜矿公司（KCM）与中国恩菲工程（NERIN Engineering）签署 4.98 亿美元协议，将在赞比亚铜带省钦戈拉建设铜回收厂，从现有矿山尾矿中提取金属，预计年增铜产量 7 万吨。该厂采用浸出技术处理矿山废料，公司称将成为非洲同类规模最大的设施。项目是 KCM 扩产计划与赞比亚铜产量目标的一部分——赞比亚计划到 2031 年把年铜产量从 2025 年的 890346 吨提升至 300 万吨。中国恩菲将提供设计、采购、施工及调试、性能测试与培训等支持。',
                orig_title='KCM signs $498 million deal with Chinese firm for copper recovery plant')),
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
