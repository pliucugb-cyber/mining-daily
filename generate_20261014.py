# -*- coding: utf-8 -*-
"""
生成 2026-10-14 矿业资讯速览 index.html（周三）
- 10-13 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-15）回补历史条目
- 换入 10-14 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-13 收盘 + LME 10-13 收盘（10-14 05:30 国内未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1014.py 注入），不进主页列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
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

REPORT = '2026-10-14'
GRAB = '2026-10-14'
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
                         r'\g<1>2026年10月14日 星期三', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261013_10334320.htm',
                '全球矿产资源信息系统', '10-13',
                '智利拉贝尔德斑岩铜矿规模扩大',
                '全球矿产资源信息系统报道，红吉利公司在智利拉贝尔德斑岩铜矿的钻探扩大见矿长度，DKP075 孔在 24 米深处见矿 188 米、铜品位 0.44%、金 0.16 克/吨；公司已完成 3.5 万多米钻探，希望在年底前完成初步资源量估算。')),

    (CAT_ZK, ni('https://www.mining.com/fortuna-logs-high-grade-gold-in-senegal-extends-depth',
                'MINING.COM', '10-13',
                'Fortuna 塞内加尔 Diamba Sud 金矿钻探见高品位并延深',
                'MINING.COM 报道，Fortuna Mining 在塞内加尔 Diamba Sud 项目 Southern Arc 矿段钻探见高品位矿化，DSR1149 孔自 228 米井下见矿 40.8 米、金品位 3.9 克/吨，延长了矿体深部延伸；该矿计划 2028 年二季度投产。',
                orig_title='Fortuna logs high-grade gold in Senegal, extends depth')),

    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104155236-caspin-boosts-kelpie-tin-resource-by-45-eyeing-standalone-open-pit-project',
                'SMM 国际站', '10-14',
                'Caspin 将 Kelpie 锡矿资源量提升 45%',
                'SMM 国际站报道，Caspin Resources 将其位于澳大利亚新南威尔士州 Bygoo 项目 Kelpie 锡矿的资源量提升 45%，现为 650 万吨、锡品位 0.43%、含锡 2.8 万吨，资源全部位于优化露天采坑范围内。',
                orig_title='[Caspin boosts Kelpie tin resource by 45% eyeing standalone open-pit project]')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474572',
                '中国有色金属报', '10-14',
                '江西省地质局第七大队牵头项目获江西省科学技术进步奖二等奖',
                '中国有色金属报报道，江西省地质局第七地质大队牵头完成的「南岭于山矿集区钨钼和银金铅锌成矿关键理论创新与找矿突破」项目获江西省科学技术进步奖二等奖，项目构建了两类矿床类型「三位一体」找矿预测模型，提交多处大中型矿床。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202610/t20261013_2939934.html',
                '自然资源部', '10-13',
                '经国务院批准，自然资源部与国家发展改革委发布《矿产资源目录》',
                '经国务院批准，自然资源部会同国家发展改革委发布《矿产资源目录》（2026 年第 28 号公告），按能源矿产、金属矿产、非金属矿产等类别系统列明我国法定矿种，作为矿产资源勘查开采统一登记管理的基础性目录。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104153147',
                '上海有色网', '10-14',
                '财政部：新能源汽车增值税出口退税率由 13% 下调至 9%',
                '上海有色网【锂电快讯】报道，财政部公告自 2027 年 4 月 1 日起将新能源汽车的增值税出口退税率由 13% 下调至 9%，并取消电子烟设备装置等产品增值税出口退税。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474563',
                '中国有色金属报', '10-14',
                '两项涉镁标准入选 2026 年度工业节能降碳标准研究项目清单',
                '中国有色金属报报道，工业和信息化部节能与综合利用司公示《2026 年度工业节能降碳标准研究项目清单》，其中《工业硅和镁单位产品能源消耗及碳排放限额》《温室气体 产品碳足迹量化方法与要求 原生镁锭》两项涉镁标准入选，公示期为 10 月 8 日至 10 月 14 日。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104154996',
                '上海有色网', '10-14',
                '锗锭年内涨近 102%，小金属板块活跃',
                '上海有色网数据显示，10 月 13 日锗锭均价 27250 元/千克，与 2025 年 12 月 31 日的 13500 元/千克相比年内上涨 101.85%；受供应偏紧叠加需求韧性支撑，小金属板块 10 月 13 日收涨 0.56%，云南锗业、北方稀土等涨幅居前。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/0410f7e985094354afa0ade31a227c02.html',
                '长江有色网', '10-13',
                '碳酸锂现货跌破 11 万元/吨，期货盘中一度跌超 5%',
                '长江有色金属网报道，2026 年 10 月 13 日长江综合电池级碳酸锂（99.5%）市场均价报 109000 元/吨，较上一交易日下跌 5000 元；工业级碳酸锂（99.2%）均价报 106000 元/吨，同步下跌 5000 元。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474556',
                '中国有色金属报', '10-14',
                '国庆节后沪铜库存增逾五成',
                '中国有色金属报报道，上海期货交易所数据显示，10 月 9 日当周沪铜库存周度增长 51.62% 至 58744 吨，增至近一个月新高；同期伦铜库存降至 233025 吨的近两个月新低，注销仓单占比接近 45%。')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1013/62158.html',
                '中国有色金属工业协会', '10-13',
                '1—8 月我国钴产品进出口数据分析及后市展望',
                '中国有色金属工业协会刊文分析，2026 年 8 月我国自刚果（金）进口钴湿法中间品 2332 吨，同比增长 61.8%、环比下降 51.3%；1—8 月累计进口仅 1.2 万吨、同比大降 85.4%，预计 9—12 月进口可达 4 万吨以上，下半年钴原料供应压力将明显缓解。')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1012/62140.html',
                '中国有色金属工业协会', '10-12',
                '铝价四季度上行空间受限',
                '中国有色金属工业协会刊文指出，铝价近期维持高位震荡，但美元指数触及 102.53 的阶段性高位、国内库存降幅较前期收窄，预计四季度铝价仍有支撑但上行空间相对受限。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474545',
                '中国有色金属报', '10-14',
                '国家电投集团首台电解铝柔性负荷试验槽通电',
                '中国有色金属报报道，9 月 29 日国家电投集团首台电解铝柔性负荷试验槽在铝电公司宁东分公司通电投运，项目选取 4 台 400 千安电解槽开展柔性电解槽结构与生产工艺攻关，可实现铝电解生产负荷动态可调。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474564',
                '中国有色金属报', '10-14',
                '立中集团携手重庆大学共启镁合金产业化新篇章',
                '中国有色金属报报道，立中集团与重庆大学签署高性能镁合金材料产学研战略合作协议，双方将聚焦镁合金产业化关键技术攻关，打造集研发、试制、生产、推广于一体的轻量化新材料创新平台。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474497',
                '中国有色金属报', '10-14',
                '五矿二十三冶与徐工集团签署战略合作协议',
                '中国有色金属报报道，9 月 28 日五矿二十三冶与徐工集团签署战略合作框架协议，双方将在矿山装备配套、海外项目协同、技术创新、市场开拓等方面深化务实合作。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474550',
                '中国有色金属报', '10-14',
                '洛钼矿山前三季度 ESG 成效显著',
                '中国有色金属报报道，洛阳钼业矿山公司前三季度在生态修复、低碳转型等方面取得成效，其中矿区分布式光伏总装机容量 438.62 千瓦峰值，预计年发电量 41 万千瓦时，矿卡已全部更新为新能源电动车辆。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202610/t20261013_10334319.htm',
                '全球矿产资源信息系统', '10-13',
                '埃塞俄比亚首建黄金冶炼厂',
                '全球矿产资源信息系统报道，埃塞俄比亚已建设该国首个黄金冶炼厂，该国总理艾哈迈德称项目初步投资 5000 万美元，国有企业埃塞俄比亚投资控股公司持有大多数股权，将处理来自埃塞俄比亚及其他地方的金原料。')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104155244-landslide-at-codelcos-el-teniente-mine-in-chile-kills-two-workers-operations-partially-suspended',
                'SMM 国际站', '10-14',
                '智利 Codelco El Teniente 铜矿滑坡致 2 人遇难，部分停产',
                'SMM 国际站援引智利矿业监管机构 SERNAGEOMIN 称，国有铜企 Codelco 旗下 El Teniente 铜矿因滑坡事故暂停部分作业，事故造成承包商 2 名工人死亡、1 人获救。',
                orig_title="Landslide at Codelco's El Teniente Mine in Chile Kills Two Workers, Operations Partially Suspended")),

    (CAT_GJ, ni('https://www.mining.com/south-americas-copper-boom-faces-a-170b-reality-check',
                'MINING.COM', '10-13',
                '南美铜矿热潮面临 1700 亿美元现实检验',
                'MINING.COM 援引 GEM 咨询报告指出，南美安第斯地区铜投资计划面临融资、基建与运营瓶颈，秘鲁 2026 年矿业项目组合含 66 个项目、估值约 641 亿美元，智利 2025—2034 年投资管线合计 1045 亿美元，而国际能源署预计到 2035 年铜供应较需求缺口约 25%。',
                orig_title="South America's copper boom faces a $170B reality check")),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202610/t20261013_10334321.htm',
                '全球矿产资源信息系统', '10-13',
                '澳大利亚最大矿企勘查投入严重不足',
                '全球矿产资源信息系统报道，BDO 矿业季度现金调查显示，二季度澳大利亚最大 50 家矿企勘查投资 2.39 亿澳元，仅占全国 10.5 亿澳元勘查投资的 27%，且勘查投资占存款比例不足 10% 的矿企比例高达 68%。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/ssr-to-buy-roxmore-for-464m-boosts-value-of-nevada-gold-mine',
                'MINING.COM', '10-14',
                'SSR 以 4.64 亿美元收购 Roxmore，提升内华达金矿价值',
                'MINING.COM 报道，SSR Mining 同意以 6.601 亿加元（4.64 亿美元）全现金收购内华达勘探商 Roxmore Resources，后者旗下 Converse 项目位于 Marigold 金矿以西约 6 公里，投产后有望在 10 年矿山寿命内年增 15 万至 17 万盎司黄金产量。',
                orig_title='SSR to buy Roxmore for $464M, boosts value of Nevada gold mine')),

    (CAT_MA, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474568',
                '中国有色金属报', '10-14',
                '广东鸿图拟设全资子公司推进镁合金压铸产能建设',
                '中国有色金属报报道，广东鸿图拟在肇庆市高要区设立全资子公司广东鸿镁新材料技术有限公司，作为镁合金压铸项目实施主体，拟租赁厂房面积约 16130.25 平方米、租赁期限 12 年，租赁期内租金总额预计不超过 3800 万元。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-14/1225603573.PDF',
                '巨潮资讯网', '10-14',
                '洛阳钼业全资子公司认购基金份额',
                '巨潮资讯网披露，洛阳钼业全资子公司西藏施莫克拟作为有限合伙人，以自有资金 50000 万元认购南京源峰磐茂股权投资基金份额，并以自有资金 40000 万元认购杭州和谐成长四期股权投资基金份额。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-12/1225602036.PDF',
                '巨潮资讯网', '10-12',
                '浩通科技累计出售贵金属铂 392 公斤，成交 1.64 亿元',
                '巨潮资讯网披露，浩通科技截至公告日累计出售贵金属铂 392 公斤，成交金额 16432.72 万元，交易产生的利润约 4820.74 万元，占公司最近一期经审计净利润的 10% 以上。',
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

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
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
