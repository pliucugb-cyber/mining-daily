# -*- coding: utf-8 -*-
"""
生成 2026-09-12 矿业新闻日报 index.html
- 09-11 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-14）回补历史条目
- 换入 09-12 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-11 收盘 + LME 09-11 收盘，全部由 price_history_detail.json /
  lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
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
)
from functools import partial


SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-12'
GRAB = '2026-09-12'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html = re.sub(r'<title>\d{4}-\d{2}-\d{2}</title>', '<title>%s</title>' % REPORT, html)
html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月12日 星期六', html)
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
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down'))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

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
lme_html = ''.join(card(*c) for c in lme_list)

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

# ============ 4. 今日新增条目（09-12 抓取，均逐源核实） ============
new_items = [
    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104111528-alchemy-resources-starts-drilling-copper-gold-targets-at-yellow-mountain',
                'SMM 国际站', '09-11',
                'Alchemy 在新南威尔士州 Yellow Mountain 铜金靶区开钻 最多 15 孔',
                '澳大利亚 Alchemy Resources 于 9 月 11 日宣布，已在新南威尔士州 Yellow Mountain 与 Overflow 项目启动反循环钻探，本轮计划施工最多 15 个钻孔并预计约 3 周完成。持股 80% 的 Yellow Mountain 项目将验证已知铜金与多金属矿化的延伸范围，并测试两个从未钻探过的地球物理靶区；该矿区此前钻探曾见 113 米、铜当量品位 1.17% 的矿化段（含铜 0.33%、金 0.37 克/吨、银 24.3 克/吨、铅 0.86%、锌 1.23%）。Overflow 项目目前控制约 34.2 万盎司金当量推断资源量，本轮同样沿走向与深部追索矿化延伸。',
                orig_title='Alchemy Resources Starts Drilling Copper-Gold Targets at Yellow Mountain')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202609/t20260911_10312021.htm',
                '全球矿产资源信息系统', '09-11',
                '刚果（金）马库库铜矿资源量大增 30% 至约 1200 万吨铜金属',
                '艾芬豪矿业正加快实施其在刚果（金）西福尔兰项目马库库（Makoko）铜矿的工作计划，目前铜金属资源量约 1200 万吨，较 2025 年估算值增长 30%，正在进行的钻探有望继续扩大资源量。该公司 9 月 8 日宣布，马库库矿区推定矿石资源量 4200 万吨、铜品位 2.66%；推测矿石资源量 6.12 亿吨、品位 1.8%。艾芬豪认为马库库是过去 10 年全球规模最大、品位最高的铜发现，此次资源量更新正值铜价高企、大型发现减少引发未来供应担忧之际。')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938171.html',
                '自然资源部', '09-11',
                '绿色矿山建设规范、固体矿产绿色勘查规范等系列国家标准发布',
                '9 月 11 日在中国国际矿业大会绿色发展成果发布会上，一批国家级、国际级地质矿业标准集中发布。自然资源部与国家市场监督管理总局联合发布的《绿色矿山建设规范》系列国家标准共 10 个部分，实现煤炭、陆上油气田、黑色金属、有色金属、化工、非金属、黄金、砂石、水泥用灰岩、地热矿泉水等主要矿产类型全覆盖，紧扣资源开采、资源综合利用、绿色低碳、生态修复、科技创新与规范管理、矿区环境六个维度设置差异化要求。同日发布的《固体矿产绿色勘查规范》是我国固体矿产勘查领域首项绿色勘查专项国家标准，覆盖绿色勘查设计、驻地建设、道路修建、探矿工程施工、“三废”处置、场地生态恢复、监督检查与项目验收全流程，对浅井、槽探、坑道、钻探等工程提出占地约束、低扰动工艺、污染防控、分区复绿等量化指标。此外还发布了《岩心数字化技术规程》英文版标准，以及我国牵头多国编制的全球岩溶领域首项国际标准 ISO 8616《岩溶关键带监测技术规范》。')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938172.html',
                '自然资源部', '09-11',
                '全国第三批矿区生态修复典型案例发布 共 24 个',
                '9 月 11 日，2026 中国国际矿业大会矿区生态修复专题论坛举办，全国第三批矿区生态修复典型案例同期发布，共 24 个，涵盖不同矿种，覆盖西北生态脆弱区、黄河流域、长江流域等区域，分废弃矿区、生产矿山、矿业遗迹三种类型。其中北京门头沟寨口石灰石废弃矿区修复等 12 个案例展示地方推进历史遗留废弃矿区修复、探索“生态修复+”模式的做法；河北邢台冀中能源邢东矿等 10 个案例展示矿山企业落实法定修复义务、践行“边开采、边修复”；浙江温州苍南矾山国家地质公园矿业遗迹保护等 2 个案例展示矿业遗迹的原址保护与活化利用。据论坛披露，“十四五”期间自然资源部协同财政部在长江、黄河等重要流域及青藏高原、“三北”工程区部署 68 个示范工程，累计下达中央财政奖补资金超 168 亿元，带动全国完成历史遗留废弃矿区修复 335 万亩、超目标任务近 20%。')),
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202609/t20260911_2938173.html',
                '自然资源部', '09-11',
                '《自然资源部关于规范矿业权管理有关事项的通知（征求意见稿）》公开征求意见情况公告',
                '自然资源部发布关于《自然资源部关于规范矿业权管理有关事项的通知（征求意见稿）》公开征求意见情况的公告（索引号 000019174/2026-00040，成文日期 2026 年 9 月 11 日）。该通知为贯彻落实《矿产资源法》《矿产资源法实施条例》起草，旨在规范矿业权管理、推动矿产资源合理开发利用和增储上产、提高矿产资源保障能力。公告就征求意见期间收到的意见与采纳情况作出说明，标志着该规范性文件进入出台前最后阶段。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104086512',
                '上海有色网', '09-12',
                '隔夜行情：沃什放鹰 金银跳水基本金属普跌 伦锡、沪镍跌幅居前',
                'SMM 隔夜行情汇总显示，上周五（9 月 11 日）夜盘贵金属大幅跳水：COMEX 黄金跌 3.43%（当周跌 3.77%），COMEX 白银跌 4.48%（当周跌 3.51%）；国内沪金主连跌 2.65%（当周涨 2.09%，周线六连涨），沪银主连跌 3.62%（当周涨 3.64%，连涨六周）。基本金属普跌，伦锡、沪镍跌幅居前，氧化铝涨超 2%。消息面，美联储主席人选沃什发表偏鹰表态，叠加美国 8 月 PPI 超预期，市场对加息的押注升温，压制有色金属与贵金属估值。')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104111526-chile-july-copper-output-falls-94-yoy-escondida-slumps-221',
                'SMM 国际站', '09-11',
                '智利 7 月铜产量同比降 9.4% Escondida 骤降 22.1%',
                '智利铜业委员会（Cochilco）数据显示，2026 年 7 月智利铜产量同比下降 9.4%。国有 Codelco 产量同比降 5% 至 11.28 万吨；必和必拓控股的全球最大铜矿 Escondida 降幅更大，同比降 22.1% 至 8.94 万吨；英美资源与嘉能可合资的 Collahuasi 产量则同比增 12.3% 至 3.84 万吨。智利国家统计局另报 7 月铜矿产量 403,424 吨，矿业生产指数同比降 7.2%、金属矿业活动降 10.7%，主因铜采选下滑，北部恶劣天气与主力矿山检修亦构成拖累。Cochilco 预计 2026 年智利铜产量约 527 万吨、同比降 2.6%，2027 年回升 5.2% 至约 555 万吨。',
                orig_title='Chile July Copper Output Falls 9.4% YoY; Escondida Slumps 22.1%')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104111445-smm-analysis-drc-cobalt-exports-surge-shifting-near-term-bargaining-power-to-buyers',
                'SMM 国际站', '09-11',
                '刚果（金）钴出口回升 短期议价权转向买方',
                'SMM 分析指出，刚果（金）钴出口正逐步恢复：2026 年上半年该国出口钴金属量 4.11 万吨、同比下降 6.4%，为 2022—2026 年同期最低、较 2024 年峰值低 59.1%；但 6 月氢氧化钴出口环比大增 92.9%，中国 7 月进口钴中间品 1.6 万实物吨。运输滞后是判断后市的关键——经德班港到中国通常需约两个月，遇卡车运力、船期或转运问题可延至近三个月，因此上半年发出的货物将在未来数月集中到港，缓解中国钴原料短缺并把议价权转向买方。钴盐需求疲弱、冶炼利润承压，卖方需让价才能成交；中期供应仍受出口配额与少数生产商发运节奏约束。',
                orig_title='[SMM Analysis] DRC Cobalt Exports Surge, Shifting Near-Term Bargaining Power to Buyers')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/e55b42f6a70e425094b9c792e4ffa6df.html',
                '长江有色网', '09-11',
                '锑价周内持续走强 站稳 105,000 元/吨关口',
                '2026 年 9 月 11 日，长江现货 1# 锑均价报 105,000 元/吨，较上一交易日上涨 1,000 元/吨。本周锑价自 9 月 7 日开启震荡上行通道，周初开盘 102,000 元/吨，全周累计上涨 3,000 元/吨，走出一波单边向上行情，市场做多情绪逐步升温，供需格局对价格形成支撑。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/cab716194e424829ac9b50e51f64385b.html',
                '长江有色网', '09-11',
                '四氧化三钴连续回调 全周累计下跌 19,500 元/吨',
                '2026 年 9 月 11 日，长江综合电池级四氧化三钴均价报 263,500 元/吨，较上一交易日继续下跌 2,500 元/吨。本周该品种走出陡峭的单边下行行情，全周累计下跌 19,500 元/吨。原料端钴中间品供应预期宽松拖累成本支撑，叠加下游需求疲软，短期行情难有起色。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/7d0c122969764db9bf287f47b56cd1aa.html',
                '长江有色网', '09-11',
                '硅料库存持续累积 多晶硅周度下跌 3.48%',
                '2026 年 9 月 11 日，长江综合多晶硅均价报 40,000 元/吨，较上一交易日下跌 50 元/吨。期货盘面波动加剧，多晶硅期货早盘一度跌幅超过 4%，随后探底回升，主力合约收盘下跌 1.49%，周度累计跌幅达到 3.48%。硅料库存持续累积，产业链上下游陷入僵持博弈，短期价格承压运行。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX018/202609/c5ff953db4314b6082f664b5acba93d9.html',
                '长江有色网', '09-12',
                '铅酸电池旺季尾声备货乏力 沪伦比值 8.50 进口窗口关闭',
                '截至 9 月 11 日 12:40，长江现货 1# 铅均价 16,200 元/吨、较前一交易日跌 50 元，区间 16,150~16,250 元；沪铅 2610 合约最新 16,150 元/吨、较昨结上涨 30 元。消费端温吞与海外伦铅坚挺形成内弱外强裂口：LME 伦铅收报 1,901 美元/吨、跌 8 美元/吨，库存连降 9 日，沪伦比值约 8.50，进口窗口关闭；上期所铅库存 73,828 吨持续累积，印证国内供需宽松。铅酸电池传统旺季正步入尾声，下游备货热情未如期升温。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473767',
                '中国有色金属报', '09-07',
                '中国十五冶承建赞比亚卢安夏新矿穆南混合井永久井架吊装就位',
                '当地时间 8 月 14 日，中国十五冶金建设集团承建的赞比亚卢安夏新矿穆南混合井永久井架一对天轮精准吊装就位——下天轮标高 46 米、上天轮标高 52 米，两个直径 4 米、净重 26 吨的天轮嵌入井架顶端。该井架自 7 月 30 日完成 304 吨斜架双桅杆整体吊装，8 月 1 日立架分节对接，至 8 月 14 日双天轮就位，标志这一高原矿区新矿建设的关键节点完成，为后续提升系统安装奠定基础。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473769',
                '中国有色金属报', '09-07',
                '贵州铝厂自研柴油阳极运输车启运哈萨克斯坦',
                '9 月 3 日，贵州铝厂自主研制的柴油阳极运输车完成出厂检验并正式装车发运，目的地为哈萨克斯坦。阳极运输车是电解铝生产的核心专用设备，长期面临高温、粉尘、强磁场、重载等严苛工况，此前国产化程度较低。此次整机出口反映国产电解铝专用装备在可靠性与出口适配方面取得进展。')),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104111423-liaoning-hongda-group-breaks-ground-on-lead-zinc-mining-project-in-kazakhstan',
                'SMM 国际站', '09-11',
                '辽宁宏达集团哈萨克斯坦布赖拜铅锌矿项目开工 一期年产铅锌原料 21 万吨',
                '据外媒报道，中国辽宁宏达集团近日在哈萨克斯坦克孜勒奥尔达州举行布赖拜（Burabay）铅锌采选项目开工仪式。项目建设期两年，计划 2028 年建成；详细地质勘探已完成，平均品位为锌 2.01%、铅 1.62%，深部仍有资源扩大潜力。一期预计年产铅锌原料 21 万吨、回收白银 20 吨，创造当地就业岗位 550 个以上。',
                orig_title='Liaoning Hongda Group Breaks Ground on Lead-Zinc Mining Project in Kazakhstan')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473613',
                '中国有色金属报', '08-31',
                '中铝国际沈阳院总承包扎哈淖尔 35 万吨绿电铝项目推进建设',
                '作为霍林河循环经济“煤—新能源—电—铝”联营及源网荷储直供新范式的标志性工程，中铝国际工程股份有限公司所属沈阳铝镁设计研究院总承包的扎哈淖尔 35 万吨绿电铝项目正推进建设。项目以绿电替代火电支撑电解铝生产，是高载能铝工业在“双碳”目标下褪去“灰色”、焕发“青绿”的代表性工程。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/eu-scrutiny-of-anglo-mmg-nickel-deal-tests-china-stance',
                'MINING.COM', '09-11',
                '欧盟审查五矿资源收购英美资源巴西镍业务 涉及 5 亿美元交易',
                '中国五矿资源（MMG）正敦促欧洲监管机构批准其以 5 亿美元收购英美资源巴西镍业务的交易，该案被视为检验欧盟在多大程度上限制中资控制战略性资源供应链的试金石。欧盟委员会正在调查该收购是否会使 MMG 将巴西镍铁从欧洲分流、从而推高不锈钢生产商成本，预计下周将发出正式警告。MMG 公司事务执行总经理表示，相信欧盟竞争总司会把地缘政治考量放在一边、依据数据作出判断。该交易涵盖两处镍铁在产资产与两个绿地项目，于 2025 年 2 月签署。',
                orig_title='EU scrutiny of Anglo-MMG nickel deal tests China stance')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104101578-smm-news-zimbabwes-lithium-beneficiation-policy-set-to-reshape-investment-flows-move-country-up-value-chain',
                'SMM 国际站', '09-11',
                '津巴布韦锂矿本地加工政策重塑投资流向 推动价值链上移',
                '据 SMM 报道，津巴布韦能否持续吸引并留住锂矿投资，取决于其经济稳定性、基础设施建设和长期资本可得性，该国锂资源禀赋仍是吸引投资者的主要因素，但进一步释放价值需加大对加工、基础设施与电力的投入。此前出台的锂出口限制政策旨在鼓励境内加工，已在影响投资者的资本配置，预计将进一步重塑投资决策并推动津巴布韦沿锂价值链上移。境内锂矿加工需要更高的前期资本投入，但出口收益增加、附加值提升、就业创造等长期收益预计将超过初始成本；该政策还可能推动行业整合，小型锂矿企业通过代加工、合资或并购与大型运营商结成战略合作。',
                orig_title="[SMM News] Zimbabwe's Lithium Beneficiation Policy Set to Reshape Investment Flows, Move Country Up Value Chain")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104111422-smm-analysis-us-solar-adcvd-case-nears-final-ruling-threatening-6-gw-import-channel-from-india-indonesia-and-laos',
                'SMM 国际站', '09-11',
                '美国光伏反倾销反补贴案临近终裁 威胁 60 亿瓦自印度、印尼、老挝进口通道',
                '美国国际贸易委员会（USITC）于 9 月 9 日就自印度、印尼、老挝进口的晶硅光伏电池及组件反倾销、反补贴调查举行终裁阶段听证会。按现行日程，听证后书面意见于 9 月 16 日提交，委员会拟于 10 月 14 日投票，终裁与意见定于 10 月 26 日发布，当日听证未加征新关税。美国商务部此前已作出肯定性初裁，部分涉案进口已适用保证金要求，市场正等待终裁税率、USITC 损害认定以及临时措施是否转为正式“双反”令。美国商务部数据显示，2024 年美国自印度、印尼、老挝进口涉案光伏产品约 6.01 吉瓦，较 2023 年的 2.57 吉瓦增长约 134%。',
                orig_title='【SMM Analysis】 US Solar AD/CVD Case Nears Final Ruling, Threatening 6 GW Import Channel from India, Indonesia, and Laos')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104111453-smm-chromium-flash-tharisas-underground-transition-at-its-chrome-pgm-flagship-mine-remains-on-track',
                'SMM 国际站', '09-11',
                'Tharisa 铬-铂族旗舰矿地下化转型按期推进 2029 年三季度达产',
                'Tharisa 确认其位于南非布什维尔德杂岩体西南翼的旗舰 Tharisa 矿地下化转型按期、按预算推进，并与津巴布韦 Karo 铂金项目建设融资同步进行。2026 年 3 月启动的 Apollo 地下矿段正向本季度首批出矿推进，目标是 2029 日历年度三季度达到月产 25.5 万吨的稳定产能；Orion 矿段随后跟进，目标 2031 财年首次出矿、2033 日历年度三季度达产。公司表示两座地下矿段合计可将该矿（同一矿体同时副产铬精矿与铂族金属）的开采寿命在原露天矿枯竭后再延长 60 年以上。地下项目资金来自 Absa、Standard Bank 开发贷款与 Nedbank 资产抵押循环额度，与本周围绕 Karo 募集的 3 亿美元北欧债券相互独立。',
                orig_title="[SMM Chromium Flash] Tharisa's Underground Transition at Its Chrome-PGM Flagship Mine Remains On Track")),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260911_10312024.htm',
                '全球矿产资源信息系统', '09-11',
                '刚果（金）实行地质资料分级访问 加强对战略性矿产数据管控',
                '据矿业周刊援引路透社报道，刚果（金）计划加强对能够引导数十亿美元矿产勘查投资的地质数据管控，这可能影响该国未来的矿产勘探开发。官员称，刚果（金）正加快地质填图、航空测量与历史资料数字化，以建设关键矿产方面的综合性国家地质资料中心，从而降低勘查风险。该计划将使金沙萨加大对世界最大产钴国和第二大产铜国的管控力度，有分析人士认为其影响甚至超过该国重塑全球钴市场的政策。刚果（金）地质调查局（SGNC）局长透露，今年 1 月已与全球地质数据填图领先者西班牙艾克斯卡利伯（Xcalibur）公司开展合作。')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104099018-smm-tungsten-analysis-global-tungsten-markets-quintuple-dilemma-smelting-capacity-bottleneck-at-the-core',
                'SMM 国际站', '09-11',
                'SMM 钨分析：全球钨市场面临五重困境 冶炼产能瓶颈为核心',
                'SMM 钨市场分析指出，全球钨市正面临五重困境，冶炼产能瓶颈处于核心位置。同期国际钼氧化物价格大幅上行，SMM 评估天津港 CIF 钼氧化物为 33.9~34 美元/磅钼，均价 33.95 美元/磅钼（折合中国含税口径约 5,735 元/吨度），较前一交易日上涨 0.28 美元/磅钼，进口套利窗口仍然关闭。美国大型工业刀具分销商 MSC Industrial 高管 9 月 9 日警告，钨供应冲击正沿其供应链传导并持续推高工业刀具成本，碳化钨原料投入品通胀率约达 500%，成本正向下游制造商转嫁；尽管钨价已趋稳，但因钨粉采购来源与库存水平不同，各供应商调价节奏不一，涟漪式通胀效应尚未结束。',
                orig_title="[SMM Tungsten Analysis] Global Tungsten Market's Quintuple Dilemma: Smelting Capacity Bottleneck at the Core")),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://www.mining.com/usa-rare-earth-breaks-ground-at-1-2b-rare-earth-magnet-manufacturing-facility-in-south-carolina',
                'MINING.COM', '09-12',
                '美国稀土公司 12 亿美元磁材工厂在南卡罗来纳州动工',
                '美国稀土公司（Nasdaq: USAR）本周在南卡罗来纳州布莱克斯堡为其新的稀土金属与磁体制造工厂举行破土动工仪式，这是其构建美国及盟友一体化稀土供应链计划的里程碑。工厂位于切罗基县贝利工业园一处 124 英亩地块，建筑面积 80 万平方英尺，投资约 12 亿美元，预计在上州地区创造约 490 个制造岗位。公司称在全国评估近 275 个候选地块后选定布莱克斯堡，看重当地先进制造业劳动力、可靠电力、交通基础设施以及与客户和供应商的邻近性；首席执行官表示该项目把愿景从纸面计划变为正在成形的实体基础设施，并宣布向斯帕坦堡社区学院捐款 25 万美元。',
                orig_title='USA Rare Earth breaks ground at $1.2B rare earth magnet manufacturing facility in South Carolina')),
    (CAT_MA, ni('https://www.mining.com/glencore-mercuria-compete-for-venezuela-aluminum-smelter-deal',
                'MINING.COM', '09-12',
                '嘉能可与摩科瑞竞逐委内瑞拉最大铝厂 Venalum 交易',
                '嘉能可（Glencore）与摩科瑞能源集团（Mercuria）正参与竞逐委内瑞拉最大铝冶炼厂 Venalum 的交易，该交易有望使这座多年减产的老厂恢复生产。据彭博援引知情人士报道，协议结构尚不明确，但与委内瑞拉政府的讨论内容包括接管该冶炼厂运营并获取其铝产品。Venalum 位于奥尔达斯港，靠近水电资源与铝土矿，年产能约 43 万吨原铝，若达成协议有望恢复其主要生产商地位。嘉能可此前曾为该国资铝业提供融资，新协议将深化其参与；摩科瑞据称与私人矿业投资公司 Heeney Capital 合作参与本次交易。目前尚未达成任何协议。',
                orig_title='Glencore, Mercuria compete for Venezuela aluminum smelter deal')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104111527-freeport-ceo-signals-likely-go-ahead-for-45-billion-bagdad-copper-expansion',
                'SMM 国际站', '09-11',
                '自由港 CEO 释放推进 45 亿美元 Bagdad 铜矿扩建信号',
                '自由港麦克莫兰（Freeport-McMoRan）首席执行官 Kathleen Quirk 表示，公司预计将推进亚利桑那州 Bagdad 铜矿的扩建项目，在正式投资决定前释放出更强的承诺信号。她 9 月 10 日在杰富瑞全球工业大会上称，项目仍需董事会批准，但预期公司会继续推进，并称这是一项约三年的建设工程、预计不会遇到重大许可障碍。最新测算显示 Bagdad 扩建资本开支约 45 亿美元，较此前 35 亿美元的估算高约 30%，反映成本上升、范围变化与新增工程。项目将使该矿选矿产能翻倍以上，预计每年新增铜产量约 2 亿~2.5 亿磅（约 9.1 万~11.3 万吨），并新增钼 1000 万~1200 万磅；Bagdad 现有储量寿命超过 80 年。',
                orig_title='Freeport CEO Signals Likely Go-Ahead for $4.5 Billion Bagdad Copper Expansion')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-10/1225554982.PDF',
                '巨潮资讯网', '09-10',
                '无锡振华：收购德维嘉汽车电子系统（无锡）有限公司控股权并完成工商变更',
                '无锡振华公告，公司收购德维嘉汽车电子系统（无锡）有限公司控股权事项已完成，并办理完毕相应的工商登记变更手续。本次收购完成后德维嘉纳入公司合并范围，具体交易对价、股权比例与业绩承诺安排以公告全文为准。')),
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
