# -*- coding: utf-8 -*-
"""
生成 2026-09-17 矿业资讯速览 index.html
- 09-16 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-18）回补历史条目
- 换入 09-16 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-16 收盘 + LME 09-16 收盘，全部由 price_history_detail.json /
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
    unit_class, UNIT_SHFE_GROUP, UNIT_LME_GROUP,
)
from functools import partial


SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-17'
GRAB = '2026-09-17'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
# 用宽松匹配吃掉落点前的任意旧标题，可覆盖三种历史写法：
#   纯日期（2026-09-07~09-12，站名丢失）／「站名 日期」（09-04~09-06）／「站名 · 日期」。
# 2026-09-12 修复：此前 09-07 起写成纯日期，浏览器标签页只剩一个光秃秃的日期，看不出是什么站。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月17日 星期四', html)
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

# ============ 4. 今日新增条目（09-16~09-17 抓取，均逐源核实真实发布日期） ============
# cnmn 列表日期仍失真（第 5 次复现）：本批 474011/474012/474008/474018/474009/474000 详情页实为 09-15，
# 473843/473846/473841/473821 实为 09-08（已弃用），473963 实为 09-14；故选条前逐条抓详情页核过真实日期。
new_items = [
    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938171.html',
                '自然资源部', '09-11',
                '绿色勘查绿色矿山系列国家标准发布 覆盖主要矿产类型',
                '9 月 11 日，在 2026 中国国际矿业大会绿色发展成果发布会上，一批国家级、国际级地质矿业标准集中发布。其中《绿色矿山建设规范》系列国家标准共 10 个部分，覆盖煤炭、陆上油气田、黑色金属、有色金属、化工、非金属、黄金、砂石、水泥用灰岩、地热矿泉水等我国主要矿产类型；《固体矿产绿色勘查规范》是我国固体矿产勘查领域首项绿色勘查专项国家标准，覆盖绿色勘查设计、驻地建设、道路修建、探矿工程施工、「三废」处置、场地生态恢复与项目验收全流程，对浅井、槽探、坑道、钻探等工程提出占地约束、低扰动工艺、污染防控与分区复绿量化指标。同期发布的《岩心数字化技术规程》英文版与 ISO 8616《岩溶关键带监测技术规范》国际标准面向全球开放共享。')),
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202609/t20260911_2938173.html',
                '自然资源部', '09-11',
                '规范矿业权管理通知征求意见结束 共收到意见 279 条',
                '自然资源部公告《关于规范矿业权管理有关事项的通知（征求意见稿）》公开征求意见情况：征求意见期为 2026 年 8 月 24 日至 9 月 7 日，共收到社会各界提出的意见和建议 279 条，将认真研究并最大程度予以吸收采纳。该通知为贯彻落实《矿产资源法》《矿产资源法实施条例》起草，指向规范矿业权管理、推动矿产资源合理开发利用和增储上产、提高矿产资源保障能力。')),
    (CAT_ZC, ni('https://news.smm.cn/news/104118375',
                '上海有色网', '09-16',
                '上期所调整锡品种套期保值持仓额度自动转化标准',
                '上海期货交易所发布公告，调整锡品种套期保值持仓额度自动转化标准。该调整涉及锡期货合约套期保值持仓额度向一般持仓转化的规则，是交易所在锡价波动放大背景下对风控参数的常规优化，具体执行标准与实施时间以上期所公告为准。')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260916_10313847.htm',
                '全球矿产资源信息系统', '09-16',
                '马拉维通杜卢稀土矿钻探见富矿 重稀土品位异常高',
                '据 Miningnews.net 网站报道，金王矿业公司（AuKing Mining）在马拉维南部通杜卢（Tundulu）稀土矿初步钻探样品分析结果好于预期，且见到超常富集的重稀土。最突出结果是在 40 米深处见矿 91 米、总稀土氧化物（TREO）品位 1.51%，其中含 15 米厚、品位 3.4% 的矿体；另一孔自地表开始见矿 80 米、TREO 品位 1.54%，其中含 11 米厚、品位 4.33% 的矿体。重稀土-钇（HREE-Y）矿段品位异常高，首个孔在 68 米深处见矿 8 米、HREE-Y 品位 16.09%，第二个孔在 13 米深处见矿 42 米、品位 11.46%。公司称 4300 米反循环钻探将支撑年底前首次形成资源量。')),
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260912_2938231.html',
                '自然资源部', '09-12',
                '中沙地学合作首批 24 幅精细地质填图成果发布',
                '9 月 11 日，在 2026 中国国际矿业大会中亚西亚矿业投资推介会上，沙特地质调查局发布由中国地质调查局牵头实施的沙特阿拉伯地盾首批 24 幅 1∶10 万精细地质填图成果，总面积达 7.08 万平方千米，覆盖阿拉伯地盾区重要金、铜、锌、铬以及稀有金属成矿带，是沙特首次在该区域获得的系统性大比例尺高精度基础地质填图成果。项目覆盖地盾区约 60 万平方千米，为本世纪全球规模最大的地质填图技术服务项目；填图过程中新识别出一批矿化异常与找矿线索，圈定了系列具有勘查潜力的成矿远景区，成果数据已接入沙特国家地学数据库门户开放共享。')),
    (CAT_ZK, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474018',
                '中国有色金属报', '09-15',
                '洛阳特种材料研究院攻克超大规格镁稀土合金构件制备难题',
                '洛阳特种材料研究院攻克超大规格镁稀土合金构件制备难题，在镁稀土合金大尺寸构件的组织均匀性控制与成形工艺上取得突破。镁稀土合金是航空航天、军工装备轻量化的关键材料，超大规格构件制备长期受制于凝固组织不均、成形合格率低等瓶颈，该突破为镁稀土合金在高端装备上的工程化应用提供了工艺支撑。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474011',
                '中国有色金属报', '09-15',
                '沪铜库存连降 3 周 刷新逾两年最低位',
                '上海期货交易所数据显示，9 月 11 日当周沪铜库存继续下滑，周度库存减少 13.05% 至 54780 吨，降至逾两年新低。目前铜精矿现货加工费持续下跌，叠加副产品硫酸价格回落，冶炼厂生产压力较前期增加，整体供应增量受限；国际铜库存减少 1901 吨至 14690 吨。伦敦金属交易所（LME）上周伦铜库存先增后降、整体小幅增加，最新库存水平 234475 吨；纽铜库存 9 月 10 日创历史新高 767664 短吨后有所回落。截至 9 月 11 日，LME、COMEX、SHFE 合计库存 105.68 万吨，同比大幅增加近 50 万吨，其中 COMEX 独占七成以上。')),
    (CAT_SC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474012',
                '中国有色金属报', '09-15',
                '世界黄金协会：8 月全球黄金 ETF 吸金 180 亿美元',
                '世界黄金协会数据显示，8 月全球黄金 ETF 资金净流入约 180 亿美元，黄金 ETF 持仓与资产管理规模继续攀升。在美联储货币政策转向预期与地缘不确定性叠加的背景下，机构与个人投资者持续增配黄金资产，黄金作为避险与抗通胀配置工具的吸引力增强。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX018/202609/575f3645e5424eb097c2a660ad6a642f.html',
                '长江有色网', '09-16',
                '刚果（金）上半年铜出口 172 万吨 欧美采购份额翻倍',
                '刚果（金）上半年铜出口量达 172 万吨，其中对欧美市场的采购份额实现翻倍。作为非洲最大铜生产国，刚果（金）铜出口结构正由传统亚洲市场向欧美延伸，反映欧美在关键矿产供应链多元化布局下对非洲铜资源采购力度的提升。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202609/ce5b82aa3b954cc2a89c42ac337fc6d6.html',
                '长江有色网', '09-16',
                '8 月原铝产量 398 万吨创历史新高 高利润驱动产能释放',
                '8 月我国原铝产量达 398 万吨，创历史新高。高利润驱动下冶炼厂全力释放产能，电解铝运行产能维持高位。产量创新高与铝价走强形成正反馈，后续需关注需求端承接能力与库存变化对价格的支撑力度。')),
    (CAT_HY, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=473963',
                '中国有色金属报', '09-14',
                '陕西有色天策科技百吨级中间相沥青基碳纤维产线正式投产',
                '陕西有色天策科技百吨级中间相沥青基碳纤维生产线正式投产，实现该高端碳材料从实验室走向规模化生产。中间相沥青基碳纤维具有高导热、高模量特性，长期依赖进口，产线投产有助于推动相关材料在航空航天、电子散热等领域的国产化替代。')),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-17/1225568541.PDF',
                '巨潮资讯网', '09-17',
                '中金岭南凡口铅锌矿复工复产事项取得进展',
                '中金岭南公告，公司凡口铅锌矿复工复产事项取得进展。凡口铅锌矿为国内大型铅锌矿山，本次公告就复产推进情况作出说明，具体复产安排、时间节点与产能恢复进度详见巨潮资讯网公告原文。',
                embed='pdf')),
    (CAT_HY, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260912_2938228.html',
                '自然资源部', '09-12',
                '两份矿业权威报告发布 我国 14 种矿产储量居世界第一',
                '9 月 11 日，自然资源部在 2026（第二十八届）中国国际矿业大会上发布《中国矿产资源报告 2026》和《全球矿业发展报告 2026》。报告显示，截至「十四五」末，我国稀土、钨、锡等 14 种矿产储量居世界第一位，煤、铁、锰、钛等 9 种矿产储量居世界前四位；矿产资源供需格局分化特征愈发突出。2025 年我国地质勘查投资连续第五年正增长，采矿业固定资产投资连续第五年正增长；「十四五」时期全国完成历史遗留废弃矿山修复治理面积 22.3 万公顷，超额完成预期目标任务 19.6%。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/eu-objects-to-mmgs-anglo-american-nickel-deal',
                'MINING.COM', '09-16',
                '欧盟对五矿资源收购英美资源镍业务提出异议',
                '欧盟委员会对五矿资源（MMG）收购英美资源集团（Anglo American）镍业务的交易提出异议。该交易标的为英美资源旗下镍资产，此前已进入欧盟并购审查程序，欧盟委员会在审查意见中表达了反对立场，交易能否推进取决于监管审查结果。',
                orig_title="EU objects to MMG's Anglo American nickel deal")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104117798-smm-analysis-indonesia-revises-nickel-ore-hpm-o',
                'SMM 国际站', '09-16',
                '印尼年内再次修订镍矿内贸基准价（HPM）公式 褐铁矿价向市场靠拢',
                '据 SMM 分析，印度尼西亚年内再次修订镍矿内贸基准价（HPM）定价公式，推动褐铁矿（limonite）价格向市场价格水平靠拢。HPM 是印尼镍矿内贸交易的官方基准价，本次调整将直接影响印尼镍矿销售定价与下游镍冶炼成本，市场关注其对镍价与镍铁、硫酸镍环节的传导。',
                orig_title='Indonesia Revises Nickel Ore HPM Once Again, Pulling Limonite Prices Toward Market Levels')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104118420-alba-restores-80-of-pre-war-aluminium-productio',
                'SMM 国际站', '09-17',
                'Alba 恢复 80% 铝产能 改由沙特通道出口',
                '据 SMM 国际站报道，铝生产商 Alba 已恢复其此前 80% 的铝产能，并改由沙特通道安排出口。产能与物流通道的恢复有助于缓解区域铝供应扰动，后续实际到货节奏与区域升贴水变化仍待观察。',
                orig_title='Alba Restores 80% of Pre-War Aluminium Production, Exports via Saudi a…')),
    (CAT_GJ, ni('https://www.mining.com/sudan-gold-mine-collapse-kills-at-least-60-miners',
                'MINING.COM', '09-16',
                '苏丹一金矿发生坍塌事故 至少 70 名矿工遇难',
                '苏丹一座金矿发生坍塌事故，造成至少 70 名矿工死亡。苏丹是非洲重要黄金生产国，手工与小规模采金活动广泛，矿难频发，此次事故再次暴露当地小规模采金安全管理缺位问题。',
                orig_title='Sudan gold mine collapse kills at least 70 miners')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-15/1225564431.PDF',
                '巨潮资讯网', '09-15',
                '焦作万方终止发行股份购买资产并撤回申请文件',
                '焦作万方（000612）公告，公司决定终止发行股份购买资产暨关联交易事项，并向监管机构撤回相关申请文件。该重组事项此前已推进多时，终止后公司股票交易与后续资本运作安排以正式公告为准，具体原因详见巨潮资讯网公告原文。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-17/1225569068.PDF',
                '巨潮资讯网', '09-17',
                '紫金矿业全资子公司与关联人共同投资',
                '紫金矿业公告，公司全资子公司拟与关联人共同投资。该事项属关联交易范畴，公司已按信息披露要求履行相关程序并披露，具体投资标的、金额与股权安排详见巨潮资讯网公告原文。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-17/1225568224.PDF',
                '巨潮资讯网', '09-17',
                '永臻股份投建年产 6 万吨成品电池铝箔项目',
                '永臻股份公告，公司拟投资建设年产 6 万吨成品电池铝箔项目。项目指向新能源电池铝箔环节的产能扩张，建成后将提升公司在锂电铝箔领域的供应能力，具体投资规模与建设周期详见巨潮资讯网公告原文。',
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
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字（如 113米看成别的）。
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
