# -*- coding: utf-8 -*-
"""
生成 2026-10-13 矿业资讯速览 index.html（周二）
- 10-12 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-14）回补历史条目
- 换入 10-13 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-12 收盘 + LME 10-12 收盘（10-13 05:30 国内未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1013.py 注入），不进主页列表
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

REPORT = '2026-10-13'
GRAB = '2026-10-13'
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
                         r'\g<1>2026年10月13日 星期二', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261012_10333289.htm',
                '全球矿产资源信息系统', '10-12',
                '马拉维通杜卢钻探发现更多稀土矿体',
                '全球矿产资源信息系统报道，马拉维通杜卢（Tundulu）项目钻探发现更多稀土矿体，矿区稀土矿化范围进一步扩大。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/flfg/202610/t20261012_10333288.htm',
                '全球矿产资源信息系统', '10-12',
                '加纳新矿法草案拟恢复矿权 20 年期限',
                '全球矿产资源信息系统报道，加纳新矿法草案拟恢复矿权 20 年期限，相关修订旨在稳定矿业投资者预期。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104148841',
                '上海有色网', '10-13',
                '广期所就氢氧化锂期货公开征求意见，上市临近',
                '上海有色网报道，广州期货交易所就氢氧化锂期货合约及相关规则公开征求意见，新品种上市临近，多家产业链企业已抢先布局。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104150533',
                '上海有色网', '10-12',
                '津巴布韦称没有理由推迟锂精矿出口禁令',
                '上海有色网【锂电快讯】报道，津巴布韦方面表示没有理由推迟锂精矿出口禁令，当地锂精矿出口政策继续推进。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104152525',
                '上海有色网', '10-13',
                '终端需求走弱，钨价自历史高点回撤近七成',
                '上海有色网【SMM 评论】指出，终端需求走弱，钨价自历史高点回撤近七成，市场关注后续哪些变量将影响钨市方向。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/a24f388affdc4e2e90c94dae02d5e812.html',
                '长江有色网', '10-12',
                '碳酸锂刷新年内低点，期货暴跌 11.79%',
                '长江有色网报道，碳酸锂价格刷新年内低点，期货单日暴跌 11.79%，强现实难敌远期供给压力。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/0017c82741e74e5bbd636429010b541d.html',
                '长江有色网', '10-12',
                '期现劈叉、升水高位塌方：11 万铜价背后的铜市「虚实博弈」',
                '长江有色网报道，铜价站上 11 万元/吨关口后，期现结构出现劈叉、现货升水高位塌方，铜市「虚实博弈」加剧。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/94f1ad09d30f40b5b8ee61d7945de182.html',
                '长江有色网', '10-13',
                'LME 金属期货普遍下跌，伦铜表现一枝独秀',
                '长江有色网报道，LME 金属期货普遍下跌，其中伦铜表现一枝独秀。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202610/t20261012_10333291.htm',
                '全球矿产资源信息系统', '10-12',
                '上周五国际铂钯价格涨幅居前',
                '全球矿产资源信息系统报道，上周五国际铂、钯价格涨幅居前。')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1012/62142.html',
                '中国有色金属工业协会', '10-12',
                '高库存对上弱需求，镍价震荡偏弱运行',
                '中国有色金属工业协会刊发分析指出，镍市高库存对上弱需求，镍价震荡偏弱运行。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104152806',
                '上海有色网', '10-13',
                '北方稀土前三季度净利同比预增 134.95%—138.84%',
                '上海有色网报道，北方稀土预计 2026 年前三季度净利润同比增长 134.95% 至 138.84%，主要稀土产品价格高位震荡带动业绩改善。')),

    (CAT_HY, ni('https://news.smm.cn/news/104152859',
                '上海有色网', '10-13',
                '金钼股份前三季度净利同比增 30.94%',
                '上海有色网报道，金钼股份 2026 年前三季度净利润同比增长 30.94%，公司称各类钼产品价格较上年同期上涨。')),

    (CAT_HY, ni('https://news.smm.cn/news/104152506',
                '上海有色网', '10-13',
                '大全能源：多晶硅仍处供需再平衡阶段',
                '上海有色网报道，大全能源表示当前多晶硅仍处于供需再平衡阶段，实际产量变化是影响行业基本面的核心变量。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-13/1225600571.PDF',
                '巨潮资讯网', '10-13',
                '宝地矿业：控股子公司备战矿业取得采矿安全设施设计审查意见书并转入基建期',
                '巨潮资讯网披露，新疆宝地矿业股份有限公司公告其控股子公司备战矿业取得采矿安全设施设计审查意见书，项目转入基建期。',
                embed='pdf')),

    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/1012/62144.html',
                '中国有色金属工业协会', '10-12',
                '中铝国际贵阳院破解炭素焙烧烟气治理难题',
                '中国有色金属工业协会报道，中铝国际贵阳院在炭素焙烧烟气治理环节取得突破，破解了该工序的环保治理难题。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104152920-dynacor-completes-first-senegal-gold-pour-at-galam-pilot-plant',
                'SMM 国际站', '10-13',
                'Dynacor 完成塞内加尔 Galam 中试厂首次黄金浇铸',
                'SMM 国际站报道，Dynacor Gold Mines 宣布其位于塞内加尔的 Galam 中试厂完成首次黄金浇铸。',
                orig_title='Dynacor completes first Senegal gold pour at Galam pilot plant')),

    (CAT_GJ, ni('https://www.mining.com/governments-turn-mining-data-into-billions-in-revenue',
                'MINING.COM', '10-12',
                '各国政府将矿业数据转化为数十亿美元收入',
                'MINING.COM 报道，透明度规则正在重塑矿业交易，暴露非法资金流动，并使各国政府对资源财富拥有更大的议价能力。',
                orig_title='Governments turn mining data into billions in revenue')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104152904-smm-analysis-zimbabwes-lithium-product-exports-top-us2159-billion-in-first-three-quarters-of-2026',
                'SMM 国际站', '10-13',
                '津巴布韦前三季度锂产品出口额突破 21.59 亿美元',
                'SMM 国际站报道，2026 年前三季度津巴布韦锂产品出口额突破 21.59 亿美元。',
                orig_title="[SMM Analysis] Zimbabwe's Lithium Product Exports Top US$2.159 Billion in First Three Quarters of 2026")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-13/1225601876.PDF',
                '巨潮资讯网', '10-13',
                '浙商中拓参与江苏德龙镍业等 30 家公司实质合并重整投资暨收购资产',
                '巨潮资讯网披露，浙商中拓公告参与江苏德龙镍业有限公司等 30 家公司实质合并重整投资的进展，并披露对外投资收购资产事项。',
                embed='pdf')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104152919-kenmare-confirms-non-binding-approach-for-mozambique-mine-owner',
                'SMM 国际站', '10-13',
                'Kenmare 确认就收购莫桑比克矿山业主提出非约束性接触',
                'SMM 国际站报道，肯梅尔资源（Kenmare Resources）确认已就收购莫桑比克一处矿山业主提出非约束性接触，交易尚处早期阶段。',
                orig_title='Kenmare confirms non-binding approach for Mozambique mine owner')),

    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202610/t20261012_10333290.htm',
                '全球矿产资源信息系统', '10-12',
                '派厄尼尔公司拟收购阿根廷铜金银矿',
                '全球矿产资源信息系统报道，派厄尼尔公司拟收购阿根廷一处铜金银矿项目。')),

    (CAT_MA, ni('https://www.mining.com/energyx-inks-10-year-2b-lithium-offtake-deal-with-trafigura',
                'MINING.COM', '10-13',
                'EnergyX 与托克签署 10 年期锂产品承购协议',
                'MINING.COM 报道，EnergyX 与托克（Trafigura）签署 10 年期锂产品承购协议，覆盖其位于智利的 Black Giant 项目与得克萨斯州的 Lonestar 项目。',
                orig_title='EnergyX inks 10-year, $2B lithium offtake deal with Trafigura')),

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
