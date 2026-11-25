# -*- coding: utf-8 -*-
"""
生成 2026-11-25 矿业资讯速览 index.html（周三）
- 11-23 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30）回补历史条目
- 换入 11-24 采集的条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-23 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）
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

REPORT = '2026-11-25'
GRAB = '2026-11-25'
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
                         r'\g<1>2026年11月25日 星期三', html)
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
    (CAT_ZC, ni('https://news.metal.com/newscontent/MEU7VND3JXKPWXOAHX2TTKZCU7VQYUYZY3C4G6I-jamaica-plans-to-allow-bauxite-and-alumina-enterprises-to-import-lng-duty-free-reducing-industry-energy-costs',
                'SMM 国际站', '11-23',
                '牙买加拟允许铝土矿与氧化铝企业免关税进口LNG',
                '牙买加参议院 11 月 20 日通过《铝土矿与氧化铝工业（鼓励）法》修正案，拟允许铝土矿和氧化铝生产商免税进口液化天然气（LNG）。政策目标是压低当地采矿与氧化铝企业的能源成本、提升行业竞争力，并推动能源结构向清洁化转型。牙买加是全球主要铝土矿生产国，能源成本变化将直接影响当地氧化铝生产成本；该政策能否落地及实际降本幅度仍取决于后续立法流程与实施细则。',
                orig_title='Jamaica Plans to Allow Bauxite and Alumina Enterprises to Import LNG Duty-Free, Reducing Industry Energy Costs')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/dwdt/202611/t20261125_873334.html',
                '中国地质调查局', '11-25',
                '西昆仑—松潘甘孜锂矿带深部结构研究获进展，提出锂富集新机制',
                '中国地质调查局西安矿产资源调查中心在大红柳滩、甲基卡、草陇三个矿集区开展三维大地电磁成像，首次从岩石圈尺度揭示西昆仑—松潘甘孜巨型伟晶岩型锂矿带的深部结构特征。研究发现锂矿床主要分布于中下地壳穹状高导异常上方、加厚地壳与古特提斯缝合带交汇部位；热模拟表明高导异常并非现今活动岩浆房，而是古岩浆—流体通道的残留记录。研究提出地壳增厚与壳幔相互作用协同控制锂超常富集的新机制，该成矿带延伸约 2800 千米。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475584',
                '中国有色金属报', '11-25',
                'Auro Metals圣巴巴拉项目中部单孔连续见矿679.9米',
                'Auro Metals 11 月 17 日发布厄瓜多尔 Santa Barbara 金铜矿二期首批钻探化验结果，中部外围的 DSB-79 孔自地表连续见矿 679.9 米，平均金 0.44 克/吨、铜 0.14%；该区域在今年 3 月 SRK 资源模型中原被划为采坑内废石。5 个钻孔按见矿长度加权铜品位 0.115%，较原推断资源 0.09% 高近 28%。二期钻探已完成 9 个钻孔、累计进尺超 7000 米，约占 2 万米总目标的三成，钻机由一期 4 台增至 7 台。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/6YADRWSIGX2ECQNNVXNPTKIOGRBJJEXWAWRIRHQ',
                '上海有色网', '11-22',
                '智利铜产量或创23年新低，硫酸进口依赖推高堆浸成本',
                '普拉斯矿业（Plusmining）分析师帕尔多估计，2026 年智利铜产量将下降 6.6% 至 503.4 万吨，较上年减少 35.4 万吨，为 2003 年以来最低水平（当年 490.4 万吨）。8 月智利铜产量同比下降 12.7% 至 36.6 万吨，埃斯康迪达与斯宾塞降幅最大。2025 年智利硫酸进口达创纪录的 397 万吨、占其消费量近一半，冶炼厂平均产能利用率降至约 60%，SX-EW 铜成本随之抬升；该机构预计 2027 年产量回升 25 万吨。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475575',
                '中国有色金属报', '11-25',
                '铜市近强远弱走到历史极值，国内库存处近一年1.9%分位',
                '11 月中旬沪铜主力自 11 万元/吨上方跌至 10.3 万元/吨附近，11 月 23 日沪铜 2701 合约最低至 90320 元/吨，同期跨期月差扩至历史极值。截至 11 月 13 日当周，国内电解铜社会库存（不含保税区）约 6.13 万吨，处近一年 1.9% 分位；进口铜精矿现货 TC 报 -240 至 -246 美元/干吨。10 月国内电解铜产量 108.67 万吨、同比下降 0.45%，冶炼零单亏损约 4800 元/吨，LME 铜现货升水维持在 68.71 美元/吨附近。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475570',
                '中国有色金属报', '11-25',
                '天齐锂业1000吨/年电池级金属锂项目在重庆铜梁竣工',
                '天齐锂业年产 1000 吨高能锂电材料电池级金属锂项目在重庆市铜梁区竣工，成为全国首个全自动电池级金属锂工厂，项目总投资约 4 亿元。全面投产后，天齐锂业重庆金属锂总产能将提升至 1600 吨/年，成为全球单体产能规模领先的金属锂生产基地。公司 2017 年与昆瑜锂业合资成立重庆天齐接手铜梁原有业务，此前已形成 600 吨金属锂产能。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475585',
                '中国有色金属报', '11-25',
                '中铝国际签约越南平福240万吨氧化铝EPC项目',
                '11 月 16 日，中铝国际与越南平福矿石开采和选矿股份公司签署越南平福 240 万吨氧化铝 EPC 总承包合同。项目位于越南同奈省平福区，规划新建年产 240 万吨冶金级氧化铝生产线，配套 740 万吨/年洗后铝土矿产能，业主方持有当地铝土矿勘探与开采许可，具备矿—氧化铝一体化条件。EPC 范围涵盖全流程设计、设备材料供应、施工安装、竣工试验、缺陷修复及商业运营首年技术支持。')),

    (CAT_HY, ni('https://news.metal.com/newscontent/TWDKVECFKHIAKYIJ4QO4EAILUPRTUSZAHMWFGEQ-cmoc-completes-installation-of-two-autoclaves-at-kfm-copper-cobalt-mine-phase-ii-in-the-drc',
                'SMM 国际站', '11-23',
                '洛阳钼业刚果（金）KFM二期两台高压釜完成安装',
                '洛阳钼业（CMOC）11 月 20 日表示，刚果（金）KFM 铜钴矿二期两台高压釜已运抵现场并完成安装。按此前披露的投资计划，二期建设预算 10.84 亿美元，计划 2027 年投产、服务年限 15 年，新增年处理硫化矿 726 万吨并扩建湿法冶金厂，满产后年均新增铜约 10 万吨。公司持有 KFM 71.25% 权益，一期已于 2023 年达产；配套的 Nzilo II 水电站大坝已开始首仓混凝土浇筑。',
                orig_title='CMOC Completes Installation of Two Autoclaves at KFM Copper-Cobalt Mine Phase II in the DRC')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475558',
                '中国有色金属报', '11-25',
                '五矿签约厄立特里亚米尔金矿采尾EPC项目，合同额约1.8亿元',
                '厄立特里亚时间 11 月 13 日，五矿中亚南亚厄特项目部与克尔克贝特矿业股份公司（KMSC）签订米尔金矿采尾 EPC 项目合同，合同总额约 1.8 亿元，工期 12 个月，计划 2027 年 10 月竣工交付。建设内容包括米尔金矿基建剥离、尾矿库建设、道路施工与场地平整。这是该项目部继阿斯马拉铜金多金属矿埃巴多哈采剥一期、二期之后，在厄立特里亚获得的第 3 份合同。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/WTJ2NJ6LYKVMJWBWCDR34KUPQCL3IJOLIDOOOVI',
                '上海有色网', '11-25',
                '天齐锂业拟68.72亿元收购润丰矿业及上都布探矿权',
                '天齐锂业 11 月 24 日晚公告，拟通过子公司以现金收购润丰矿业、天齐兴宇 100% 股权及四川雅江上都布锂辉石、硅石矿详查探矿权，交易作价合计约 68.72 亿元；叠加承担天齐兴宇 9.2104 亿元债务，合计对价约 77.9256 亿元。核心资产烧炭沟锂矿生产规模 120 万吨/年，查明锂矿石量 6675.2 万吨、氧化锂 75.769 万吨；上都布探矿权有效期至 2031 年 10 月 17 日，尚需办理探转采。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/QQCEJ3BBJJ3GAR3BQFFXMPUS3OLSD34QGABAKDQ',
                '上海有色网', '11-24',
                '巴新潘古纳铜金矿重启遇阻，土地所有者申请禁令',
                '巴布亚新几内亚传统土地所有者正寻求阻止已关闭近 40 年的潘古纳（Panguna）铜金矿重启，部族首领 Beverly Bakaori 已申请禁令，质疑向印度 Lloyds Metals & Energy 等方授予 25 年采矿租约的合法性，并要求交还矿床控制权。该矿 1989 年在力拓持有期间因环境与收益分配抗议引发内战而关停；剩余储量估计铜 530 万吨、黄金 1930 万盎司，按当前价格价值超 1300 亿美元。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202611/t20261125_10374193.htm',
                '全球矿产资源信息系统', '11-25',
                '西澳鲁尼铌矿获授战略项目地位，审批将获跨部门协调',
                '据矿业周刊报道，澳交所上市企业 WA1 资源公司的鲁尼（Luni）铌项目已获西澳牵头机构机制授予战略项目地位，未来三年将获得州能源与经济多元化部的主动式个案管理、跨部门协调及审批协助。该项目 2025 年 11 月已获澳大利亚联邦政府认定为重大项目。WA1 表示预可行性研究已明确开发路径，目标确立澳大利亚作为世界第二大原生铌资源国的地位，开发与融资路径正在系统性评估。')),

    (CAT_GJ, ni('https://www.mining.com/tudor-sees-2-3b-value-in-treaty-creek-mine',
                'MINING.COM', '11-24',
                'Tudor公布Treaty Creek首次经济评估，税后净现值23亿美元',
                'Tudor Gold 公布不列颠哥伦比亚省 Treaty Creek 项目 Goldstorm 矿床的首次经济评估：税后净现值 23 亿美元（32 亿加元），初期投资 15.4 亿美元，28 年累计产金 468 万盎司，内部收益率 20%。第 3 至 12 年年均产金 20.23 万盎司，全生命周期年均 16.56 万盎司；按金价 3670 美元/盎司、银 50 美元/盎司、铜 5 美元/磅测算，投资回收期 3.7 年，全维持成本 1358 美元/盎司。公司尚未宣告储量，仍需取得许可与融资。',
                orig_title='Tudor sees $2.3B value in Treaty Creek mine')),
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
    ('牙买加', CAT_ZC),
    ('西昆仑', CAT_ZK),
    ('Auro', CAT_ZK),
    ('智利铜产量', CAT_SC),
    ('近强远弱', CAT_SC),
    ('金属锂项目', CAT_HY),
    ('氧化铝EPC', CAT_HY),
    ('KFM', CAT_HY),
    ('米尔金矿', CAT_HY),
    ('润丰矿业', CAT_MA),
    ('潘古纳', CAT_GJ),
    ('鲁尼', CAT_GJ),
    ('Treaty Creek', CAT_GJ),
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
