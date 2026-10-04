# -*- coding: utf-8 -*-
"""
生成 2026-10-05 矿业资讯速览 index.html（周一 · 国庆假期第 5 天）
- 10-04 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-02）回补历史条目
- 换入 10-05 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-30 收盘（现算）
  + LME 卡片=走势图末点口径 10-02 收盘（周一国庆假期电子盘未收盘），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易），不进主页列表
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

REPORT = '2026-10-05'
GRAB = '2026-10-05'
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
                         r'\g<1>2026年10月05日 星期一', html)
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
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104143453-cascadia-intersects-7555-m-at-119-cu-at-carmacks-copper-gold-project',
                'SMM 国际站', '10-02',
                'Cascadia 育空 Carmacks 铜金矿见矿 75.55 米，铜品位 1.19%',
                'SMM 国际站报道，加拿大 Cascadia Minerals 公布育空地区 Carmacks 铜金矿项目 2026 年勘探新成果：钻孔 CD-26-058 见矿 75.55 米，铜品位 1.19%、金品位 0.97 克/吨，其中 14.50 米段铜品位 2.30%、金品位 2.68 克/吨，折合铜当量 5.08%；钻孔 CD-26-059 见矿 93.99 米，铜品位 0.96%、金品位 0.70 克/吨。公司称新结果把 Zone 2000S 矿化延伸至现有资源量边界之外，视厚度约为钻进厚度的 60%~70%。',
                orig_title='Cascadia Intersects 75.55 m at 1.19% Cu at Carmacks Copper-Gold Project')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104143393-smm-flash-news-south32-revised-q4-26-cif-mjp-premium-offer-at-us265mt',
                'SMM 国际站', '10-02',
                'South32 将四季度 MJP 铝升水报价下调至 265 美元/吨',
                'SMM 国际站援引市场消息报道，South32 将 2026 年四季度 CIF 日本 MJP 铝升水报价由此前的 325 美元/吨下调至 265 美元/吨，降幅 60 美元/吨，该报价有效期至 2026 年 10 月 5 日。',
                orig_title="[SMM Flash News] South32 Revised Q4 '26 CIF MJP Premium Offer at US$265/mt")),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474356',
                '中国有色金属报', '09-29',
                '供应压力显现，铜价将震荡走强',
                '中国有色金属报分析文章指出，美联储 9 月加息 25 个基点落地后铜价仅短暂回调即快速修复，全球铜精矿供应延续偏紧：自由港推迟印尼 Grasberg 全面复产，刚果（金）8 月初宣布禁止铜精矿出口，Antofagasta 与 Lundin 分别下调 2026 年铜产量指引。国内 9 月精炼铜产量预计 113.93 万吨，上期所精炼铜库存降至 5.61 万吨，文章认为四季度铜价将震荡偏强运行。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474365',
                '中国有色金属报', '09-29',
                '“金九”预期落空，镁价筑底运行',
                '中国有色金属报报道，9 月第 4 周国内镁市先弱后稳：截至 9 月 25 日陕西府谷 99.9% 镁锭主流成交价约 1.575 万元/吨，较上上周五小幅回落约 100 元/吨，重回谷底区间。“金九”旺季预期落空、供需未明显改善，但煤价高位推升生产成本、镁厂挺价意愿较强，预计国庆节前镁价以筑底运行为主。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260929_10325841.htm',
                '全球矿产资源信息系统', '09-29',
                '国际金银价格大幅下跌，LME 六种基本金属普跌',
                '全球矿产资源信息系统报道，周一国际金银价格跳水：纽约商品交易所黄金收于 4,115.0 美元/盎司、下跌 3.97%，白银 60.63 美元/盎司、下跌 5.65%，铂 1,724.1 美元/盎司、下跌 3.01%，钯 1,223.0 美元/盎司、下跌 4.15%。同日伦敦金属交易所铜收于 14,469.00 美元/吨、下跌 1.07%，铝 3,248.00 美元/吨、下跌 0.85%，铅、锌、镍、锡跌幅在 1.12%~1.35% 之间。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202609/t20260928_10324228.htm',
                '全球矿产资源信息系统', '09-28',
                '8 月世界粗钢产量同比下降 1.2%，中国下降 3.7%',
                '全球矿产资源信息系统援引世界钢铁协会对 70 个国家的统计，8 月世界粗钢产量 1.442 亿吨、同比下降 1.2%，其中中国产量 7,460 万吨、同比下降 3.7%。印度 1,480 万吨、增长 4.6%，日本 670 万吨、增长 0.4%，韩国 540 万吨、增长 2.6%，越南 270 万吨、增长 36.4%；欧盟 27 国 890 万吨、下降 1.0%，美国 730 万吨、增长 3.0%，巴西 270 万吨、下降 6.2%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474411',
                '中国有色金属报', '10-01',
                '2026 年先进有色金属（稀有）材料现代产业链共链行动大会在成都召开',
                '中国有色金属报报道，9 月 29 日 2026 年先进有色金属（稀有）材料现代产业链共链行动大会在四川成都召开，由国务院国资委、工业和信息化部、中国有色金属工业协会和中国铝业集团有限公司指导。中国有色金属工业协会党委书记敖宏致辞指出，2023 年以来国家对镓、锗、锑、铟等实施两用物项出口管制，全行业正加快向高端新材料开发迈进；会上中铝科学院、中铝乾星与科研院所签订联合攻关协议，并与上下游重点企业就产业协同技术攻关签约。')),

    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260929_10325840.htm',
                '全球矿产资源信息系统', '09-29',
                '格陵兰矿业公司在法兰克福证券交易所二次上市',
                '全球矿产资源信息系统援引矿业周刊报道，纳斯达克上市企业格陵兰矿产公司在法兰克福证券交易所二次上市，普通股已于 9 月 25 日开始交易，此次上市未发行新股。公司希望借此拓宽欧洲投资者渠道并取得欧盟原材料联盟成员资格，推进“北大西洋关键金属走廊”策略；其拥有格陵兰萨法托克（Sarfartoq）和斯卡尔加德（Skaergaard）稀土项目，以及东格陵兰金钯铂项目。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/top-50-mining-companies-take-264-billion-hit-as-gold-trade-unwinds-lithium-stocks-exit/',
                'MINING.COM', '10-04',
                '全球 50 大矿业公司 9 月市值缩水 2,640 亿美元',
                'MINING.COM 报道，全球市值最高的 50 家矿业公司 9 月末合计市值 2.26 万亿美元，单月缩水 2,640 亿美元，为该项排名历史上第二大月度跌幅，并回吐了 8 月创纪录的 3,570 亿美元涨幅的四分之三。主因是金价下跌，铜矿股亦未跟随创纪录的铜价上行，锂生产商中仅一家仍在榜单内。',
                orig_title='Top 50 mining companies take $264 billion hit as gold trade unwinds, lithium stocks exit')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260929_10325837.htm',
                '全球矿产资源信息系统', '09-29',
                '美国拟为阿根廷关键矿产与能源项目提供 70 亿美元融资',
                '全球矿产资源信息系统援引 MINING.COM 报道，美国与阿根廷在联合国大会期间宣布，美国进出口银行将为阿根廷关键矿产和能源项目提供 70 亿美元资金，用于推进“安第斯—大西洋走廊”（安大走廊）建设，加大对交通、能源、矿产和数字基础设施的公共与私人投资。未来两年在阿根廷经营的企业可利用该资金采购美国设备，协议意在扩大美方获取锂、铜、稀土等矿产的渠道；两国 2 月宣布的关键矿产协定尚待阿根廷国会批准。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260928_10324229.htm',
                '全球矿产资源信息系统', '09-28',
                '秘鲁拟 5~6 年内将铜产量增加 100 万吨',
                '全球矿产资源信息系统援引 BNAmericas 报道，秘鲁总统藤森庆子在联合国大会期间向国际投资者推介采矿业机遇，强调吸引私人投资；目前秘鲁关键矿产项目超过 130 个、总投资额超 640 亿美元，希望建立战略矿产伙伴关系。秘鲁能矿部长辛诺透露，世界两大经济体均在考虑投资该国矿产资源；受矿石品位下降与反矿社会冲突影响，今年秘鲁铜产量预计维持在 250 万~270 万吨，政府希望未来 5~6 年内将铜产量增加 100 万吨。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260930_10327480.htm',
                '全球矿产资源信息系统', '09-30',
                '日线资源 Colosseum 金矿获美方支持，泰兰纳拟入股安哥拉库拉稀土矿',
                '全球矿产资源信息系统援引 Miningnews.net 报道，日线资源公司（Dateline Resources）在美国加利福尼亚州的科罗索姆（Colosseum）金矿获美国国防部与司法部支持，暂缓执行一项旨在叫停该矿开发的初步禁令，国防部认为该矿事关国家安全且具稀土找矿潜力。泰兰纳资源公司（Tyranna Resources）将投资 160 万美元分阶段获得安哥拉库拉（Coola）稀土-铌矿 50% 权益，再投 100 万美元可进一步增至 70%，彭萨纳（Pensana）所持权益将由 40% 降至 20%。')),

    # ── 💼 矿权交易（仅入 rightsSection 数据层，不进主列表） ───
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
